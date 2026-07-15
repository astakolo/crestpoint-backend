import logging

from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import status, generics, filters
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from crestpoint_credit.security.permissions import IsAdminRole
from .models import (
    BillerCategory,
    Biller,
    BillerSaved,
    BillPayment,
)
from .serializers import (
    BillerCategorySerializer,
    BillerSerializer,
    BillerSavedSerializer,
    SaveBillerSerializer,
    PayBillSerializer,
    BillPaymentSerializer,
    BillPaymentDetailSerializer,
    BillPaymentAdminSerializer,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Biller catalog views
# ---------------------------------------------------------------------------


class BillerCategoryListView(generics.ListAPIView):
    """
    GET /bills/categories/
    List all active biller categories.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = BillerCategorySerializer
    queryset = BillerCategory.objects.filter(is_active=True)


class BillerListView(generics.ListAPIView):
    """
    GET /bills/billers/
    List all active billers (optional category filter).
    """

    permission_classes = [IsAuthenticated]
    serializer_class = BillerSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ["name", "biller_code"]

    def get_queryset(self):
        qs = Biller.objects.filter(is_active=True).select_related("category")

        category_id = self.request.query_params.get("category")
        if category_id:
            qs = qs.filter(category_id=category_id)

        return qs


# ---------------------------------------------------------------------------
# Saved billers views
# ---------------------------------------------------------------------------


class SavedBillersListView(generics.ListAPIView):
    """
    GET /bills/saved/
    List the authenticated user's saved billers.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = BillerSavedSerializer
    ordering = ["-created_at"]

    def get_queryset(self):
        return BillerSaved.objects.filter(
            user=self.request.user
        ).select_related("biller", "biller__category")


@method_decorator(never_cache, name="dispatch")
class SaveBillerView(APIView):
    """
    POST /bills/saved/
    Save a biller for quick future payments.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = SaveBillerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        biller = serializer._biller
        data = serializer.validated_data

        saved, created = BillerSaved.objects.update_or_create(
            user=request.user,
            biller=biller,
            defaults={
                "nickname": data.get("nickname", ""),
                "account_number": data["account_number"],
            },
        )

        http_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(
            BillerSavedSerializer(saved).data,
            status=http_status,
        )


@method_decorator(never_cache, name="dispatch")
class DeleteSavedBillerView(APIView):
    """
    DELETE /bills/saved/<pk>/
    Remove a saved biller.
    """

    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        try:
            saved = BillerSaved.objects.select_related("biller").get(pk=pk)
        except BillerSaved.DoesNotExist:
            return Response(
                {"detail": "Saved biller not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if saved.user_id != request.user.id:
            return Response(
                {"detail": "This saved biller does not belong to you."},
                status=status.HTTP_403_FORBIDDEN,
            )

        saved.delete()
        return Response(
            {"message": "Biller removed from saved list."},
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Bill payment views
# ---------------------------------------------------------------------------


@method_decorator(never_cache, name="dispatch")
class PayBillView(APIView):
    """
    POST /bills/pay/
    Pay a bill (debits bank account).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PayBillSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        biller = serializer._biller
        account = serializer._account
        data = serializer.validated_data
        amount = data["amount"]

        # Debit bank account
        account.balance -= amount
        account.save(update_fields=["balance", "updated_at"])

        # Create bill payment record
        payment = BillPayment.objects.create(
            user=request.user,
            account=account,
            biller=biller,
            amount=amount,
            status="completed",
            narration=data.get("narration", ""),
        )

        logger.info(
            "Bill payment %s of %s to %s by user %s",
            payment.reference,
            amount,
            biller.name,
            request.user.email,
        )

        return Response(
            BillPaymentSerializer(payment).data,
            status=status.HTTP_201_CREATED,
        )


class BillPaymentListView(generics.ListAPIView):
    """
    GET /bills/payments/
    List the authenticated user's bill payment history.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = BillPaymentSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["reference", "narration", "biller__name"]
    ordering_fields = ["created_at", "amount"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return BillPayment.objects.filter(
            user=self.request.user
        ).select_related("biller", "account")


class BillPaymentDetailView(generics.RetrieveAPIView):
    """
    GET /bills/payments/<pk>/
    Retrieve a single bill payment (own payments only).
    """

    permission_classes = [IsAuthenticated]
    serializer_class = BillPaymentDetailSerializer

    def get_queryset(self):
        return BillPayment.objects.filter(
            user=self.request.user
        ).select_related("biller", "account")


# ---------------------------------------------------------------------------
# Admin views
# ---------------------------------------------------------------------------


class AdminBillPaymentListView(generics.ListAPIView):
    """
    GET /bills/admin/
    Admin view: list all bill payments.
    """

    permission_classes = [IsAuthenticated, IsAdminRole]
    serializer_class = BillPaymentAdminSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["user__email", "reference", "biller__name"]
    ordering_fields = ["created_at", "amount", "status"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = BillPayment.objects.select_related("user", "account", "biller")

        pay_status = self.request.query_params.get("status")
        if pay_status:
            qs = qs.filter(status=pay_status)

        user_id = self.request.query_params.get("user")
        if user_id:
            qs = qs.filter(user_id=user_id)

        return qs