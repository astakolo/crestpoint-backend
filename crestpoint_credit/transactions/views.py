import logging

from django.http import Http404
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status, filters, generics
from rest_framework.permissions import IsAuthenticated, BasePermission

from crestpoint_credit.security.permissions import HasVerifiedKYC, IsAdminRole
from crestpoint_credit.security.throttling import TransferRateThrottle, TransactionRateThrottle
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ReadOnlyModelViewSet

from crestpoint_credit.accounts.models import BankAccount
from crestpoint_credit.core.exceptions import (
    InsufficientFundsError,
    AccountLockedError,
    DailyLimitExceededError,
    TransferLimitExceededError,
    InvalidTransferError,
)
from .models import Transaction
from .serializers import (
    DepositSerializer,
    WithdrawalSerializer,
    TransferSerializer,
    TransactionSerializer,
    TransactionDetailSerializer,
)
from .services import (
    execute_deposit,
    execute_withdrawal,
    execute_transfer,
    get_transaction_history,
    reverse_transaction,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Permissions (string-referenced where possible)
# ---------------------------------------------------------------------------

class IsOwner(BasePermission):
    """Allow access only if the transaction's account belongs to the user."""

    def has_object_permission(self, request, view, obj):
        return obj.account.user_id == request.user.id


# ---------------------------------------------------------------------------
# Mixin for consistent error handling in operation views
# ---------------------------------------------------------------------------

class _OperationViewMixin:
    """
    Provides a standard error-to-HTTP-status mapping for service-layer
    exceptions so that each operation view stays lean.
    """

    _exception_map = {
        InsufficientFundsError: (
            "Insufficient funds.",
            status.HTTP_400_BAD_REQUEST,
        ),
        AccountLockedError: (
            "Account is locked or frozen.",
            status.HTTP_403_FORBIDDEN,
        ),
        DailyLimitExceededError: (
            "Daily transaction limit exceeded.",
            status.HTTP_429_TOO_MANY_REQUESTS,
        ),
        TransferLimitExceededError: (
            "Single transfer limit exceeded.",
            status.HTTP_400_BAD_REQUEST,
        ),
        InvalidTransferError: (
            "Invalid transfer request.",
            status.HTTP_400_BAD_REQUEST,
        ),
    }

    def _handle_service_error(self, exc):
        """Return the appropriate Response for a known service exception."""
        for exc_class, (message, http_status) in self._exception_map.items():
            if isinstance(exc, exc_class):
                return Response(
                    {"detail": str(exc)},
                    status=http_status,
                )
        # Unexpected exception – re-raise so DRF's default handler catches it
        raise exc


# ---------------------------------------------------------------------------
# Operation views
# ---------------------------------------------------------------------------

@method_decorator(never_cache, name="dispatch")
class DepositView(APIView, _OperationViewMixin):
    """
    POST /transactions/deposit/
    Create a deposit for the authenticated user's bank account.
    """

    permission_classes = [IsAuthenticated, HasVerifiedKYC]
    throttle_classes = [TransactionRateThrottle]

    def post(self, request):
        serializer = DepositSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        account = serializer._account
        amount = serializer.validated_data["amount"]
        description = serializer.validated_data.get("description", "")

        try:
            txn = execute_deposit(account, amount, description)
        except Exception as exc:
            return self._handle_service_error(exc)

        return Response(
            TransactionSerializer(txn).data,
            status=status.HTTP_201_CREATED,
        )


@method_decorator(never_cache, name="dispatch")
class WithdrawalView(APIView, _OperationViewMixin):
    """
    POST /transactions/withdraw/
    Create a withdrawal for the authenticated user's bank account.
    """

    permission_classes = [IsAuthenticated, HasVerifiedKYC]
    throttle_classes = [TransactionRateThrottle]

    def post(self, request):
        serializer = WithdrawalSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        account = serializer._account
        amount = serializer.validated_data["amount"]
        description = serializer.validated_data.get("description", "")

        try:
            txn = execute_withdrawal(account, amount, description)
        except Exception as exc:
            return self._handle_service_error(exc)

        return Response(
            TransactionSerializer(txn).data,
            status=status.HTTP_201_CREATED,
        )


@method_decorator(never_cache, name="dispatch")
class TransferView(APIView, _OperationViewMixin):
    """
    POST /transactions/transfer/
    Transfer funds between two bank accounts.
    """

    permission_classes = [IsAuthenticated, HasVerifiedKYC]
    throttle_classes = [TransferRateThrottle]

    def post(self, request):
        serializer = TransferSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        sender_account = serializer._sender_account
        recipient_account_number = serializer.validated_data["recipient_account_number"]
        amount = serializer.validated_data["amount"]
        description = serializer.validated_data.get("description", "")

        try:
            sender_txn, recipient_txn = execute_transfer(
                sender_account, recipient_account_number, amount, description
            )
        except Exception as exc:
            return self._handle_service_error(exc)

        return Response(
            {
                "sender_transaction": TransactionSerializer(sender_txn).data,
                "recipient_transaction": TransactionDetailSerializer(recipient_txn).data,
            },
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# History / detail views
# ---------------------------------------------------------------------------

class TransactionHistoryView(generics.ListAPIView):
    """
    GET /transactions/history/
    Paginated transaction history for the authenticated user's accounts.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = TransactionSerializer
    filter_backends = [
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    search_fields = ["reference", "description"]
    ordering_fields = ["created_at", "amount"]
    ordering = ["-created_at"]

    def get_queryset(self):
        user = self.request.user
        # Only transactions for accounts owned by this user
        account_ids = BankAccount.objects.filter(user=user).values_list(
            "id", flat=True
        )
        qs = Transaction.objects.filter(account_id__in=account_ids)

        # Filter params
        account_id = self.request.query_params.get("account_id")
        if account_id:
            qs = qs.filter(account_id=account_id)

        txn_type = self.request.query_params.get("transaction_type")
        if txn_type:
            qs = qs.filter(transaction_type=txn_type)

        txn_status = self.request.query_params.get("status")
        if txn_status:
            qs = qs.filter(status=txn_status)

        from_date = self.request.query_params.get("from_date")
        if from_date:
            qs = qs.filter(created_at__date__gte=from_date)

        to_date = self.request.query_params.get("to_date")
        if to_date:
            qs = qs.filter(created_at__date__lte=to_date)

        min_amount = self.request.query_params.get("min_amount")
        if min_amount:
            qs = qs.filter(amount__gte=min_amount)

        max_amount = self.request.query_params.get("max_amount")
        if max_amount:
            qs = qs.filter(amount__lte=max_amount)

        return qs


class TransactionDetailView(generics.RetrieveAPIView):
    """
    GET /transactions/<pk>/
    Retrieve a single transaction (own transactions only).
    """

    permission_classes = [IsAuthenticated, IsOwner]
    serializer_class = TransactionDetailSerializer

    def get_queryset(self):
        user = self.request.user
        account_ids = BankAccount.objects.filter(user=user).values_list(
            "id", flat=True
        )
        return Transaction.objects.filter(account_id__in=account_ids)


# ---------------------------------------------------------------------------
# Admin views
# ---------------------------------------------------------------------------

class AdminTransactionViewSet(ReadOnlyModelViewSet):
    """
    GET /transactions/admin/
    Admin read-only access to all transactions.
    """

    permission_classes = [IsAuthenticated, IsAdminRole]
    serializer_class = TransactionDetailSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["reference", "description"]
    ordering_fields = ["created_at", "amount"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = Transaction.objects.select_related("account", "recipient_account")

        # Filter params
        user_id = self.request.query_params.get("user")
        if user_id:
            qs = qs.filter(account__user_id=user_id)

        account_id = self.request.query_params.get("account")
        if account_id:
            qs = qs.filter(account_id=account_id)

        txn_type = self.request.query_params.get("type")
        if txn_type:
            qs = qs.filter(transaction_type=txn_type)

        txn_status = self.request.query_params.get("status")
        if txn_status:
            qs = qs.filter(status=txn_status)

        flagged = self.request.query_params.get("flagged")
        if flagged is not None:
            qs = qs.filter(is_flagged=flagged.lower() in ("true", "1", "yes"))

        from_date = self.request.query_params.get("from_date")
        if from_date:
            qs = qs.filter(created_at__date__gte=from_date)

        to_date = self.request.query_params.get("to_date")
        if to_date:
            qs = qs.filter(created_at__date__lte=to_date)

        return qs


class FlagTransactionView(APIView):
    """
    POST /transactions/<pk>/flag/
    Admin/support endpoint to flag a transaction for review.
    """

    permission_classes = [IsAuthenticated, IsAdminRole]

    def post(self, request, pk):
        try:
            txn = Transaction.objects.get(pk=pk)
        except Transaction.DoesNotExist:
            return Response(
                {"detail": "Transaction not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        reason = request.data.get("reason", "")
        txn.is_flagged = True
        txn.flag_reason = reason
        txn.save(update_fields=["is_flagged", "flag_reason", "updated_at"])

        return Response(
            TransactionDetailSerializer(txn).data,
            status=status.HTTP_200_OK,
        )


class UnflagTransactionView(APIView):
    """
    POST /transactions/<pk>/unflag/
    Admin endpoint to remove a flag from a transaction.
    """

    permission_classes = [IsAuthenticated, IsAdminRole]

    def post(self, request, pk):
        try:
            txn = Transaction.objects.get(pk=pk)
        except Transaction.DoesNotExist:
            return Response(
                {"detail": "Transaction not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        txn.is_flagged = False
        txn.flag_reason = ""
        txn.save(update_fields=["is_flagged", "flag_reason", "updated_at"])

        return Response(
            {"message": "Transaction unflagged successfully."},
            status=status.HTTP_200_OK,
        )


class ReverseTransactionView(APIView, _OperationViewMixin):
    """
    POST /transactions/<pk>/reverse/
    Admin endpoint to reverse a completed transaction.
    """

    permission_classes = [IsAuthenticated, IsAdminRole]

    def post(self, request, pk):
        reason = request.data.get("reason", "Admin-initiated reversal.")
        try:
            txn = Transaction.objects.get(pk=pk)
        except Transaction.DoesNotExist:
            return Response(
                {"detail": "Transaction not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            reversed_txn = reverse_transaction(txn, reason)
        except Exception as exc:
            return self._handle_service_error(exc)

        logger.info(
            "Transaction %s reversed by admin %s",
            txn.reference,
            request.user.email,
        )

        return Response(
            {
                "message": f"Transaction {txn.reference} reversed successfully.",
                "original_status": reversed_txn.status,
            },
            status=status.HTTP_200_OK,
        )


class AdminTransactionStatsView(APIView):
    """
    GET /transactions/admin/stats/
    Returns aggregated stats for the admin dashboard.
    """

    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        from django.db.models import Sum, Count, Q, F
        from crestpoint_credit.accounts.models import BankAccount

        from datetime import timedelta
        from django.utils import timezone

        today = timezone.now().date()

        # Total platform balance
        total_balance = BankAccount.objects.filter(
            is_active=True
        ).aggregate(total=Sum("balance"))["total"] or 0

        # Active accounts count
        active_accounts = BankAccount.objects.filter(
            is_active=True
        ).count()

        # Today's transactions volume and count
        today_txns = Transaction.objects.filter(
            created_at__date=today,
            status="completed",
        )
        today_volume = today_txns.aggregate(vol=Sum("amount"))["vol"] or 0
        today_count = today_txns.count()

        # Flagged count
        flagged_count = Transaction.objects.filter(is_flagged=True).count()

        # Failed count
        failed_count = Transaction.objects.filter(status="failed").count()

        # Pending count
        pending_count = Transaction.objects.filter(status="pending").count()

        # Frozen accounts count
        frozen_count = BankAccount.objects.filter(is_frozen=True).count()

        return Response({
            "total_balance": str(total_balance),
            "active_accounts": active_accounts,
            "today_volume": str(today_volume),
            "today_transaction_count": today_count,
            "flagged_count": flagged_count,
            "failed_count": failed_count,
            "pending_count": pending_count,
            "frozen_accounts": frozen_count,
        })


class AdminCSVExportView(APIView):
    """
    GET /transactions/admin/export-csv/
    Export filtered transactions as CSV. Returns the file as a download.
    """

    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        import csv
        import io

        from django.http import HttpResponse

        qs = Transaction.objects.select_related("account", "account__user", "recipient_account")

        # Apply same filters as AdminTransactionViewSet
        user_id = request.query_params.get("user")
        if user_id:
            qs = qs.filter(account__user_id=user_id)
        account_id = request.query_params.get("account")
        if account_id:
            qs = qs.filter(account_id=account_id)
        txn_type = request.query_params.get("type")
        if txn_type:
            qs = qs.filter(transaction_type=txn_type)
        txn_status = request.query_params.get("status")
        if txn_status:
            qs = qs.filter(status=txn_status)
        flagged = request.query_params.get("flagged")
        if flagged is not None:
            qs = qs.filter(is_flagged=flagged.lower() in ("true", "1", "yes"))
        from_date = request.query_params.get("from_date")
        if from_date:
            qs = qs.filter(created_at__date__gte=from_date)
        to_date = request.query_params.get("to_date")
        if to_date:
            qs = qs.filter(created_at__date__lte=to_date)

        # Limit export to 10000 rows
        qs = qs.order_by("-created_at")[:10000]

        # Build CSV
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "ID", "Reference", "Type", "Status", "Account Number",
            "User Email", "Amount", "Balance Before", "Balance After",
            "Description", "Flagged", "Flag Reason", "Created At",
        ])
        for txn in qs:
            writer.writerow([
                txn.id,
                txn.reference,
                txn.transaction_type,
                txn.status,
                txn.account.account_number,
                txn.account.user.email if txn.account.user else "",
                str(txn.amount),
                str(txn.balance_before),
                str(txn.balance_after),
                txn.description,
                txn.is_flagged,
                txn.flag_reason,
                txn.created_at.isoformat() if txn.created_at else "",
        ])

        response = HttpResponse(
            output.getvalue(),
            content_type="text/csv",
        )
        response["Content-Disposition"] = 'attachment; filename="transactions_export.csv"'
        return response
