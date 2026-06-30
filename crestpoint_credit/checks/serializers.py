from rest_framework import serializers

from crestpoint_credit.accounts.models import BankAccount
from .models import CheckDeposit


class CheckDepositCreateSerializer(serializers.Serializer):
    """Validates input for creating a check deposit (multipart form data)."""

    account_id = serializers.IntegerField(help_text="ID of the bank account to deposit into.")
    amount = serializers.DecimalField(max_digits=15, decimal_places=2)
    check_number = serializers.CharField(
        required=False, default="", allow_blank=True, max_length=50
    )
    front_image = serializers.ImageField(help_text="Front image of the check.")
    back_image = serializers.ImageField(help_text="Back image of the check.")

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value

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
            raise serializers.ValidationError("This account is frozen.")
        self._account = account
        return value


class CheckDepositSerializer(serializers.ModelSerializer):
    """Read serializer for a user's check deposit."""

    account_number = serializers.CharField(source="account.account_number", read_only=True)

    class Meta:
        model = CheckDeposit
        fields = [
            "id",
            "reference",
            "account_number",
            "check_number",
            "amount",
            "front_image",
            "back_image",
            "status",
            "processed_at",
            "failure_reason",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class CheckDepositDetailSerializer(CheckDepositSerializer):
    """Extended serializer for detail views."""

    class Meta(CheckDepositSerializer.Meta):
        fields = CheckDepositSerializer.Meta.fields + ["metadata"]


class CheckDepositAdminSerializer(serializers.ModelSerializer):
    """Admin serializer for check deposits with user info."""

    account_number = serializers.CharField(source="account.account_number", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_full_name = serializers.SerializerMethodField()

    class Meta:
        model = CheckDeposit
        fields = [
            "id",
            "reference",
            "user_email",
            "user_full_name",
            "account_number",
            "check_number",
            "amount",
            "front_image",
            "back_image",
            "status",
            "processed_at",
            "failure_reason",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_user_full_name(self, obj):
        return f"{obj.user.first_name} {obj.user.last_name}".strip()


class AdminProcessCheckDepositSerializer(serializers.Serializer):
    """Validates admin approve/reject input for check deposits."""

    action = serializers.ChoiceField(
        choices=["approve", "reject"],
        help_text="'approve' to process the deposit, 'reject' to deny it.",
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
                {"rejection_reason": "A rejection reason is required when rejecting a check deposit."}
            )
        return attrs