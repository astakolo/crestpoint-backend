from django.conf import settings
from django.db import models

from crestpoint_credit.core.models import TimestampedModel
from crestpoint_credit.core.utils import generate_transaction_ref


class BillPaymentStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class BillerCategory(models.Model):
    """A category for billers, e.g. Utilities, Internet, Insurance."""

    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=100, unique=True)
    icon = models.CharField(max_length=50, blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "biller_categories"
        ordering = ["name"]
        verbose_name = "Biller Category"
        verbose_name_plural = "Biller Categories"

    def __str__(self):
        return self.name


class Biller(models.Model):
    """A biller that users can pay bills to."""

    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=200)
    category = models.ForeignKey(
        BillerCategory,
        related_name="billers",
        on_delete=models.PROTECT,
    )
    account_number = models.CharField(max_length=100)
    biller_code = models.CharField(max_length=50)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "billers"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.biller_code})"


class BillerSaved(TimestampedModel):
    """A biller saved by a user for quick future payments."""

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="saved_billers",
        on_delete=models.CASCADE,
        db_index=True,
    )
    biller = models.ForeignKey(
        Biller,
        related_name="saved_by",
        on_delete=models.PROTECT,
    )
    nickname = models.CharField(max_length=100, blank=True, default="")
    account_number = models.CharField(max_length=100)

    class Meta:
        db_table = "saved_billers"
        unique_together = ("user", "biller")
        verbose_name = "Saved Biller"
        verbose_name_plural = "Saved Billers"

    def __str__(self):
        return f"{self.user.email} - {self.biller.name}"


class BillPayment(TimestampedModel):
    """Records a bill payment made by a user."""

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="bill_payments",
        on_delete=models.PROTECT,
        db_index=True,
    )
    account = models.ForeignKey(
        "accounts.BankAccount",
        related_name="bill_payments",
        on_delete=models.PROTECT,
        db_index=True,
    )
    biller = models.ForeignKey(
        Biller,
        related_name="payments",
        on_delete=models.PROTECT,
    )
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=BillPaymentStatus.choices,
        default=BillPaymentStatus.PENDING,
        db_index=True,
    )
    reference = models.CharField(
        max_length=30,
        unique=True,
        default=generate_transaction_ref,
        editable=False,
    )
    narration = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "bill_payments"
        indexes = [
            models.Index(fields=["user", "created_at"], name="ix_bp_user_created"),
            models.Index(fields=["status"], name="ix_bp_status"),
        ]

    def __str__(self):
        return f"{self.reference} - {self.biller.name}"