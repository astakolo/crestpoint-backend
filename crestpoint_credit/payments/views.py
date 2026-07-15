import logging

from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import status, filters, generics
from rest_framework.permissions import IsAuthenticated, BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ReadOnlyModelViewSet

from crestpoint_credit.security.permissions import HasVerifiedKYC, IsAdminRole
from crestpoint_credit.core.exceptions import (
    InvalidTransferError,
    AccountLockedError,
)

from .models import Payment
from .serializers import (
    InitiatePaymentSerializer,
    PaymentSerializer,
    PaymentDetailSerializer,
    RefundSerializer,
)
from .services import initiate_payment, verify_payment, refund_payment

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------


class IsPaymentOwner(BasePermission):
    """Allow access only if the payment belongs to the requesting user."""

    def has_object_permission(self, request, view, obj):
        return obj.user_id == request.user.id


# ---------------------------------------------------------------------------
# Mixin for consistent error handling
# ---------------------------------------------------------------------------


class _PaymentOperationMixin:
    """Maps service-layer exceptions to appropriate HTTP responses."""

    _exception_map = {
        AccountLockedError: (
            "Account is locked or frozen.",
            status.HTTP_403_FORBIDDEN,
        ),
        InvalidTransferError: (
            "Invalid payment request.",
            status.HTTP_400_BAD_REQUEST,
        ),
    }

    def _handle_service_error(self, exc):
        for exc_class, (message, http_status) in self._exception_map.items():
            if isinstance(exc, exc_class):
                return Response(
                    {"detail": str(exc)},
                    status=http_status,
                )
        raise exc


# ---------------------------------------------------------------------------
# Initiate Payment
# ---------------------------------------------------------------------------


@method_decorator(never_cache, name="dispatch")
class InitiatePaymentView(APIView, _PaymentOperationMixin):
    """
    POST /payments/initiate/
    Start a new payment for the authenticated user.
    """

    permission_classes = [IsAuthenticated, HasVerifiedKYC]

    def post(self, request):
        serializer = InitiatePaymentSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        account = serializer._account
        amount = serializer.validated_data["amount"]
        payment_method = serializer.validated_data["payment_method"]
        provider = serializer.validated_data.get(
            "provider", "bank_mock"
        )
        metadata = serializer.validated_data.get("metadata", {})

        try:
            payment = initiate_payment(
                user=request.user,
                account=account,
                amount=amount,
                payment_method=payment_method,
                provider=provider,
                metadata=metadata,
            )
        except Exception as exc:
            return self._handle_service_error(exc)

        return Response(
            PaymentSerializer(payment).data,
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Payment List
# ---------------------------------------------------------------------------


class PaymentListView(generics.ListAPIView):
    """
    GET /payments/
    Paginated list of the authenticated user's payments.
    Supports filtering by status, payment_method, and date range.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = PaymentSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["created_at", "amount"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = Payment.objects.filter(user=self.request.user)

        # Filter by status
        payment_status = self.request.query_params.get("status")
        if payment_status:
            qs = qs.filter(status=payment_status)

        # Filter by payment method
        method = self.request.query_params.get("payment_method")
        if method:
            qs = qs.filter(payment_method=method)

        # Filter by date range
        from_date = self.request.query_params.get("from_date")
        if from_date:
            qs = qs.filter(created_at__date__gte=from_date)

        to_date = self.request.query_params.get("to_date")
        if to_date:
            qs = qs.filter(created_at__date__lte=to_date)

        return qs


# ---------------------------------------------------------------------------
# Payment Detail
# ---------------------------------------------------------------------------


class PaymentDetailView(generics.RetrieveAPIView):
    """
    GET /payments/<pk>/
    Retrieve a single payment (own payments only).
    """

    permission_classes = [IsAuthenticated, IsPaymentOwner]
    serializer_class = PaymentDetailSerializer

    def get_queryset(self):
        return Payment.objects.filter(user=self.request.user)


# ---------------------------------------------------------------------------
# Verify Payment
# ---------------------------------------------------------------------------


@method_decorator(never_cache, name="dispatch")
class VerifyPaymentView(APIView, _PaymentOperationMixin):
    """
    POST /payments/<pk>/verify/
    Verify a payment with its provider.
    """

    permission_classes = [IsAuthenticated, IsPaymentOwner]

    def post(self, request, pk):
        try:
            payment = Payment.objects.get(pk=pk)
        except Payment.DoesNotExist:
            return Response(
                {"detail": "Payment not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Ensure the user owns this payment
        if payment.user_id != request.user.id:
            return Response(
                {"detail": "Permission denied."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            payment = verify_payment(pk)
        except Exception as exc:
            return self._handle_service_error(exc)

        return Response(
            PaymentDetailSerializer(payment).data,
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Refund Payment (admin only)
# ---------------------------------------------------------------------------


@method_decorator(never_cache, name="dispatch")
class RefundPaymentView(APIView, _PaymentOperationMixin):
    """
    POST /payments/<pk>/refund/
    Refund a completed payment. Admin only.
    """

    permission_classes = [IsAuthenticated, IsAdminRole]

    def post(self, request, pk):
        serializer = RefundSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data.get("reason", "")

        try:
            payment = refund_payment(pk, reason=reason)
        except Exception as exc:
            return self._handle_service_error(exc)

        return Response(
            PaymentDetailSerializer(payment).data,
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Admin Payment ViewSet
# ---------------------------------------------------------------------------


class AdminPaymentViewSet(ReadOnlyModelViewSet):
    """
    GET /payments/admin/
    Full read access to all payments for admin users.
    Supports filtering by user, status, provider, and method.
    """

    permission_classes = [IsAuthenticated, IsAdminRole]
    serializer_class = PaymentDetailSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["reference", "user__email"]
    ordering_fields = ["created_at", "amount"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = Payment.objects.select_related("user", "account")

        # Filter by user
        user_id = self.request.query_params.get("user")
        if user_id:
            qs = qs.filter(user_id=user_id)

        # Filter by status
        payment_status = self.request.query_params.get("status")
        if payment_status:
            qs = qs.filter(status=payment_status)

        # Filter by provider
        provider = self.request.query_params.get("provider")
        if provider:
            qs = qs.filter(provider=provider)

        # Filter by payment method
        method = self.request.query_params.get("payment_method")
        if method:
            qs = qs.filter(payment_method=method)

        # Filter by date range
        from_date = self.request.query_params.get("from_date")
        if from_date:
            qs = qs.filter(created_at__date__gte=from_date)

        to_date = self.request.query_params.get("to_date")
        if to_date:
            qs = qs.filter(created_at__date__lte=to_date)

        return qs
