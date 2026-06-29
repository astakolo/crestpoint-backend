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
