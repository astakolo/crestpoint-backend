import logging
from decimal import Decimal

from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import status, generics, filters
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from crestpoint_credit.accounts.models import BankAccount
from .models import (
    Stock,
    InvestmentAccount,
    StockHolding,
    InvestmentTransaction,
)
from .serializers import (
    StockSerializer,
    StockDetailSerializer,
    InvestmentAccountSerializer,
    StockHoldingSerializer,
    InvestmentTransactionSerializer,
    BuyStockSerializer,
    SellStockSerializer,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Market / Stock views
# ---------------------------------------------------------------------------


class MarketListView(generics.ListAPIView):
    """
    GET /investments/market/
    List available stocks with current prices.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = StockSerializer
    queryset = Stock.objects.all()
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["symbol", "name"]
    ordering_fields = ["symbol", "current_price", "change_percent"]
    ordering = ["symbol"]


class StockDetailView(generics.RetrieveAPIView):
    """
    GET /investments/market/<pk>/
    Retrieve a single stock's detail.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = StockDetailSerializer
    queryset = Stock.objects.all()


# ---------------------------------------------------------------------------
# Investment account & portfolio views
# ---------------------------------------------------------------------------


class InvestmentAccountView(APIView):
    """
    GET /investments/account/
    Get the authenticated user's investment account (creates one if not exists).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        account, created = InvestmentAccount.objects.get_or_create(
            user=request.user,
            defaults={
                "balance": Decimal("0.00"),
                "total_invested": Decimal("0.00"),
                "total_returns": Decimal("0.00"),
            },
        )
        serializer = InvestmentAccountSerializer(account)
        return Response(serializer.data, status=status.HTTP_200_OK)


class PortfolioListView(generics.ListAPIView):
    """
    GET /investments/portfolio/
    List the authenticated user's stock holdings.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = StockHoldingSerializer
    ordering = ["-created_at"]

    def get_queryset(self):
        try:
            inv_account = InvestmentAccount.objects.get(user=self.request.user)
        except InvestmentAccount.DoesNotExist:
            return StockHolding.objects.none()
        return StockHolding.objects.filter(
            investment_account=inv_account
        ).select_related("stock")


# ---------------------------------------------------------------------------
# Buy / Sell views
# ---------------------------------------------------------------------------


@method_decorator(never_cache, name="dispatch")
class BuyStockView(APIView):
    """
    POST /investments/buy/
    Buy stock shares (debits bank account, credits investment account).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = BuyStockSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        stock = serializer._stock
        account = serializer._account
        quantity = serializer.validated_data["quantity"]
        total_cost = (stock.current_price * quantity).quantize(Decimal("0.01"))

        # Get or create investment account
        inv_account, _ = InvestmentAccount.objects.get_or_create(
            user=request.user,
            defaults={
                "balance": Decimal("0.00"),
                "total_invested": Decimal("0.00"),
                "total_returns": Decimal("0.00"),
            },
        )

        # Debit bank account
        account.balance -= total_cost
        account.save(update_fields=["balance", "updated_at"])

        # Update or create holding
        holding, created = StockHolding.objects.update_or_create(
            investment_account=inv_account,
            stock=stock,
            defaults={
                "quantity": StockHolding.objects.filter(
                    investment_account=inv_account, stock=stock
                ).first().quantity + quantity if not created else quantity,
                "current_value": 0,  # Will be recalculated
                "pnl": 0,
            },
        )
        if not created:
            holding.quantity += quantity
        else:
            holding.quantity = quantity
            holding.average_buy_price = stock.current_price

        # Recalculate average buy price
        old_total = holding.total_invested
        holding.total_invested = old_total + total_cost
        holding.average_buy_price = (holding.total_invested / holding.quantity).quantize(
            Decimal("0.01")
        )
        holding.current_value = (stock.current_price * holding.quantity).quantize(
            Decimal("0.01")
        )
        holding.pnl = (holding.current_value - holding.total_invested).quantize(
            Decimal("0.01")
        )
        holding.save()

        # Update investment account
        inv_account.total_invested = (
            inv_account.total_invested + total_cost
        ).quantize(Decimal("0.01"))
        inv_account.save(update_fields=["total_invested", "updated_at"])

        # Create transaction record
        txn = InvestmentTransaction.objects.create(
            investment_account=inv_account,
            stock=stock,
            transaction_type="buy",
            quantity=quantity,
            price_per_unit=stock.current_price,
            amount=total_cost,
            status="completed",
        )

        logger.info(
            "User %s bought %s shares of %s for %s",
            request.user.email,
            quantity,
            stock.symbol,
            total_cost,
        )

        return Response(
            InvestmentTransactionSerializer(txn).data,
            status=status.HTTP_201_CREATED,
        )


@method_decorator(never_cache, name="dispatch")
class SellStockView(APIView):
    """
    POST /investments/sell/
    Sell stock shares (credits bank account).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = SellStockSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        stock = serializer._stock
        account = serializer._account
        holding = serializer._holding
        quantity = serializer.validated_data["quantity"]
        total_proceeds = (stock.current_price * quantity).quantize(Decimal("0.01"))

        inv_account = holding.investment_account

        # Credit bank account
        account.balance += total_proceeds
        account.save(update_fields=["balance", "updated_at"])

        # Update holding
        holding.quantity -= quantity
        holding.total_invested = (holding.average_buy_price * holding.quantity).quantize(
            Decimal("0.01")
        )
        holding.current_value = (stock.current_price * holding.quantity).quantize(
            Decimal("0.01")
        )
        holding.pnl = (holding.current_value - holding.total_invested).quantize(
            Decimal("0.01")
        )

        if holding.quantity == 0:
            holding.delete()
        else:
            holding.save()

        # Update investment account
        investment_cost = (holding.average_buy_price * quantity) if not holding.quantity == 0 else (holding.average_buy_price * quantity) if quantity else Decimal("0.00")
        inv_account.total_invested = max(
            (inv_account.total_invested - investment_cost).quantize(Decimal("0.01")),
            Decimal("0.00"),
        )
        inv_account.total_returns = (
            inv_account.total_returns + (total_proceeds - investment_cost)
        ).quantize(Decimal("0.01"))
        inv_account.save(update_fields=["total_invested", "total_returns", "updated_at"])

        # Create transaction record
        txn = InvestmentTransaction.objects.create(
            investment_account=inv_account,
            stock=stock,
            transaction_type="sell",
            quantity=quantity,
            price_per_unit=stock.current_price,
            amount=total_proceeds,
            status="completed",
        )

        logger.info(
            "User %s sold %s shares of %s for %s",
            request.user.email,
            quantity,
            stock.symbol,
            total_proceeds,
        )

        return Response(
            InvestmentTransactionSerializer(txn).data,
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Transaction history
# ---------------------------------------------------------------------------


class InvestmentHistoryView(generics.ListAPIView):
    """
    GET /investments/history/
    List the authenticated user's investment transactions.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = InvestmentTransactionSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    ordering_fields = ["created_at", "amount"]
    ordering = ["-created_at"]

    def get_queryset(self):
        try:
            inv_account = InvestmentAccount.objects.get(user=self.request.user)
        except InvestmentAccount.DoesNotExist:
            return InvestmentTransaction.objects.none()

        qs = InvestmentTransaction.objects.filter(
            investment_account=inv_account
        ).select_related("stock")

        txn_type = self.request.query_params.get("type")
        if txn_type:
            qs = qs.filter(transaction_type=txn_type)

        txn_status = self.request.query_params.get("status")
        if txn_status:
            qs = qs.filter(status=txn_status)

        return qs