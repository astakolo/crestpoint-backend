from django.conf import settings
from django.db import models

from crestpoint_credit.core.models import TimestampedModel
from crestpoint_credit.core.utils import generate_transaction_ref


class TransactionType(models.TextChoices):
    BUY = "buy", "Buy"
    SELL = "sell", "Sell"
    DEPOSIT = "deposit", "Deposit"
    WITHDRAWAL = "withdrawal", "Withdrawal"


class TransactionStatus(models.TextChoices):
    COMPLETED = "completed", "Completed"
    PENDING = "pending", "Pending"
    FAILED = "failed", "Failed"


class Stock(models.Model):
    """Represents a tradable stock with current market data."""

    id = models.BigAutoField(primary_key=True)
    symbol = models.CharField(max_length=10, unique=True, db_index=True)
    name = models.CharField(max_length=200)
    current_price = models.DecimalField(max_digits=15, decimal_places=2)
    previous_close = models.DecimalField(max_digits=15, decimal_places=2)
    change_percent = models.DecimalField(max_digits=8, decimal_places=4)
    market_cap = models.DecimalField(max_digits=20, decimal_places=2, null=True, blank=True)
    volume = models.BigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "stocks"
        ordering = ["symbol"]

    def __str__(self):
        return f"{self.symbol} - {self.name}"


class InvestmentAccount(TimestampedModel):
    """A user's investment account that holds their portfolio."""

    id = models.BigAutoField(primary_key=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        related_name="investment_account",
        on_delete=models.PROTECT,
        db_index=True,
    )
    balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_invested = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_returns = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "investment_accounts"

    def __str__(self):
        return f"Investment Account for {self.user.email}"


class StockHolding(TimestampedModel):
    """A user's holding of a particular stock."""

    id = models.BigAutoField(primary_key=True)
    investment_account = models.ForeignKey(
        InvestmentAccount,
        related_name="holdings",
        on_delete=models.PROTECT,
        db_index=True,
    )
    stock = models.ForeignKey(
        Stock,
        related_name="holdings",
        on_delete=models.PROTECT,
    )
    quantity = models.DecimalField(max_digits=15, decimal_places=4)
    average_buy_price = models.DecimalField(max_digits=15, decimal_places=2)
    current_value = models.DecimalField(max_digits=15, decimal_places=2)
    total_invested = models.DecimalField(max_digits=15, decimal_places=2)
    pnl = models.DecimalField(max_digits=15, decimal_places=2)

    class Meta:
        db_table = "stock_holdings"
        unique_together = ("investment_account", "stock")
        indexes = [
            models.Index(fields=["investment_account", "stock"], name="ix_holding_account_stock"),
        ]

    def __str__(self):
        return f"{self.investment_account.user.email} - {self.stock.symbol} x{self.quantity}"


class InvestmentTransaction(TimestampedModel):
    """Records an investment-related transaction."""

    id = models.BigAutoField(primary_key=True)
    investment_account = models.ForeignKey(
        InvestmentAccount,
        related_name="transactions",
        on_delete=models.PROTECT,
        db_index=True,
    )
    stock = models.ForeignKey(
        Stock,
        null=True,
        blank=True,
        related_name="transactions",
        on_delete=models.SET_NULL,
    )
    transaction_type = models.CharField(
        max_length=20,
        choices=TransactionType.choices,
        db_index=True,
    )
    quantity = models.DecimalField(max_digits=15, decimal_places=4, null=True, blank=True)
    price_per_unit = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=TransactionStatus.choices,
        default=TransactionStatus.COMPLETED,
        db_index=True,
    )
    reference = models.CharField(
        max_length=30,
        unique=True,
        default=generate_transaction_ref,
        editable=False,
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "investment_transactions"
        indexes = [
            models.Index(fields=["investment_account", "created_at"], name="ix_itx_account_created"),
        ]

    def __str__(self):
        return self.reference