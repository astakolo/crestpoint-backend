from decimal import Decimal

from rest_framework import serializers

from crestpoint_credit.accounts.models import BankAccount
from .models import (
    Stock,
    InvestmentAccount,
    StockHolding,
    InvestmentTransaction,
)


class StockSerializer(serializers.ModelSerializer):
    """Read serializer for stock data."""

    class Meta:
        model = Stock
        fields = [
            "id",
            "symbol",
            "name",
            "current_price",
            "previous_close",
            "change_percent",
            "market_cap",
            "volume",
            "updated_at",
        ]
        read_only_fields = fields


class StockDetailSerializer(StockSerializer):
    """Extended stock detail serializer."""

    class Meta(StockSerializer.Meta):
        fields = StockSerializer.Meta.fields


class InvestmentAccountSerializer(serializers.ModelSerializer):
    """Read serializer for a user's investment account."""

    class Meta:
        model = InvestmentAccount
        fields = [
            "id",
            "balance",
            "total_invested",
            "total_returns",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class StockHoldingSerializer(serializers.ModelSerializer):
    """Read serializer for a user's stock holdings."""

    symbol = serializers.CharField(source="stock.symbol", read_only=True)
    name = serializers.CharField(source="stock.name", read_only=True)
    current_price = serializers.DecimalField(
        source="stock.current_price", max_digits=15, decimal_places=2, read_only=True
    )

    class Meta:
        model = StockHolding
        fields = [
            "id",
            "symbol",
            "name",
            "quantity",
            "average_buy_price",
            "current_value",
            "total_invested",
            "pnl",
            "current_price",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class InvestmentTransactionSerializer(serializers.ModelSerializer):
    """Read serializer for investment transactions."""

    symbol = serializers.CharField(source="stock.symbol", read_only=True, default=None)

    class Meta:
        model = InvestmentTransaction
        fields = [
            "id",
            "reference",
            "transaction_type",
            "symbol",
            "quantity",
            "price_per_unit",
            "amount",
            "status",
            "created_at",
        ]
        read_only_fields = fields


class BuyStockSerializer(serializers.Serializer):
    """Validates input for buying a stock."""

    stock_id = serializers.IntegerField(help_text="ID of the stock to buy.")
    quantity = serializers.DecimalField(max_digits=15, decimal_places=4)
    account_id = serializers.IntegerField(help_text="Bank account to debit funds from.")

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than zero.")
        return value

    def validate_stock_id(self, value):
        try:
            stock = Stock.objects.get(pk=value)
        except Stock.DoesNotExist:
            raise serializers.ValidationError("Stock does not exist.")
        self._stock = stock
        return value

    def validate_account_id(self, value):
        request = self.context.get("request")
        try:
            account = BankAccount.objects.get(pk=value)
        except BankAccount.DoesNotExist:
            raise serializers.ValidationError("Bank account does not exist.")
        if request and account.user_id != request.user.id:
            raise serializers.ValidationError("This account does not belong to you.")
        if not account.is_active:
            raise serializers.ValidationError("This account is not active.")
        if account.is_frozen:
            raise serializers.ValidationError("This account is frozen.")
        self._account = account
        return value

    def validate(self, attrs):
        stock = getattr(self, "_stock", None)
        account = getattr(self, "_account", None)
        if stock and account:
            total_cost = stock.current_price * attrs["quantity"]
            if account.balance < total_cost:
                raise serializers.ValidationError(
                    {"non_field_errors": ["Insufficient funds to complete this purchase."]}
                )
        return attrs


class SellStockSerializer(serializers.Serializer):
    """Validates input for selling a stock."""

    stock_id = serializers.IntegerField(help_text="ID of the stock to sell.")
    quantity = serializers.DecimalField(max_digits=15, decimal_places=4)
    account_id = serializers.IntegerField(help_text="Bank account to credit funds to.")

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than zero.")
        return value

    def validate_stock_id(self, value):
        request = self.context.get("request")
        try:
            stock = Stock.objects.get(pk=value)
        except Stock.DoesNotExist:
            raise serializers.ValidationError("Stock does not exist.")
        self._stock = stock

        # Check user has a holding for this stock
        try:
            holding = StockHolding.objects.get(
                investment_account__user=request.user,
                stock=stock,
            )
            self._holding = holding
        except StockHolding.DoesNotExist:
            raise serializers.ValidationError("You do not hold this stock.")

        return value

    def validate_account_id(self, value):
        request = self.context.get("request")
        try:
            account = BankAccount.objects.get(pk=value)
        except BankAccount.DoesNotExist:
            raise serializers.ValidationError("Bank account does not exist.")
        if request and account.user_id != request.user.id:
            raise serializers.ValidationError("This account does not belong to you.")
        if not account.is_active:
            raise serializers.ValidationError("This account is not active.")
        self._account = account
        return value

    def validate(self, attrs):
        holding = getattr(self, "_holding", None)
        stock = getattr(self, "_stock", None)
        if holding and stock:
            if attrs["quantity"] > holding.quantity:
                raise serializers.ValidationError(
                    {"quantity": f"You only hold {holding.quantity} shares."}
                )
        return attrs