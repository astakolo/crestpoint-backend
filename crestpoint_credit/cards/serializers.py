from decimal import Decimal

from rest_framework import serializers

from crestpoint_credit.accounts.models import BankAccount
from .models import (
    VirtualCard,
    CardTransaction,
    CardFunding,
    generate_card_number,
    generate_cvv,
    generate_expiry,
)


class VirtualCardSerializer(serializers.ModelSerializer):
    """Read serializer for a user's virtual cards (masked card number)."""

    account_number = serializers.CharField(source="account.account_number", read_only=True)
    masked_card_number = serializers.SerializerMethodField()
    cvv = serializers.SerializerMethodField()

    class Meta:
        model = VirtualCard
        fields = [
            "id",
            "account_number",
            "card_number",
            "masked_card_number",
            "cardholder_name",
            "expiry_month",
            "expiry_year",
            "cvv",
            "card_type",
            "brand",
            "balance",
            "spending_limit",
            "amount_spent",
            "status",
            "is_default",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_masked_card_number(self, obj):
        """Return card number with all but last 4 digits masked."""
        last_four = obj.card_number.replace(" ", "")[-4:]
        return f"**** **** **** {last_four}"

    def get_cvv(self, obj):
        """Hide CVV in list views."""
        return "***"


class VirtualCardDetailSerializer(VirtualCardSerializer):
    """Extended serializer for detail views showing full card number and CVV."""

    cvv = serializers.CharField(read_only=True)
    card_number = serializers.CharField(read_only=True)
    masked_card_number = serializers.SerializerMethodField()

    class Meta(VirtualCardSerializer.Meta):
        pass


class CardCreateSerializer(serializers.Serializer):
    """Validates input for creating a new virtual card."""

    account_id = serializers.IntegerField(help_text="Bank account to link the card to.")
    card_type = serializers.ChoiceField(
        choices=["virtual", "physical"],
        required=False,
        default="virtual",
    )
    brand = serializers.ChoiceField(
        choices=["visa", "mastercard"],
        required=False,
        default="visa",
    )
    spending_limit = serializers.DecimalField(
        max_digits=15,
        decimal_places=2,
        required=False,
        default=Decimal("5000.00"),
    )
    cardholder_name = serializers.CharField(max_length=200, required=False)

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

    def validate_spending_limit(self, value):
        if value <= 0:
            raise serializers.ValidationError("Spending limit must be greater than zero.")
        return value


class CardFreezeSerializer(serializers.Serializer):
    """Validates input for freezing/unfreezing a card."""

    action = serializers.ChoiceField(
        choices=["freeze", "unfreeze"],
        help_text="'freeze' to freeze the card, 'unfreeze' to unfreeze it.",
    )


class CardFundSerializer(serializers.Serializer):
    """Validates input for funding a virtual card from a bank account."""

    account_id = serializers.IntegerField(help_text="Bank account to debit funds from.")
    amount = serializers.DecimalField(max_digits=15, decimal_places=2)

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
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
        account = getattr(self, "_account", None)
        amount = attrs.get("amount", Decimal("0"))
        if account and account.balance < amount:
            raise serializers.ValidationError(
                {"amount": "Insufficient funds to fund this card."}
            )
        return attrs


class CardTransactionSerializer(serializers.ModelSerializer):
    """Read serializer for card transactions."""

    class Meta:
        model = CardTransaction
        fields = [
            "id",
            "reference",
            "amount",
            "merchant_name",
            "merchant_category",
            "status",
            "description",
            "created_at",
        ]
        read_only_fields = fields


class VirtualCardAdminSerializer(serializers.ModelSerializer):
    """Admin serializer for virtual cards with user info."""

    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_full_name = serializers.SerializerMethodField()
    account_number = serializers.CharField(source="account.account_number", read_only=True)

    class Meta:
        model = VirtualCard
        fields = [
            "id",
            "user_email",
            "user_full_name",
            "account_number",
            "card_number",
            "cardholder_name",
            "card_type",
            "brand",
            "balance",
            "spending_limit",
            "amount_spent",
            "status",
            "is_default",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_user_full_name(self, obj):
        return f"{obj.user.first_name} {obj.user.last_name}".strip()