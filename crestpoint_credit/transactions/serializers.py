from decimal import Decimal

from rest_framework import serializers

from crestpoint_credit.accounts.models import BankAccount
from crestpoint_credit.core.exceptions import (
    InsufficientFundsError,
    AccountLockedError,
    InvalidTransferError,
)
from .models import Transaction


# ---------------------------------------------------------------------------
# Base field shared across operation serializers
# ---------------------------------------------------------------------------

class _AmountField(serializers.DecimalField):
    """Validates that amount is strictly positive."""

    def validate_empty_values(self, data):
        (is_empty, data) = super().validate_empty_values(data)
        if not is_empty and data is not None:
            if isinstance(data, str):
                try:
                    data = Decimal(data)
                except Exception:
                    pass
            if data <= 0:
                raise serializers.ValidationError("Amount must be greater than zero.")
        return is_empty, data


# ---------------------------------------------------------------------------
# Operation serializers (input only)
# ---------------------------------------------------------------------------

class DepositSerializer(serializers.Serializer):
    account_id = serializers.IntegerField()
    amount = _AmountField(max_digits=15, decimal_places=2)
    description = serializers.CharField(required=False, default="", allow_blank=True)

    def validate_account_id(self, value):
        request = self.context.get("request")
        try:
            account = BankAccount.objects.get(pk=value)
        except BankAccount.DoesNotExist:
            raise serializers.ValidationError("Account does not exist.")

        if request and account.user_id != request.user.id:
            raise serializers.ValidationError("This account does not belong to you.")

        if not account.is_active:
            raise serializers.ValidationError("This account is not active.")

        if account.is_frozen:
            raise serializers.ValidationError(
                "This account is frozen and cannot process transactions."
            )

        self._account = account
        return value


class WithdrawalSerializer(DepositSerializer):
    """Reuses deposit validation and adds a balance check."""

    def validate(self, attrs):
        attrs = super().validate(attrs)
        account = self._account
        amount = attrs["amount"]

        if account.balance < amount:
            raise serializers.ValidationError(
                {"amount": "Insufficient funds for this withdrawal."}
            )
        return attrs


class TransferSerializer(serializers.Serializer):
    sender_account_id = serializers.IntegerField()
    recipient_account_number = serializers.CharField(max_length=30)
    amount = _AmountField(max_digits=15, decimal_places=2)
    description = serializers.CharField(required=False, default="", allow_blank=True)

    def validate_sender_account_id(self, value):
        request = self.context.get("request")
        try:
            account = BankAccount.objects.get(pk=value)
        except BankAccount.DoesNotExist:
            raise serializers.ValidationError("Sender account does not exist.")

        if request and account.user_id != request.user.id:
            raise serializers.ValidationError(
                "This account does not belong to you."
            )

        if not account.is_active:
            raise serializers.ValidationError("Sender account is not active.")

        if account.is_frozen:
            raise serializers.ValidationError(
                "Sender account is frozen and cannot process transactions."
            )

        self._sender_account = account
        return value

    def validate_recipient_account_number(self, value):
        try:
            account = BankAccount.objects.get(account_number=value)
        except BankAccount.DoesNotExist:
            raise serializers.ValidationError("Recipient account does not exist.")

        if not account.is_active:
            raise serializers.ValidationError("Recipient account is not active.")

        self._recipient_account = account
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)

        sender = getattr(self, "_sender_account", None)
        recipient = getattr(self, "_recipient_account", None)

        if sender and recipient:
            if sender.account_number == recipient.account_number:
                raise serializers.ValidationError(
                    {"recipient_account_number": "Cannot transfer to the same account."}
                )
            if sender.balance < attrs["amount"]:
                raise serializers.ValidationError(
                    {"amount": "Insufficient funds for this transfer."}
                )

        return attrs


# ---------------------------------------------------------------------------
# Read serializers
# ---------------------------------------------------------------------------

class AccountNumberField(serializers.RelatedField):
    """Serializes a BankAccount as its account_number string."""

    def to_representation(self, value):
        return value.account_number

    def to_internal_value(self, data):
        raise NotImplementedError("This field is read-only.")


class TransactionSerializer(serializers.ModelSerializer):
    """Used for list views and operation responses."""

    account = AccountNumberField(read_only=True)

    class Meta:
        model = Transaction
        fields = [
            "id",
            "reference",
            "transaction_type",
            "status",
            "account",
            "amount",
            "description",
            "balance_before",
            "balance_after",
            "is_flagged",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "reference",
            "status",
            "balance_before",
            "balance_after",
            "created_at",
        ]


class TransactionDetailSerializer(TransactionSerializer):
    """Extended serializer for detail / admin views."""

    recipient_account = AccountNumberField(read_only=True)

    class Meta(TransactionSerializer.Meta):
        fields = TransactionSerializer.Meta.fields + [
            "recipient_account",
            "metadata",
        ]
