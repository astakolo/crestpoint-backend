from decimal import Decimal

from rest_framework import serializers

from crestpoint_credit.accounts.models import BankAccount
from .models import (
    BillerCategory,
    Biller,
    BillerSaved,
    BillPayment,
)


class BillerCategorySerializer(serializers.ModelSerializer):
    """Read serializer for biller categories."""

    class Meta:
        model = BillerCategory
        fields = [
            "id",
            "name",
            "icon",
        ]
        read_only_fields = fields


class BillerSerializer(serializers.ModelSerializer):
    """Read serializer for billers."""

    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = Biller
        fields = [
            "id",
            "name",
            "category",
            "category_name",
            "account_number",
            "biller_code",
        ]
        read_only_fields = fields


class BillerSavedSerializer(serializers.ModelSerializer):
    """Read serializer for a user's saved billers."""

    biller_name = serializers.CharField(source="biller.name", read_only=True)
    biller_code = serializers.CharField(source="biller.biller_code", read_only=True)
    category_name = serializers.CharField(source="biller.category.name", read_only=True)

    class Meta:
        model = BillerSaved
        fields = [
            "id",
            "biller",
            "biller_name",
            "biller_code",
            "category_name",
            "nickname",
            "account_number",
            "created_at",
        ]
        read_only_fields = fields


class SaveBillerSerializer(serializers.Serializer):
    """Validates input for saving a biller."""

    biller_id = serializers.IntegerField(help_text="ID of the biller to save.")
    nickname = serializers.CharField(
        required=False, default="", allow_blank=True, max_length=100
    )
    account_number = serializers.CharField(max_length=100)

    def validate_biller_id(self, value):
        try:
            biller = Biller.objects.get(pk=value)
        except Biller.DoesNotExist:
            raise serializers.ValidationError("Biller does not exist.")
        if not biller.is_active:
            raise serializers.ValidationError("This biller is currently inactive.")
        self._biller = biller
        return value


class PayBillSerializer(serializers.Serializer):
    """Validates input for paying a bill."""

    biller_id = serializers.IntegerField(help_text="ID of the biller to pay.")
    account_id = serializers.IntegerField(help_text="Bank account to debit funds from.")
    amount = serializers.DecimalField(max_digits=15, decimal_places=2)
    narration = serializers.CharField(required=False, default="", allow_blank=True)

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value

    def validate_biller_id(self, value):
        try:
            biller = Biller.objects.get(pk=value)
        except Biller.DoesNotExist:
            raise serializers.ValidationError("Biller does not exist.")
        if not biller.is_active:
            raise serializers.ValidationError("This biller is currently inactive.")
        self._biller = biller
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
                {"amount": "Insufficient funds for this bill payment."}
            )
        return attrs


class BillPaymentSerializer(serializers.ModelSerializer):
    """Read serializer for a user's bill payment."""

    biller_name = serializers.CharField(source="biller.name", read_only=True)
    account_number = serializers.CharField(source="account.account_number", read_only=True)

    class Meta:
        model = BillPayment
        fields = [
            "id",
            "reference",
            "biller_name",
            "account_number",
            "amount",
            "status",
            "narration",
            "created_at",
        ]
        read_only_fields = fields


class BillPaymentDetailSerializer(BillPaymentSerializer):
    """Extended serializer for detail views."""

    class Meta(BillPaymentSerializer.Meta):
        fields = BillPaymentSerializer.Meta.fields + ["metadata"]


class BillPaymentAdminSerializer(serializers.ModelSerializer):
    """Admin serializer for bill payments with user info."""

    biller_name = serializers.CharField(source="biller.name", read_only=True)
    account_number = serializers.CharField(source="account.account_number", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_full_name = serializers.SerializerMethodField()

    class Meta:
        model = BillPayment
        fields = [
            "id",
            "reference",
            "user_email",
            "user_full_name",
            "biller_name",
            "account_number",
            "amount",
            "status",
            "narration",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_user_full_name(self, obj):
        return f"{obj.user.first_name} {obj.user.last_name}".strip()