from rest_framework import serializers

from crestpoint_credit.accounts.models import BankAccount
from .models import Payment, PaymentMethod, PaymentProvider


# ---------------------------------------------------------------------------
# Input serializers
# ---------------------------------------------------------------------------


class InitiatePaymentSerializer(serializers.Serializer):
    """Validates input for initiating a new payment."""

    account_id = serializers.IntegerField(write_only=True)
    amount = serializers.DecimalField(max_digits=15, decimal_places=2)
    payment_method = serializers.ChoiceField(choices=PaymentMethod.choices)
    provider = serializers.ChoiceField(
        choices=PaymentProvider.choices,
        required=False,
        default=PaymentProvider.BANK_MOCK,
    )
    metadata = serializers.JSONField(required=False, default=dict)

    def validate_amount(self, value):
        if value is None or value <= 0:
            raise serializers.ValidationError(
                "Amount must be greater than zero."
            )
        return value

    def validate_account_id(self, value):
        request = self.context.get("request")
        try:
            account = BankAccount.objects.get(pk=value)
        except BankAccount.DoesNotExist:
            raise serializers.ValidationError("Account does not exist.")

        if request and account.user_id != request.user.id:
            raise serializers.ValidationError(
                "This account does not belong to you."
            )

        if not account.is_active:
            raise serializers.ValidationError(
                "This account is not active."
            )

        if account.is_frozen:
            raise serializers.ValidationError(
                "This account is frozen and cannot process payments."
            )

        self._account = account
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        # Ensure the account object is available
        if not hasattr(self, "_account"):
            # If validate_account_id hasn't been called yet (e.g. partial),
            # attempt a manual lookup.
            request = self.context.get("request")
            account_id = attrs.get("account_id")
            try:
                account = BankAccount.objects.get(pk=account_id)
                if request and account.user_id != request.user.id:
                    raise serializers.ValidationError(
                        {"account_id": "This account does not belong to you."}
                    )
                self._account = account
            except BankAccount.DoesNotExist:
                pass
        return attrs


# ---------------------------------------------------------------------------
# Read serializers
# ---------------------------------------------------------------------------


class PaymentSerializer(serializers.ModelSerializer):
    """Used for list views and operation responses."""

    class Meta:
        model = Payment
        fields = [
            "id",
            "reference",
            "amount",
            "currency",
            "payment_method",
            "provider",
            "status",
            "error_message",
            "completed_at",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "reference",
            "status",
            "error_message",
            "completed_at",
        ]


class PaymentDetailSerializer(PaymentSerializer):
    """Extended serializer for detail / admin views."""

    class Meta(PaymentSerializer.Meta):
        fields = PaymentSerializer.Meta.fields + [
            "provider_payment_id",
            "provider_response",
            "metadata",
        ]


# ---------------------------------------------------------------------------
# Refund serializer
# ---------------------------------------------------------------------------


class RefundSerializer(serializers.Serializer):
    """Validates input for refunding a payment."""

    reason = serializers.CharField(required=False, default="", allow_blank=True)
