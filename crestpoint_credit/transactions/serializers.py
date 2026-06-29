from decimal import Decimal

from rest_framework import serializers

from crestpoint_credit.accounts.models import BankAccount
from crestpoint_credit.core.exceptions import (
    InsufficientFundsError,
    AccountLockedError,
    InvalidTransferError,
)
from crestpoint_credit.accounts.models import User
from .models import Transaction, WithdrawalOTP, WithdrawalRequest, WithdrawalRequestStatus


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


# ---------------------------------------------------------------------------
# Withdrawal Request serializers
# ---------------------------------------------------------------------------


class GenerateWithdrawalOTPSerializer(serializers.Serializer):
    """Validates admin input for generating a withdrawal OTP."""

    user_id = serializers.IntegerField(help_text="ID of the user to generate an OTP for.")

    def validate_user_id(self, value):
        try:
            user = User.objects.get(pk=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("User does not exist.")
        self._user = user
        return value


class WithdrawalRequestCreateSerializer(serializers.Serializer):
    """Validates input for creating a new withdrawal request.

    Requires a valid OTP code that was generated by an admin for this user.
    """

    account_id = serializers.IntegerField(help_text="ID of the bank account to withdraw from.")
    amount = _AmountField(max_digits=15, decimal_places=2)
    otp_code = serializers.CharField(
        max_length=8,
        help_text="One-time OTP code provided by your account officer.",
    )
    description = serializers.CharField(required=False, default="", allow_blank=True)
    bank_name = serializers.CharField(required=False, default="", allow_blank=True, max_length=200)
    account_number = serializers.CharField(required=False, default="", allow_blank=True, max_length=50)
    routing_number = serializers.CharField(required=False, default="", allow_blank=True, max_length=50)

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
                "This account is frozen and cannot process withdrawal requests."
            )

        self._account = account
        return value

    def validate_otp_code(self, value):
        """Verify the OTP is valid, active, and belongs to the requesting user."""
        request = self.context.get("request")
        if not request:
            raise serializers.ValidationError("Authentication required.")

        code = value.strip().upper()
        try:
            otp = WithdrawalOTP.objects.get(
                user=request.user,
                code=code,
                is_used=False,
            )
        except WithdrawalOTP.DoesNotExist:
            raise serializers.ValidationError(
                "Invalid or expired OTP code. Please contact your account officer."
            )

        if otp.is_expired:
            # Mark expired OTPs as used to clean up
            otp.is_used = True
            otp.save(update_fields=["is_used"])
            raise serializers.ValidationError(
                "This OTP has expired. Please request a new one from your account officer."
            )

        self._otp = otp
        return code

    def validate(self, attrs):
        account = getattr(self, "_account", None)
        amount = attrs.get("amount")

        if account and amount:
            if account.balance < amount:
                raise serializers.ValidationError(
                    {"amount": "Insufficient funds for this withdrawal request."}
                )

            # Check for existing pending withdrawal requests for this account
            pending_exists = WithdrawalRequest.objects.filter(
                account=account,
                status=WithdrawalRequestStatus.PENDING,
            ).exists()
            if pending_exists:
                raise serializers.ValidationError(
                    {"non_field_errors": [
                        "You already have a pending withdrawal request for this account. "
                        "Please wait for it to be reviewed before submitting another."
                    ]}
                )

        return attrs


class WithdrawalRequestSerializer(serializers.ModelSerializer):
    """Read serializer for withdrawal requests (user-facing list/detail)."""

    cp_account_number = serializers.CharField(
        source="account.account_number", read_only=True
    )

    class Meta:
        model = WithdrawalRequest
        fields = [
            "id",
            "reference",
            "cp_account_number",
            "amount",
            "status",
            "description",
            "bank_name",
            "account_number",
            "routing_number",
            "rejection_reason",
            "created_at",
            "reviewed_at",
        ]
        read_only_fields = fields


class WithdrawalRequestAdminSerializer(serializers.ModelSerializer):
    """Extended serializer for admin views showing user info."""

    cp_account_number = serializers.CharField(
        source="account.account_number", read_only=True
    )
    user_email = serializers.EmailField(
        source="account.user.email", read_only=True
    )
    user_full_name = serializers.SerializerMethodField()
    reviewer_email = serializers.EmailField(
        source="reviewed_by.email", read_only=True, default=None
    )

    class Meta:
        model = WithdrawalRequest
        fields = [
            "id",
            "reference",
            "cp_account_number",
            "user_email",
            "user_full_name",
            "amount",
            "status",
            "description",
            "bank_name",
            "account_number",
            "routing_number",
            "rejection_reason",
            "reviewer_email",
            "created_at",
            "reviewed_at",
        ]
        read_only_fields = fields

    def get_user_full_name(self, obj):
        user = obj.account.user
        return f"{user.first_name} {user.last_name}".strip()


class AdminReviewWithdrawalSerializer(serializers.Serializer):
    """Validates admin approve/reject input."""

    action = serializers.ChoiceField(
        choices=["approve", "reject"],
        help_text="'approve' to process the withdrawal, 'reject' to deny it.",
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
                {"rejection_reason": "A rejection reason is required when rejecting a withdrawal request."}
            )
        return attrs