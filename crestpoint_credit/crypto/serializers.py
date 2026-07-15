from decimal import Decimal

from rest_framework import serializers

from .models import (
    CryptoWallet,
    CryptoTransaction,
    generate_wallet_address,
)


class CryptoWalletSerializer(serializers.ModelSerializer):
    """Read serializer for a user's crypto wallet."""

    class Meta:
        model = CryptoWallet
        fields = [
            "id",
            "wallet_address",
            "currency",
            "balance",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class CryptoDepositCreateSerializer(serializers.Serializer):
    """Validates input for creating a crypto deposit."""

    crypto_currency = serializers.ChoiceField(
        choices=["BTC", "ETH", "USDT"],
        help_text="The cryptocurrency being deposited.",
    )
    amount = serializers.DecimalField(max_digits=18, decimal_places=8)
    tx_hash = serializers.CharField(
        required=False, default="", allow_blank=True, max_length=128
    )
    wallet_address = serializers.CharField(
        required=False, default="", allow_blank=True, max_length=100
    )
    payment_screenshot = serializers.ImageField(
        required=False, allow_null=True,
        help_text="Optional screenshot of the payment proof.",
    )

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value


class CryptoTransactionSerializer(serializers.ModelSerializer):
    """Read serializer for crypto transactions."""

    class Meta:
        model = CryptoTransaction
        fields = [
            "id",
            "reference",
            "transaction_type",
            "crypto_currency",
            "amount",
            "usd_amount",
            "exchange_rate",
            "status",
            "tx_hash",
            "wallet_address",
            "payment_screenshot",
            "created_at",
        ]
        read_only_fields = fields


class CryptoTransactionAdminSerializer(serializers.ModelSerializer):
    """Admin serializer for crypto transactions with user info."""

    user_email = serializers.EmailField(source="wallet.user.email", read_only=True)
    user_full_name = serializers.SerializerMethodField()

    class Meta:
        model = CryptoTransaction
        fields = [
            "id",
            "reference",
            "user_email",
            "user_full_name",
            "transaction_type",
            "crypto_currency",
            "amount",
            "usd_amount",
            "exchange_rate",
            "status",
            "tx_hash",
            "wallet_address",
            "payment_screenshot",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_user_full_name(self, obj):
        user = obj.wallet.user
        return f"{user.first_name} {user.last_name}".strip()


class AdminProcessCryptoDepositSerializer(serializers.Serializer):
    """Validates admin complete/reject input for crypto deposits."""

    action = serializers.ChoiceField(
        choices=["complete", "reject"],
        help_text="'complete' to credit the bank account, 'reject' to deny it.",
    )
    rejection_reason = serializers.CharField(
        required=False,
        default="",
        allow_blank=True,
        help_text="Required when action is 'reject'.",
    )

    def validate(self, attrs):
        if attrs["action"] == "reject" and not attrs.get("rejection_reason", "").strip():
            raise serializers.ValidationError(
                {"rejection_reason": "A rejection reason is required when rejecting a deposit."}
            )
        return attrs


class CryptoWithdrawalCreateSerializer(serializers.Serializer):
    """Validates input for creating a crypto withdrawal."""

    crypto_currency = serializers.ChoiceField(
        choices=["BTC", "ETH", "USDT"],
        help_text="The cryptocurrency to withdraw.",
    )
    amount = serializers.DecimalField(max_digits=18, decimal_places=8)
    destination_address = serializers.CharField(
        max_length=100,
        help_text="The destination wallet address.",
    )

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value

    def validate_destination_address(self, value):
        if not value.strip():
            raise serializers.ValidationError("Destination address is required.")
        return value.strip()