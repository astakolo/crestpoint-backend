import secrets
from datetime import date

from django.conf import settings
from django.db import models

from crestpoint_credit.core.models import TimestampedModel


# ---------------------------------------------------------------------------
# Choice enumerations
# ---------------------------------------------------------------------------


class PaymentMethod(models.TextChoices):
    BANK_TRANSFER = "bank_transfer", "Bank Transfer"
    DEBIT_CARD = "debit_card", "Debit Card"
    CREDIT_CARD = "credit_card", "Credit Card"
    MOBILE_MONEY = "mobile_money", "Mobile Money"


class PaymentStatus(models.TextChoices):
    INITIATED = "initiated", "Initiated"
    PROCESSING = "processing", "Processing"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    REFUNDED = "refunded", "Refunded"


class PaymentProvider(models.TextChoices):
    STRIPE_MOCK = "stripe_mock", "Stripe (Mock)"
    PAYPAL_MOCK = "paypal_mock", "PayPal (Mock)"
    BANK_MOCK = "bank_mock", "Bank (Mock)"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def generate_payment_reference() -> str:
    """Generate a unique payment reference in the format ``PAY-YYYYMMDD-XXXXXXXX``.

    The last segment is an 8-character hexadecimal string derived from
    ``secrets.token_hex``.

    Returns:
        str: e.g. ``'PAY-20250115-3f8a92c1'``
    """
    today = date.today().strftime("%Y%m%d")
    token = secrets.token_hex(4)  # 8 hex characters
    return f"PAY-{today}-{token}"


# ---------------------------------------------------------------------------
# Payment Model
# ---------------------------------------------------------------------------


class Payment(TimestampedModel):
    """Represents a payment processed through an external provider.

    Each payment is associated with a user and a bank account, and tracks
    its lifecycle from initiation through completion, failure, or refund.
    """

    id = models.BigAutoField(primary_key=True)
    reference = models.CharField(
        max_length=40,
        unique=True,
        default=generate_payment_reference,
        editable=False,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="payments",
        on_delete=models.PROTECT,
        db_index=True,
    )
    account = models.ForeignKey(
        "accounts.BankAccount",
        related_name="payments",
        on_delete=models.PROTECT,
        db_index=True,
    )
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
    )
    provider = models.CharField(
        max_length=20,
        choices=PaymentProvider.choices,
        default=PaymentProvider.BANK_MOCK,
    )
    status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.INITIATED,
    )
    provider_payment_id = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Unique identifier returned by the payment provider.",
    )
    provider_response = models.JSONField(
        default=dict,
        blank=True,
        help_text="Raw response payload from the payment provider.",
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Arbitrary metadata attached to this payment.",
    )
    error_message = models.TextField(
        blank=True,
        default="",
        help_text="Error details if the payment failed.",
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when the payment was completed or refunded.",
    )

    class Meta:
        db_table = "payments"
        verbose_name = "Payment"
        verbose_name_plural = "Payments"
        indexes = [
            models.Index(
                fields=["user", "created_at"],
                name="ix_payment_user_created",
            ),
            models.Index(
                fields=["status"],
                name="ix_payment_status",
            ),
            models.Index(
                fields=["reference"],
                name="ix_payment_reference",
            ),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.reference
