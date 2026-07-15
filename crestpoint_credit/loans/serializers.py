from decimal import Decimal

from rest_framework import serializers

from crestpoint_credit.accounts.models import BankAccount
from .models import (
    LoanType,
    LoanApplication,
    Loan,
    LoanRepayment,
)


class LoanTypeSerializer(serializers.ModelSerializer):
    """Read serializer for loan types."""

    class Meta:
        model = LoanType
        fields = [
            "id",
            "name",
            "min_amount",
            "max_amount",
            "interest_rate",
            "max_term_months",
            "description",
        ]
        read_only_fields = fields


class LoanApplicationCreateSerializer(serializers.Serializer):
    """Validates input for creating a new loan application."""

    loan_type_id = serializers.IntegerField(help_text="ID of the loan type to apply for.")
    amount_requested = serializers.DecimalField(max_digits=15, decimal_places=2)
    purpose = serializers.CharField(required=False, default="", allow_blank=True)
    employment_status = serializers.CharField(required=False, default="", allow_blank=True, max_length=50)
    monthly_income = serializers.DecimalField(
        max_digits=15, decimal_places=2, required=False, allow_null=True
    )
    term_months = serializers.IntegerField(min_value=1)

    def validate_amount_requested(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value

    def validate_loan_type_id(self, value):
        try:
            loan_type = LoanType.objects.get(pk=value)
        except LoanType.DoesNotExist:
            raise serializers.ValidationError("Loan type does not exist.")
        if not loan_type.is_active:
            raise serializers.ValidationError("This loan type is currently unavailable.")
        self._loan_type = loan_type
        return value

    def validate(self, attrs):
        loan_type = getattr(self, "_loan_type", None)
        if loan_type:
            amount = attrs.get("amount_requested", Decimal("0"))
            term = attrs.get("term_months", 0)

            if amount < loan_type.min_amount:
                raise serializers.ValidationError(
                    {"amount_requested": f"Minimum amount for this loan type is {loan_type.min_amount}."}
                )
            if amount > loan_type.max_amount:
                raise serializers.ValidationError(
                    {"amount_requested": f"Maximum amount for this loan type is {loan_type.max_amount}."}
                )
            if term > loan_type.max_term_months:
                raise serializers.ValidationError(
                    {"term_months": f"Maximum term for this loan type is {loan_type.max_term_months} months."}
                )
            if term < 1:
                raise serializers.ValidationError(
                    {"term_months": "Term must be at least 1 month."}
                )

        return attrs


class LoanApplicationSerializer(serializers.ModelSerializer):
    """Read serializer for a user's loan application."""

    loan_type_name = serializers.CharField(source="loan_type.name", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = LoanApplication
        fields = [
            "id",
            "loan_type_name",
            "user_email",
            "amount_requested",
            "purpose",
            "status",
            "employment_status",
            "monthly_income",
            "term_months",
            "submitted_at",
            "reviewed_at",
            "rejection_reason",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class LoanApplicationAdminSerializer(serializers.ModelSerializer):
    """Extended serializer for admin views showing full user info."""

    loan_type_name = serializers.CharField(source="loan_type.name", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_full_name = serializers.SerializerMethodField()
    reviewer_email = serializers.EmailField(
        source="reviewed_by.email", read_only=True, default=None
    )

    class Meta:
        model = LoanApplication
        fields = [
            "id",
            "loan_type_name",
            "user_email",
            "user_full_name",
            "amount_requested",
            "purpose",
            "status",
            "employment_status",
            "monthly_income",
            "term_months",
            "submitted_at",
            "reviewed_by",
            "reviewed_at",
            "rejection_reason",
            "reviewer_email",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_user_full_name(self, obj):
        return f"{obj.user.first_name} {obj.user.last_name}".strip()


class AdminReviewLoanApplicationSerializer(serializers.Serializer):
    """Validates admin approve/reject input for loan applications."""

    action = serializers.ChoiceField(
        choices=["approve", "reject"],
        help_text="'approve' to approve the application, 'reject' to deny it.",
    )
    rejection_reason = serializers.CharField(
        required=False,
        default="",
        allow_blank=True,
        help_text="Required when action is 'reject'.",
    )
    account_id = serializers.IntegerField(
        required=False,
        default=None,
        help_text="Bank account ID to disburse to (required for approval).",
    )

    def validate(self, attrs):
        if attrs["action"] == "reject" and not attrs.get("rejection_reason", "").strip():
            raise serializers.ValidationError(
                {"rejection_reason": "A rejection reason is required when rejecting an application."}
            )
        if attrs["action"] == "approve" and not attrs.get("account_id"):
            raise serializers.ValidationError(
                {"account_id": "A bank account ID is required when approving a loan application."}
            )
        return attrs


class LoanSerializer(serializers.ModelSerializer):
    """Read serializer for a user's loan."""

    account_number = serializers.CharField(source="account.account_number", read_only=True)
    loan_type_name = serializers.CharField(
        source="loan_application.loan_type.name", read_only=True
    )
    total_repaid = serializers.SerializerMethodField()

    class Meta:
        model = Loan
        fields = [
            "id",
            "account_number",
            "loan_type_name",
            "principal",
            "interest_rate",
            "term_months",
            "outstanding_balance",
            "status",
            "disbursement_date",
            "next_payment_date",
            "total_repaid",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_total_repaid(self, obj):
        from django.db.models import Sum
        total = obj.repayments.filter(status="completed").aggregate(
            total=Sum("amount")
        )["total"] or Decimal("0")
        return str(total.quantize(Decimal("0.01")))


class LoanDetailSerializer(LoanSerializer):
    """Extended loan serializer with repayment schedule."""

    repayments = serializers.SerializerMethodField()

    class Meta(LoanSerializer.Meta):
        fields = LoanSerializer.Meta.fields + ["repayments"]

    def get_repayments(self, obj):
        repayments = obj.repayments.order_by("payment_date")
        return LoanRepaymentSerializer(repayments, many=True).data


class LoanAdminSerializer(LoanDetailSerializer):
    """Admin serializer for loans with user info."""

    user_email = serializers.EmailField(
        source="loan_application.user.email", read_only=True
    )
    user_full_name = serializers.SerializerMethodField()

    class Meta(LoanDetailSerializer.Meta):
        fields = LoanDetailSerializer.Meta.fields + ["user_email", "user_full_name"]

    def get_user_full_name(self, obj):
        user = obj.loan_application.user
        return f"{user.first_name} {user.last_name}".strip()


class LoanRepaymentSerializer(serializers.ModelSerializer):
    """Read serializer for loan repayments."""

    class Meta:
        model = LoanRepayment
        fields = [
            "id",
            "reference",
            "amount",
            "principal_portion",
            "interest_portion",
            "payment_date",
            "status",
        ]
        read_only_fields = fields


class LoanRepaymentCreateSerializer(serializers.Serializer):
    """Validates input for making a loan repayment."""

    loan_id = serializers.IntegerField(help_text="ID of the loan to repay.")
    amount = serializers.DecimalField(max_digits=15, decimal_places=2)

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value

    def validate_loan_id(self, value):
        request = self.context.get("request")
        try:
            loan = Loan.objects.select_related("loan_application", "account").get(pk=value)
        except Loan.DoesNotExist:
            raise serializers.ValidationError("Loan does not exist.")

        if request and loan.loan_application.user_id != request.user.id:
            raise serializers.ValidationError("This loan does not belong to you.")

        if loan.status not in ("active",):
            raise serializers.ValidationError("This loan is not active.")

        self._loan = loan
        return value

    def validate(self, attrs):
        loan = getattr(self, "_loan", None)
        amount = attrs.get("amount", Decimal("0"))
        if loan and amount > loan.outstanding_balance:
            raise serializers.ValidationError(
                {"amount": f"Amount exceeds outstanding balance of {loan.outstanding_balance}."}
            )
        return attrs