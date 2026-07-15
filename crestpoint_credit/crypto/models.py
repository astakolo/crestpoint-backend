import secrets

from django.conf import settings
from django.db import models

from crestpoint_credit.core.models import TimestampedModel
from crestpoint_credit.core.utils import generate_transaction_ref


class CryptoCurrency(models.TextChoices):
    BTC = "BTC", "Bitcoin"
    ETH = "ETH", "Ethereum"
    USDT = "USDT", "Tether"


class CryptoTransactionType(models.TextChoices):
    DEPOSIT = "deposit", "Deposit"
    WITHDRAWAL = "withdrawal", "Withdrawal"
    SWAP = "swap", "Swap"


class CryptoTransactionStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class CryptoWallet(TimestampedModel):
    """A user's crypto wallet for holding digital assets."""

    id = models.BigAutoField(primary_key=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        related_name="crypto_wallet",
        on_delete=models.PROTECT,
        db_index=True,
    )
    wallet_address = models.CharField(max_length=100, unique=True)
    currency = models.CharField(
        max_length=10,
        choices=CryptoCurrency.choices,
        default=CryptoCurrency.BTC,
    )
    balance = models.DecimalField(max_digits=18, decimal_places=8, default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "crypto_wallets"

    def __str__(self):
        return f"{self.user.email} - {self.currency} Wallet"


class CryptoTransaction(TimestampedModel):
    """Records a crypto-related transaction (deposit, withdrawal, swap)."""

    id = models.BigAutoField(primary_key=True)
    wallet = models.ForeignKey(
        CryptoWallet,
        related_name="transactions",
        on_delete=models.PROTECT,
        db_index=True,
    )
    transaction_type = models.CharField(
        max_length=20,
        choices=CryptoTransactionType.choices,
        db_index=True,
    )
    crypto_currency = models.CharField(
        max_length=10,
        choices=CryptoCurrency.choices,
    )
    amount = models.DecimalField(max_digits=18, decimal_places=8)
    usd_amount = models.DecimalField(max_digits=15, decimal_places=2)
    exchange_rate = models.DecimalField(max_digits=18, decimal_places=8)
    status = models.CharField(
        max_length=20,
        choices=CryptoTransactionStatus.choices,
        default=CryptoTransactionStatus.PENDING,
        db_index=True,
    )
    tx_hash = models.CharField(max_length=128, blank=True, default="")
    payment_screenshot = models.ImageField(
        upload_to="crypto/", blank=True, null=True
    )
    wallet_address = models.CharField(max_length=100, blank=True, default="")
    reference = models.CharField(
        max_length=30,
        unique=True,
        default=generate_transaction_ref,
        editable=False,
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "crypto_transactions"
        indexes = [
            models.Index(fields=["wallet", "created_at"], name="ix_ctx_wallet_created"),
            models.Index(fields=["status"], name="ix_ctx_status"),
        ]

    def __str__(self):
        return f"{self.reference} - {self.transaction_type}"


def generate_wallet_address():
    """Generate a realistic ETH-like wallet address: 0x + 40 hex characters."""
    return "0x" + secrets.token_hex(20)