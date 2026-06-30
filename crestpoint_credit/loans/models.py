from django.conf import settings
from django.db import models

from crestpoint_credit.core.models import TimestampedModel
from crestpoint_credit.core.utils import generate_transaction_ref


class LoanApplicationStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    DISBURSED = "disbursed", "Disbursed"
    CLOSED = "closed", "Closed"


class LoanStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    PAID_OFF = "paid_off", "Paid Off"
    DEFAULTED = "defaulted", "Defaulted"
    CLOSED = "closed", "Closed"


class RepaymentStatus(models.TextChoices):
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    PENDING = "pending", "Pending"


class LoanType(models.Model):
    """Defines a type of loan available to customers."""

    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=100)
    min_amount = models.DecimalField(max_digits=15, decimal_places=2)
    max_amount = models.DecimalField(max_digits=15, decimal_places=2)
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2)  # e.g. 5.50 for 5.50%
    max_term_months = models.PositiveIntegerField()
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "loan_types"
        ordering = ["name"]

    def __str__(self):
        return self.name


class LoanApplication(TimestampedModel):
    """A customer's loan application submitted for review."""

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="loan_applications",
        on_delete=models.PROTECT,
        db_index=True,
    )
    loan_type = models.ForeignKey(
        LoanType,
        related_name="applications",
        on_delete=models.PROTECT,
    )
    amount_requested = models.DecimalField(max_digits=15, decimal_places=2)
    purpose = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=LoanApplicationStatus.choices,
        default=LoanApplicationStatus.PENDING,
        db_index=True,
    )
    employment_status = models.CharField(max_length=50, blank=True, default="")
    monthly_income = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True
    )
    term_months = models.PositiveIntegerField()
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_loan_applications",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "loan_applications"
        indexes = [
            models.Index(fields=["user", "status"], name="ix_la_user_status"),
            models.Index(fields=["status"], name="ix_la_status"),
        ]

    def __str__(self):
        return f"Loan Application #{self.id} - {self.status}"


class Loan(TimestampedModel):
    """An active or historical loan linked to a bank account."""

    id = models.BigAutoField(primary_key=True)
    loan_application = models.OneToOneField(
        LoanApplication,
        related_name="loan",
        on_delete=models.PROTECT,
    )
    account = models.ForeignKey(
        "accounts.BankAccount",
        related_name="loans",
        on_delete=models.PROTECT,
        db_index=True,
    )
    principal = models.DecimalField(max_digits=15, decimal_places=2)
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2)
    term_months = models.PositiveIntegerField()
    outstanding_balance = models.DecimalField(max_digits=15, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=LoanStatus.choices,
        default=LoanStatus.ACTIVE,
        db_index=True,
    )
    disbursement_date = models.DateTimeField(null=True, blank=True)
    next_payment_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "loans"
        indexes = [
            models.Index(fields=["account", "status"], name="ix_loan_account_status"),
            models.Index(fields=["status"], name="ix_loan_status"),
        ]

    def __str__(self):
        return f"Loan #{self.id} - {self.status}"


class LoanRepayment(TimestampedModel):
    """Records a repayment made against a loan."""

    id = models.BigAutoField(primary_key=True)
    loan = models.ForeignKey(
        Loan,
        related_name="repayments",
        on_delete=models.PROTECT,
        db_index=True,
    )
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    principal_portion = models.DecimalField(max_digits=15, decimal_places=2)
    interest_portion = models.DecimalField(max_digits=15, decimal_places=2)
    payment_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20,
        choices=RepaymentStatus.choices,
        default=RepaymentStatus.COMPLETED,
    )
    reference = models.CharField(
        max_length=30,
        unique=True,
        default=generate_transaction_ref,
        editable=False,
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "loan_repayments"
        indexes = [
            models.Index(fields=["loan", "payment_date"], name="ix_lr_loan_date"),
        ]

    def __str__(self):
        return self.reference