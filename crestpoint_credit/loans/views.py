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
    LoanType,
    LoanApplication,
    LoanApplicationStatus,
    Loan,
    LoanStatus,
    LoanRepayment,
)
from .serializers import (
    LoanTypeSerializer,
    LoanApplicationCreateSerializer,
    LoanApplicationSerializer,
    LoanApplicationAdminSerializer,
    AdminReviewLoanApplicationSerializer,
    LoanSerializer,
    LoanDetailSerializer,
    LoanAdminSerializer,
    LoanRepaymentSerializer,
    LoanRepaymentCreateSerializer,
)
from crestpoint_credit.core.utils import generate_transaction_ref

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public / Authenticated views
# ---------------------------------------------------------------------------


class LoanTypesListView(generics.ListAPIView):
    """
    GET /loans/types/
    List all active loan types.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = LoanTypeSerializer
    queryset = LoanType.objects.filter(is_active=True)


@method_decorator(never_cache, name="dispatch")
class LoanApplicationCreateView(APIView):
    """
    POST /loans/apply/
    Authenticated user submits a loan application.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = LoanApplicationCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        loan_type = serializer._loan_type
        data = serializer.validated_data

        application = LoanApplication.objects.create(
            user=request.user,
            loan_type=loan_type,
            amount_requested=data["amount_requested"],
            purpose=data.get("purpose", ""),
            employment_status=data.get("employment_status", ""),
            monthly_income=data.get("monthly_income"),
            term_months=data["term_months"],
        )

        logger.info(
            "Loan application %d submitted by user %s for %s",
            application.id,
            request.user.email,
            data["amount_requested"],
        )

        return Response(
            LoanApplicationSerializer(application).data,
            status=status.HTTP_201_CREATED,
        )


class LoanApplicationListView(generics.ListAPIView):
    """
    GET /loans/applications/
    List the authenticated user's own loan applications.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = LoanApplicationSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["purpose"]
    ordering_fields = ["created_at", "amount_requested"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return LoanApplication.objects.filter(
            user=self.request.user
        ).select_related("loan_type")


class LoanApplicationDetailView(generics.RetrieveAPIView):
    """
    GET /loans/applications/<pk>/
    Retrieve a single loan application (own applications only).
    """

    permission_classes = [IsAuthenticated]
    serializer_class = LoanApplicationSerializer

    def get_queryset(self):
        return LoanApplication.objects.filter(
            user=self.request.user
        ).select_related("loan_type")


class LoanListView(generics.ListAPIView):
    """
    GET /loans/
    List the authenticated user's active loans.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = LoanSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["created_at", "outstanding_balance"]
    ordering = ["-created_at"]

    def get_queryset(self):
        application_ids = LoanApplication.objects.filter(
            user=self.request.user
        ).values_list("id", flat=True)
        return Loan.objects.filter(
            loan_application_id__in=application_ids
        ).select_related("loan_application__loan_type", "account")


class LoanDetailView(generics.RetrieveAPIView):
    """
    GET /loans/<pk>/
    Retrieve a single loan with repayment schedule (own loans only).
    """

    permission_classes = [IsAuthenticated]
    serializer_class = LoanDetailSerializer

    def get_queryset(self):
        application_ids = LoanApplication.objects.filter(
            user=self.request.user
        ).values_list("id", flat=True)
        return Loan.objects.filter(
            loan_application_id__in=application_ids
        ).select_related("loan_application__loan_type", "account")


@method_decorator(never_cache, name="dispatch")
class LoanRepaymentCreateView(APIView):
    """
    POST /loans/<pk>/repay/
    Make a repayment on a loan (debits bank account).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        serializer = LoanRepaymentCreateSerializer(
            data=request.data, context={"request": request}
        )
        # Override loan_id from URL
        initial_data = request.data.copy()
        initial_data["loan_id"] = pk
        serializer = LoanRepaymentCreateSerializer(
            data=initial_data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        loan = serializer._loan
        amount = serializer.validated_data["amount"]
        account = loan.account

        if account.balance < amount:
            return Response(
                {"detail": "Insufficient funds in your bank account."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Calculate interest and principal portions
        monthly_rate = loan.interest_rate / Decimal("100") / Decimal("12")
        interest_portion = (loan.outstanding_balance * monthly_rate).quantize(
            Decimal("0.01")
        )
        if interest_portion > amount:
            interest_portion = amount
        principal_portion = (amount - interest_portion).quantize(Decimal("0.01"))

        # Debit bank account
        balance_before = account.balance
        account.balance -= amount
        account.save(update_fields=["balance", "updated_at"])

        # Update loan balance
        loan.outstanding_balance -= principal_portion
        if loan.outstanding_balance <= 0:
            loan.outstanding_balance = Decimal("0.00")
            loan.status = LoanStatus.PAID_OFF
        loan.save(update_fields=["outstanding_balance", "status", "updated_at"])

        # Create repayment record
        repayment = LoanRepayment.objects.create(
            loan=loan,
            amount=amount,
            principal_portion=principal_portion,
            interest_portion=interest_portion,
            status="completed",
        )

        logger.info(
            "Loan repayment %s of %s for loan %d by user %s",
            repayment.reference,
            amount,
            loan.id,
            request.user.email,
        )

        return Response(
            LoanRepaymentSerializer(repayment).data,
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Admin views
# ---------------------------------------------------------------------------


class AdminLoanApplicationListView(generics.ListAPIView):
    """
    GET /loans/admin/applications/
    Admin view: list all loan applications.
    """

    permission_classes = [IsAuthenticated, IsAdminRole]
    serializer_class = LoanApplicationAdminSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["user__email", "purpose"]
    ordering_fields = ["created_at", "amount_requested", "status"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = LoanApplication.objects.select_related("user", "loan_type", "reviewed_by")

        app_status = self.request.query_params.get("status")
        if app_status:
            qs = qs.filter(status=app_status)

        return qs


@method_decorator(never_cache, name="dispatch")
class AdminReviewLoanApplicationView(APIView):
    """
    POST /loans/admin/applications/<pk>/review/
    Admin approves or rejects a loan application.
    """

    permission_classes = [IsAuthenticated, IsAdminRole]

    def post(self, request, pk):
        try:
            application = LoanApplication.objects.select_related("user", "loan_type").get(pk=pk)
        except LoanApplication.DoesNotExist:
            return Response(
                {"detail": "Loan application not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if application.status != LoanApplicationStatus.PENDING:
            return Response(
                {"detail": f"Application is already {application.status}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = AdminReviewLoanApplicationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        action = serializer.validated_data["action"]

        if action == "reject":
            application.status = LoanApplicationStatus.REJECTED
            application.rejection_reason = serializer.validated_data["rejection_reason"]
            application.reviewed_by = request.user
            application.reviewed_at = timezone.now()
            application.save(
                update_fields=["status", "rejection_reason", "reviewed_by", "reviewed_at", "updated_at"]
            )

            logger.info(
                "Loan application %d rejected by admin %s",
                application.id,
                request.user.email,
            )

            return Response(
                LoanApplicationAdminSerializer(application).data,
                status=status.HTTP_200_OK,
            )

        # Approve
        account_id = serializer.validated_data["account_id"]
        try:
            account = BankAccount.objects.get(pk=account_id)
        except BankAccount.DoesNotExist:
            return Response(
                {"detail": "Bank account not found."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if account.user_id != application.user_id:
            return Response(
                {"detail": "This bank account does not belong to the applicant."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        application.status = LoanApplicationStatus.APPROVED
        application.reviewed_by = request.user
        application.reviewed_at = timezone.now()
        application.save(
            update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"]
        )

        # Create the Loan
        loan = Loan.objects.create(
            loan_application=application,
            account=account,
            principal=application.amount_requested,
            interest_rate=application.loan_type.interest_rate,
            term_months=application.term_months,
            outstanding_balance=application.amount_requested,
            status=LoanStatus.ACTIVE,
            disbursement_date=timezone.now(),
        )

        # Credit the bank account
        account.balance += application.amount_requested
        account.save(update_fields=["balance", "updated_at"])

        application.status = LoanApplicationStatus.DISBURSED
        application.save(update_fields=["status", "updated_at"])

        logger.info(
            "Loan application %d approved and disbursed by admin %s. Loan %d created.",
            application.id,
            request.user.email,
            loan.id,
        )

        return Response(
            {
                "application": LoanApplicationAdminSerializer(application).data,
                "loan": LoanAdminSerializer(loan).data,
            },
            status=status.HTTP_200_OK,
        )


class AdminLoanListView(generics.ListAPIView):
    """
    GET /loans/admin/
    Admin view: list all loans.
    """

    permission_classes = [IsAuthenticated, IsAdminRole]
    serializer_class = LoanAdminSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["loan_application__user__email", "account__account_number"]
    ordering_fields = ["created_at", "outstanding_balance", "status"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = Loan.objects.select_related(
            "loan_application__user",
            "loan_application__loan_type",
            "account",
        )

        loan_status = self.request.query_params.get("status")
        if loan_status:
            qs = qs.filter(status=loan_status)

        return qs