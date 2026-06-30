import logging
from decimal import Decimal

from django.utils.decorators import method_decorator
from django.utils import timezone
from django.views.decorators.cache import never_cache
from rest_framework import status, generics, filters
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from crestpoint_credit.security.permissions import IsAdminRole
from crestpoint_credit.accounts.models import BankAccount
from .models import (
    CryptoWallet,
    CryptoTransaction,
    CryptoTransactionStatus,
    generate_wallet_address,
)
from .serializers import (
    CryptoWalletSerializer,
    CryptoDepositCreateSerializer,
    CryptoWithdrawalCreateSerializer,
    CryptoTransactionSerializer,
    CryptoTransactionAdminSerializer,
    AdminProcessCryptoDepositSerializer,
)

logger = logging.getLogger(__name__)

# Mock exchange rates for crypto to USD
MOCK_EXCHANGE_RATES = {
    "BTC": Decimal("97542.30"),
    "ETH": Decimal("3687.15"),
    "USDT": Decimal("1.00"),
}


# ---------------------------------------------------------------------------
# User-facing views
# ---------------------------------------------------------------------------


class CryptoWalletView(APIView):
    """
    GET /crypto/wallet/
    Get the authenticated user's crypto wallet (creates one if not exists).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        wallet, created = CryptoWallet.objects.get_or_create(
            user=request.user,
            defaults={
                "wallet_address": generate_wallet_address(),
                "currency": "BTC",
                "balance": Decimal("0"),
            },
        )
        serializer = CryptoWalletSerializer(wallet)
        http_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(serializer.data, status=http_status)


@method_decorator(never_cache, name="dispatch")
class CryptoDepositCreateView(APIView):
    """
    POST /crypto/deposit/
    Initiate a crypto deposit (with optional screenshot upload).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CryptoDepositCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        crypto_currency = data["crypto_currency"]
        amount = data["amount"]
        exchange_rate = MOCK_EXCHANGE_RATES.get(crypto_currency, Decimal("1.00"))
        usd_amount = (amount * exchange_rate).quantize(Decimal("0.01"))

        wallet = CryptoWallet.objects.get(user=request.user)

        txn = CryptoTransaction.objects.create(
            wallet=wallet,
            transaction_type="deposit",
            crypto_currency=crypto_currency,
            amount=amount,
            usd_amount=usd_amount,
            exchange_rate=exchange_rate,
            status=CryptoTransactionStatus.PENDING,
            tx_hash=data.get("tx_hash", ""),
            payment_screenshot=data.get("payment_screenshot", None),
            wallet_address=data.get("wallet_address", ""),
        )

        logger.info(
            "Crypto deposit %s submitted by user %s: %s %s (%s USD)",
            txn.reference,
            request.user.email,
            amount,
            crypto_currency,
            usd_amount,
        )

        return Response(
            CryptoTransactionSerializer(txn).data,
            status=status.HTTP_201_CREATED,
        )


class CryptoTransactionListView(generics.ListAPIView):
    """
    GET /crypto/transactions/
    List the authenticated user's crypto transactions.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = CryptoTransactionSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["created_at", "amount"]
    ordering = ["-created_at"]

    def get_queryset(self):
        try:
            wallet = CryptoWallet.objects.get(user=self.request.user)
        except CryptoWallet.DoesNotExist:
            return CryptoTransaction.objects.none()

        qs = CryptoTransaction.objects.filter(wallet=wallet)

        txn_type = self.request.query_params.get("type")
        if txn_type:
            qs = qs.filter(transaction_type=txn_type)

        txn_status = self.request.query_params.get("status")
        if txn_status:
            qs = qs.filter(status=txn_status)

        return qs


@method_decorator(never_cache, name="dispatch")
class CryptoWithdrawalCreateView(APIView):
    """
    POST /crypto/withdraw/
    Initiate a crypto withdrawal from the user's bank account.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CryptoWithdrawalCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        crypto_currency = data["crypto_currency"]
        amount = data["amount"]
        destination_address = data["destination_address"]
        exchange_rate = MOCK_EXCHANGE_RATES.get(crypto_currency, Decimal("1.00"))
        usd_amount = (amount * exchange_rate).quantize(Decimal("0.01"))

        # Debit the first active, unfrozen bank account
        bank_account = BankAccount.objects.filter(
            user=request.user,
            is_active=True,
            is_frozen=False,
        ).first()

        if not bank_account:
            return Response(
                {"detail": "No active bank account found."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if bank_account.balance < usd_amount:
            return Response(
                {"detail": f"Insufficient balance. You need at least ${usd_amount} USD."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        bank_account.balance -= usd_amount
        bank_account.save(update_fields=["balance", "updated_at"])

        wallet, _ = CryptoWallet.objects.get_or_create(
            user=request.user,
            defaults={
                "wallet_address": generate_wallet_address(),
                "currency": "BTC",
                "balance": Decimal("0"),
            },
        )

        txn = CryptoTransaction.objects.create(
            wallet=wallet,
            transaction_type="withdrawal",
            crypto_currency=crypto_currency,
            amount=amount,
            usd_amount=usd_amount,
            exchange_rate=exchange_rate,
            status=CryptoTransactionStatus.PENDING,
            wallet_address=destination_address,
            metadata={"destination_address": destination_address},
        )

        logger.info(
            "Crypto withdrawal %s submitted by user %s: %s %s (%s USD) to %s",
            txn.reference,
            request.user.email,
            amount,
            crypto_currency,
            usd_amount,
            destination_address,
        )

        return Response(
            CryptoTransactionSerializer(txn).data,
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Admin views
# ---------------------------------------------------------------------------


class AdminCryptoTransactionListView(generics.ListAPIView):
    """
    GET /crypto/admin/
    Admin view: list all crypto transactions.
    """

    permission_classes = [IsAuthenticated, IsAdminRole]
    serializer_class = CryptoTransactionAdminSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["wallet__user__email", "reference", "tx_hash"]
    ordering_fields = ["created_at", "amount", "status"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = CryptoTransaction.objects.select_related("wallet", "wallet__user")

        txn_status = self.request.query_params.get("status")
        if txn_status:
            qs = qs.filter(status=txn_status)

        crypto_currency = self.request.query_params.get("currency")
        if crypto_currency:
            qs = qs.filter(crypto_currency=crypto_currency)

        return qs


@method_decorator(never_cache, name="dispatch")
class AdminProcessCryptoDepositView(APIView):
    """
    POST /crypto/admin/<pk>/process/
    Admin completes or rejects a crypto deposit (credits bank account on completion).
    """

    permission_classes = [IsAuthenticated, IsAdminRole]

    def post(self, request, pk):
        try:
            txn = CryptoTransaction.objects.select_related(
                "wallet", "wallet__user"
            ).get(pk=pk)
        except CryptoTransaction.DoesNotExist:
            return Response(
                {"detail": "Crypto transaction not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if txn.status != CryptoTransactionStatus.PENDING:
            return Response(
                {"detail": f"Transaction is already {txn.status}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = AdminProcessCryptoDepositSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        action = serializer.validated_data["action"]

        if action == "reject":
            txn.status = CryptoTransactionStatus.FAILED
            txn.metadata = {**txn.metadata, "rejection_reason": serializer.validated_data["rejection_reason"]}
            txn.save(update_fields=["status", "metadata", "updated_at"])

            logger.info(
                "Crypto deposit %s rejected by admin %s",
                txn.reference,
                request.user.email,
            )

            return Response(
                CryptoTransactionAdminSerializer(txn).data,
                status=status.HTTP_200_OK,
            )

        # Complete: credit the user's bank account
        txn.status = CryptoTransactionStatus.COMPLETED
        txn.save(update_fields=["status", "updated_at"])

        # Credit the first active bank account
        bank_account = BankAccount.objects.filter(
            user=txn.wallet.user,
            is_active=True,
            is_frozen=False,
        ).first()

        if bank_account:
            bank_account.balance += txn.usd_amount
            bank_account.save(update_fields=["balance", "updated_at"])
            logger.info(
                "Crypto deposit %s completed. %s USD credited to account %s.",
                txn.reference,
                txn.usd_amount,
                bank_account.account_number,
            )
        else:
            logger.warning(
                "Crypto deposit %s completed but user %s has no active bank account.",
                txn.reference,
                txn.wallet.user.email,
            )

        return Response(
            CryptoTransactionAdminSerializer(txn).data,
            status=status.HTTP_200_OK,
        )