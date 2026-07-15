import logging
from decimal import Decimal

from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import status, generics, filters
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from crestpoint_credit.security.permissions import IsAdminRole
from .models import (
    VirtualCard,
    CardTransaction,
    CardFunding,
    CardStatus,
    generate_card_number,
    generate_cvv,
    generate_expiry,
)
from .serializers import (
    VirtualCardSerializer,
    VirtualCardDetailSerializer,
    CardCreateSerializer,
    CardFreezeSerializer,
    CardFundSerializer,
    CardTransactionSerializer,
    VirtualCardAdminSerializer,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# User-facing views
# ---------------------------------------------------------------------------


class CardListView(generics.ListAPIView):
    """
    GET /cards/
    List the authenticated user's virtual cards.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = VirtualCardSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["created_at", "balance"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return VirtualCard.objects.filter(
            user=self.request.user
        ).select_related("account")


@method_decorator(never_cache, name="dispatch")
class CardCreateView(APIView):
    """
    POST /cards/
    Create a new virtual card.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CardCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        account = serializer._account
        data = serializer.validated_data

        brand = data.get("brand", "visa")
        expiry_month, expiry_year = generate_expiry()

        cardholder_name = data.get("cardholder_name", "")
        if not cardholder_name:
            cardholder_name = f"{request.user.first_name} {request.user.last_name}".strip()

        card = VirtualCard.objects.create(
            user=request.user,
            account=account,
            card_number=generate_card_number(brand),
            cardholder_name=cardholder_name,
            expiry_month=expiry_month,
            expiry_year=expiry_year,
            cvv=generate_cvv(),
            card_type=data.get("card_type", "virtual"),
            brand=brand,
            spending_limit=data.get("spending_limit", Decimal("5000.00")),
        )

        logger.info(
            "Virtual card ****%s created for user %s",
            card.card_number[-4:],
            request.user.email,
        )

        return Response(
            VirtualCardDetailSerializer(card).data,
            status=status.HTTP_201_CREATED,
        )


class CardDetailView(generics.RetrieveAPIView):
    """
    GET /cards/<pk>/
    Retrieve a single card detail (includes full number, CVV).
    """

    permission_classes = [IsAuthenticated]
    serializer_class = VirtualCardDetailSerializer

    def get_queryset(self):
        return VirtualCard.objects.filter(
            user=self.request.user
        ).select_related("account")


@method_decorator(never_cache, name="dispatch")
class CardFreezeView(APIView):
    """
    POST /cards/<pk>/freeze/
    Freeze or unfreeze a virtual card.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            card = VirtualCard.objects.get(pk=pk)
        except VirtualCard.DoesNotExist:
            return Response(
                {"detail": "Card not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if card.user_id != request.user.id:
            return Response(
                {"detail": "This card does not belong to you."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = CardFreezeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        action = serializer.validated_data["action"]

        if action == "freeze":
            if card.status != CardStatus.ACTIVE:
                return Response(
                    {"detail": f"Card cannot be frozen. Current status: {card.status}."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            card.status = CardStatus.FROZEN
            logger.info("Card ****%s frozen by user %s", card.card_number[-4:], request.user.email)
        else:
            if card.status != CardStatus.FROZEN:
                return Response(
                    {"detail": f"Card cannot be unfrozen. Current status: {card.status}."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            card.status = CardStatus.ACTIVE
            logger.info("Card ****%s unfrozen by user %s", card.card_number[-4:], request.user.email)

        card.save(update_fields=["status", "updated_at"])

        return Response(
            VirtualCardSerializer(card).data,
            status=status.HTTP_200_OK,
        )


@method_decorator(never_cache, name="dispatch")
class CardFundView(APIView):
    """
    POST /cards/<pk>/fund/
    Add funds to a virtual card from a bank account.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            card = VirtualCard.objects.select_related("account").get(pk=pk)
        except VirtualCard.DoesNotExist:
            return Response(
                {"detail": "Card not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if card.user_id != request.user.id:
            return Response(
                {"detail": "This card does not belong to you."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if card.status != CardStatus.ACTIVE:
            return Response(
                {"detail": "This card is not active."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = CardFundSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        account = serializer._account
        amount = serializer.validated_data["amount"]

        # Check spending limit
        new_balance = card.balance + amount
        if new_balance > card.spending_limit:
            return Response(
                {"detail": f"Funding would exceed the card's spending limit of {card.spending_limit}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Debit bank account
        account.balance -= amount
        account.save(update_fields=["balance", "updated_at"])

        # Credit card
        card.balance = new_balance
        card.save(update_fields=["balance", "updated_at"])

        # Create funding record
        funding = CardFunding.objects.create(
            card=card,
            account=account,
            amount=amount,
            status="completed",
        )

        logger.info(
            "Card ****%s funded with %s from account %s by user %s",
            card.card_number[-4:],
            amount,
            account.account_number,
            request.user.email,
        )

        return Response(
            {
                "funding": {
                    "reference": funding.reference,
                    "amount": str(funding.amount),
                    "status": funding.status,
                },
                "card": VirtualCardSerializer(card).data,
            },
            status=status.HTTP_201_CREATED,
        )


class CardTransactionListView(generics.ListAPIView):
    """
    GET /cards/<pk>/transactions/
    List a card's transactions.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = CardTransactionSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["created_at", "amount"]
    ordering = ["-created_at"]

    def get_queryset(self):
        card_id = self.kwargs["pk"]
        try:
            card = VirtualCard.objects.get(pk=card_id, user=self.request.user)
        except VirtualCard.DoesNotExist:
            return CardTransaction.objects.none()
        return CardTransaction.objects.filter(card=card)


# ---------------------------------------------------------------------------
# Admin views
# ---------------------------------------------------------------------------


class AdminCardListView(generics.ListAPIView):
    """
    GET /cards/admin/
    Admin view: list all virtual cards.
    """

    permission_classes = [IsAuthenticated, IsAdminRole]
    serializer_class = VirtualCardAdminSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["user__email", "card_number", "cardholder_name"]
    ordering_fields = ["created_at", "balance", "status"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = VirtualCard.objects.select_related("user", "account")

        card_status = self.request.query_params.get("status")
        if card_status:
            qs = qs.filter(status=card_status)

        brand = self.request.query_params.get("brand")
        if brand:
            qs = qs.filter(brand=brand)

        return qs