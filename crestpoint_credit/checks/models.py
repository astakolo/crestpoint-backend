from django.conf import settings
from django.db import models

from crestpoint_credit.core.models import TimestampedModel
from crestpoint_credit.core.utils import generate_transaction_ref


class CheckDepositStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    REJECTED = "rejected", "Rejected"


class CheckDeposit(TimestampedModel):
    """A check deposit submitted by a user with front and back images."""

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="check_deposits",
        on_delete=models.PROTECT,
        db_index=True,
    )
    account = models.ForeignKey(
        "accounts.BankAccount",
        related_name="check_deposits",
        on_delete=models.PROTECT,
        db_index=True,
    )
    check_number = models.CharField(max_length=50, blank=True, default="")
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    front_image = models.ImageField(upload_to="checks/")
    back_image = models.ImageField(upload_to="checks/")
    status = models.CharField(
        max_length=20,
        choices=CheckDepositStatus.choices,
        default=CheckDepositStatus.PENDING,
        db_index=True,
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.TextField(blank=True, default="")
    reference = models.CharField(
        max_length=30,
        unique=True,
        default=generate_transaction_ref,
        editable=False,
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "check_deposits"
        indexes = [
            models.Index(fields=["user", "status"], name="ix_cd_user_status"),
            models.Index(fields=["status"], name="ix_cd_status"),
        ]

    def __str__(self):
        return f"Check Deposit {self.reference} - {self.status}"