import secrets

from django.db import models
from django.conf import settings

from crestpoint_credit.core.models import TimestampedModel
from crestpoint_credit.core.utils import generate_transaction_ref


class TransactionType(models.TextChoices):
    DEPOSIT = "deposit", "Deposit"
    WITHDRAWAL = "withdrawal", "Withdrawal"
    TRANSFER_IN = "transfer_in", "Transfer In"
    TRANSFER_OUT = "transfer_out", "Transfer Out"
    PAYMENT = "payment", "Payment"


class TransactionStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    REVERSED = "reversed", "Reversed"


class WithdrawalRequestStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class Transaction(TimestampedModel):
    """
    Represents a financial transaction (deposit, withdrawal, transfer, payment).
    Every mutation of a BankAccount balance MUST create a Transaction record.
    """

    id = models.BigAutoField(primary_key=True)
    reference = models.CharField(
        max_length=30,
        unique=True,
        default=generate_transaction_ref,
        editable=False,
    )
    transaction_type = models.CharField(
        max_length=20,
        choices=TransactionType.choices,
    )
    status = models.CharField(
        max_length=20,
        choices=TransactionStatus.choices,
        default=TransactionStatus.PENDING,
    )
    account = models.ForeignKey(
        "accounts.BankAccount",
        related_name="transactions",
        on_delete=models.PROTECT,
        db_index=True,
    )
    recipient_account = models.ForeignKey(
        "accounts.BankAccount",
        null=True,
        blank=True,
        related_name="incoming_transactions",
        on_delete=models.SET_NULL,
    )
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    description = models.TextField(blank=True, default="")
    balance_before = models.DecimalField(max_digits=15, decimal_places=2)
    balance_after = models.DecimalField(max_digits=15, decimal_places=2)
    is_flagged = models.BooleanField(default=False)
    flag_reason = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["account", "created_at"], name="ix_txn_account_created"),
            models.Index(fields=["reference"], name="ix_txn_reference"),
            models.Index(fields=["status"], name="ix_txn_status"),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return self.reference


class WithdrawalRequest(TimestampedModel):
    """
    Represents a user-initiated withdrawal request that requires admin approval.
    When approved, funds are deducted from the account. When rejected, no
    balance change occurs.
    """

    id = models.BigAutoField(primary_key=True)
    reference = models.CharField(
        max_length=30,
        unique=True,
        default=generate_transaction_ref,
        editable=False,
    )
    account = models.ForeignKey(
        "accounts.BankAccount",
        related_name="withdrawal_requests",
        on_delete=models.PROTECT,
        db_index=True,
    )
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=WithdrawalRequestStatus.choices,
        default=WithdrawalRequestStatus.PENDING,
        db_index=True,
    )
    description = models.TextField(blank=True, default="")
    bank_name = models.CharField(max_length=200, blank=True, default="")
    account_number = models.CharField(max_length=50, blank=True, default="")
    routing_number = models.CharField(max_length=50, blank=True, default="")
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_withdrawals",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "withdrawal_requests"
        indexes = [
            models.Index(fields=["account", "created_at"], name="ix_wr_account_created"),
            models.Index(fields=["status"], name="ix_wr_status"),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference} - {self.status}"


class WithdrawalOTP(models.Model):
    """One-time password issued by admin for a user's withdrawal request.

    An OTP is valid for ``OTP_TTL_MINUTES`` minutes after creation and can only
    be used once (``is_used`` flag).  Only one *active* (unused, non-expired)
    OTP may exist per user at a time — generating a new one invalidates any
    previous active code.
    """

    OTP_TTL_MINUTES = 30

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="withdrawal_otps",
        db_index=True,
    )
    code = models.CharField(max_length=8, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="generated_withdrawal_otps",
    )
    is_used = models.BooleanField(default=False)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "withdrawal_otps"
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = secrets.token_hex(3).upper()  # 6-char hex, e.g. A3F1B2
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        from django.utils import timezone
        from datetime import timedelta
        if not self.created_at:
            return True
        return timezone.now() > self.created_at + timedelta(minutes=self.OTP_TTL_MINUTES)

    @property
    def is_active(self):
        return not self.is_used and not self.is_expired

    def __str__(self):
        return f"OTP {self.code} for {self.user.email}"