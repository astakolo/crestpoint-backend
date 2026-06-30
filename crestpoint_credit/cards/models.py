import secrets

from django.conf import settings
from django.db import models

from crestpoint_credit.core.models import TimestampedModel
from crestpoint_credit.core.utils import generate_transaction_ref


class CardType(models.TextChoices):
    VIRTUAL = "virtual", "Virtual"
    PHYSICAL = "physical", "Physical"


class CardBrand(models.TextChoices):
    VISA = "visa", "Visa"
    MASTERCARD = "mastercard", "Mastercard"


class CardStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    FROZEN = "frozen", "Frozen"
    CLOSED = "closed", "Closed"
    EXPIRED = "expired", "Expired"


class TransactionStatus(models.TextChoices):
    COMPLETED = "completed", "Completed"
    PENDING = "pending", "Pending"
    FAILED = "failed", "Failed"


def generate_card_number(brand="visa"):
    """Generate a realistic card number.

    For Visa: starts with 4, 16 digits total.
    For Mastercard: starts with 5, 16 digits total.
    """
    if brand == "mastercard":
        prefix = "5"
    else:
        prefix = "4"

    # Generate remaining 15 digits
    remaining = str(secrets.randbelow(10**15)).zfill(15)
    number = prefix + remaining

    # Format as XXXX XXXX XXXX XXXX
    return f"{number[:4]} {number[4:8]} {number[8:12]} {number[12:]}"


def generate_cvv():
    """Generate a random 3-digit CVV."""
    return str(secrets.randbelow(1000)).zfill(3)


def generate_expiry():
    """Generate a realistic expiry date (2-5 years from now)."""
    from datetime import datetime, timedelta
    import random

    years_ahead = random.randint(2, 5)
    expiry = datetime.now() + timedelta(days=years_ahead * 365)
    return str(expiry.month).zfill(2), str(expiry.year)


class VirtualCard(TimestampedModel):
    """A virtual card linked to a user's bank account."""

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="virtual_cards",
        on_delete=models.PROTECT,
        db_index=True,
    )
    account = models.ForeignKey(
        "accounts.BankAccount",
        related_name="virtual_cards",
        on_delete=models.PROTECT,
        db_index=True,
    )
    card_number = models.CharField(max_length=20, unique=True, db_index=True)
    cardholder_name = models.CharField(max_length=200)
    expiry_month = models.CharField(max_length=2)
    expiry_year = models.CharField(max_length=4)
    cvv = models.CharField(max_length=4)
    card_type = models.CharField(
        max_length=20,
        choices=CardType.choices,
        default=CardType.VIRTUAL,
    )
    brand = models.CharField(
        max_length=20,
        choices=CardBrand.choices,
        default=CardBrand.VISA,
    )
    balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    spending_limit = models.DecimalField(max_digits=15, decimal_places=2, default=5000)
    amount_spent = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    status = models.CharField(
        max_length=20,
        choices=CardStatus.choices,
        default=CardStatus.ACTIVE,
        db_index=True,
    )
    is_default = models.BooleanField(default=False)

    class Meta:
        db_table = "virtual_cards"
        indexes = [
            models.Index(fields=["user", "status"], name="ix_vc_user_status"),
        ]

    def __str__(self):
        return f"Card ****{self.card_number[-4:]} - {self.status}"


class CardTransaction(TimestampedModel):
    """Records a transaction made with a virtual card."""

    id = models.BigAutoField(primary_key=True)
    card = models.ForeignKey(
        VirtualCard,
        related_name="transactions",
        on_delete=models.PROTECT,
        db_index=True,
    )
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    merchant_name = models.CharField(max_length=200)
    merchant_category = models.CharField(max_length=100, blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=TransactionStatus.choices,
        default=TransactionStatus.COMPLETED,
    )
    reference = models.CharField(
        max_length=30,
        unique=True,
        default=generate_transaction_ref,
        editable=False,
    )
    description = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "card_transactions"
        indexes = [
            models.Index(fields=["card", "created_at"], name="ix_ctx_card_created"),
        ]

    def __str__(self):
        return f"{self.reference} - {self.merchant_name}"


class CardFunding(TimestampedModel):
    """Records funding a virtual card from a bank account."""

    id = models.BigAutoField(primary_key=True)
    card = models.ForeignKey(
        VirtualCard,
        related_name="fundings",
        on_delete=models.PROTECT,
        db_index=True,
    )
    account = models.ForeignKey(
        "accounts.BankAccount",
        related_name="card_fundings",
        on_delete=models.PROTECT,
    )
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=TransactionStatus.choices,
        default=TransactionStatus.COMPLETED,
    )
    reference = models.CharField(
        max_length=30,
        unique=True,
        default=generate_transaction_ref,
        editable=False,
    )

    class Meta:
        db_table = "card_fundings"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Card funding {self.reference} - {self.amount}"