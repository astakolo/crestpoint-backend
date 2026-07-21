import logging
import re

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from .models import BankAccount, KYCDocument, User

logger = logging.getLogger("crestpoint_credit")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PASSWORD_PATTERN = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).+$"
)


def _validate_password_strength(password: str) -> str:
    """Raise ``ValidationError`` if *password* does not meet requirements.

    Requirements:
    * At least 8 characters.
    * At least one uppercase letter.
    * At least one lowercase letter.
    * At least one digit.
    """
    if len(password) < 8:
        raise serializers.ValidationError(
            _("Password must be at least 8 characters long.")
        )
    if not _PASSWORD_PATTERN.match(password):
        raise serializers.ValidationError(
            _(
                "Password must contain at least one uppercase letter, "
                "one lowercase letter, and one digit."
            )
        )
    return password


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class RegisterSerializer(serializers.ModelSerializer):
    """Serializer for user registration.

    Validates email uniqueness, password strength, and password confirmation
    before creating a new ``User``.
    """

    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    confirm_password = serializers.CharField(write_only=True, style={"input_type": "password"})

    class Meta:
        model = User
        fields = ["email", "first_name", "last_name", "phone", "password", "confirm_password"]

    def validate_email(self, value):
        qs = User.objects.filter(email__iexact=value)
        if qs.exists():
            raise serializers.ValidationError(_("A user with this email already exists."))
        return value

    def validate(self, attrs):
        password = attrs.get("password")
        confirm_password = attrs.get("confirm_password")

        if password != confirm_password:
            raise serializers.ValidationError(
                {"password": _("Password and confirm password do not match.")}
            )

        _validate_password_strength(password)

        return attrs

    def create(self, validated_data):
        validated_data.pop("confirm_password", None)
        password = validated_data.pop("password", None)

        user = User.objects.create_user(
            email=validated_data["email"],
            first_name=validated_data["first_name"],
            last_name=validated_data["last_name"],
            password=password,
            **{
                k: v for k, v in validated_data.items() if k in ("phone",)
            },
        )
        return user


# ---------------------------------------------------------------------------
# User Serializers
# ---------------------------------------------------------------------------


class UserSerializer(serializers.ModelSerializer):
    """Standard serializer for the authenticated user's own profile."""

    created_at = serializers.DateTimeField(read_only=True)
    kyc_status = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "phone",
            "role",
            "is_active",
            "is_verified",
            "kyc_status",
            "created_at",
        ]
        read_only_fields = ["id", "role", "is_active", "is_verified", "kyc_status", "created_at"]

    def get_kyc_status(self, obj):
        if hasattr(obj, "kyc_document"):
            return obj.kyc_document.status
        return "not_submitted"


class UserAdminSerializer(serializers.ModelSerializer):
    """Extended serializer for admin use – includes security-related fields.

    On **create** (POST) the optional ``password`` field lets an admin set the
    user's initial password.  On read/update the field is ignored.
    """

    is_locked = serializers.BooleanField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    password = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        min_length=8,
        help_text="Optional. Set initial password on user creation (min 8 chars).",
    )

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "phone",
            "role",
            "is_active",
            "is_verified",
            "password",
            "failed_login_attempts",
            "is_locked",
            "locked_until",
            "last_login_at",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "failed_login_attempts",
            "is_locked",
            "locked_until",
            "last_login_at",
            "created_at",
        ]

    def create(self, validated_data):
        """Hash the password (if provided) and create the user via the manager."""
        password = validated_data.pop("password", None)
        email = validated_data.get("email")
        first_name = validated_data.get("first_name", "")
        last_name = validated_data.get("last_name", "")

        if password:
            user = User.objects.create_user(
                email=email,
                first_name=first_name,
                last_name=last_name,
                password=password,
                **{k: v for k, v in validated_data.items()
                   if k in ("phone", "role", "is_active", "is_verified")},
            )
        else:
            user = User.objects.create_user(
                email=email,
                first_name=first_name,
                last_name=last_name,
                **{k: v for k, v in validated_data.items()
                   if k in ("phone", "role", "is_active", "is_verified")},
            )
        return user


# ---------------------------------------------------------------------------
# Bank Account Serializers
# ---------------------------------------------------------------------------


class BankAccountSerializer(serializers.ModelSerializer):
    """Serializer for listing / retrieving bank accounts."""

    masked_number = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = BankAccount
        fields = [
            "id",
            "account_number",
            "account_type",
            "balance",
            "currency",
            "is_active",
            "is_frozen",
            "masked_number",
            "created_at",
        ]
        read_only_fields = ["id", "account_number", "masked_number", "created_at", "balance"]

    def create(self, validated_data):
        """Auto-generate the account number on creation."""
        from crestpoint_credit.core.utils import generate_account_number

        validated_data["account_number"] = generate_account_number()
        return super().create(validated_data)


class BankAccountDetailSerializer(BankAccountSerializer):
    """Extended account serializer that includes the owner's email."""

    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta(BankAccountSerializer.Meta):
        fields = BankAccountSerializer.Meta.fields + ["user_email"]


class CreateAccountSerializer(serializers.ModelSerializer):
    """Minimal serializer for creating a new bank account.

    Enforces:
    * User must be verified (``is_verified=True``).
    * A user may have at most 5 bank accounts.
    """

    class Meta:
        model = BankAccount
        fields = ["account_type"]

    def validate_account_type(self, value):
        valid = [choice[0] for choice in BankAccount.ACCOUNT_TYPE_CHOICES]
        if value not in valid:
            raise serializers.ValidationError(_("Invalid account type."))
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None

        if user is None:
            raise serializers.ValidationError(_("Authentication required."))

        if not user.is_verified:
            raise serializers.ValidationError(
                _("You must verify your email before creating a bank account.")
            )

        max_accounts = 5
        if user.bank_accounts.filter(is_active=True).count() >= max_accounts:
            raise serializers.ValidationError(
                _("You can have a maximum of %(max)d active bank accounts.")
                % {"max": max_accounts}
            )

        return attrs

    def create(self, validated_data):
        from crestpoint_credit.core.utils import generate_account_number

        request = self.context["request"]
        validated_data["user"] = request.user
        validated_data["account_number"] = generate_account_number()
        return super().create(validated_data)


# ---------------------------------------------------------------------------
# KYC Serializers
# ---------------------------------------------------------------------------

KYC_MAX_FILE_SIZE = getattr(settings, "KYC_MAX_FILE_SIZE", 10 * 1024 * 1024)  # 10 MB


class KYCDocumentSerializer(serializers.ModelSerializer):
    """Serializer for uploading / viewing KYC documents."""

    class Meta:
        model = KYCDocument
        fields = [
            "id",
            "document_type",
            "document_number",
            "front_image",
            "back_image",
            "status",
            "submitted_at",
            "rejection_reason",
        ]
        read_only_fields = ["id", "status", "submitted_at", "rejection_reason"]

    def validate_document_number(self, value):
        """Validate document number based on document type."""
        doc_type = self.initial_data.get("document_type")

        if doc_type == "passport":
            # Passport numbers are typically alphanumeric, 6-15 characters
            if not re.match(r"^[A-Za-z0-9]{6,15}$", value.strip()):
                raise serializers.ValidationError(
                    _("Invalid passport number format. Must be 6-15 alphanumeric characters.")
                )
        elif doc_type == "national_id":
            # National ID: numeric, typically 8-20 digits
            if not re.match(r"^\d{8,20}$", value.strip()):
                raise serializers.ValidationError(
                    _("Invalid national ID format. Must be 8-20 digits.")
                )
        elif doc_type == "drivers_license":
            # Driver's license: alphanumeric, 5-20 characters
            if not re.match(r"^[A-Za-z0-9]{5,20}$", value.strip()):
                raise serializers.ValidationError(
                    _("Invalid driver's license number format. Must be 5-20 alphanumeric characters.")
                )

        return value.strip()

    def validate_front_image(self, value):
        """Check file size for front image."""
        if value.size > KYC_MAX_FILE_SIZE:
            max_mb = KYC_MAX_FILE_SIZE // (1024 * 1024)
            raise serializers.ValidationError(
                _("File size must not exceed %(max)d MB.") % {"max": max_mb}
            )
        return value

    def validate_back_image(self, value):
        """Check file size for back image (if provided)."""
        if value is not None and value.size > KYC_MAX_FILE_SIZE:
            max_mb = KYC_MAX_FILE_SIZE // (1024 * 1024)
            raise serializers.ValidationError(
                _("File size must not exceed %(max)d MB.") % {"max": max_mb}
            )
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None

        if user is None:
            raise serializers.ValidationError(_("Authentication required."))

        # Check if user already has an approved KYC
        if hasattr(user, "kyc_document") and user.kyc_document.status == "approved":
            raise serializers.ValidationError(
                _("You already have an approved KYC document.")
            )

        return attrs


class KYCReviewSerializer(serializers.Serializer):
    """Serializer for admin/support KYC review actions."""

    status = serializers.ChoiceField(choices=["approved", "rejected"], write_only=True)
    rejection_reason = serializers.CharField(required=False, allow_blank=True, write_only=True)

    def validate(self, attrs):
        if attrs["status"] == "rejected" and not attrs.get("rejection_reason"):
            raise serializers.ValidationError(
                {"rejection_reason": _("A rejection reason is required when rejecting a KYC document.")}
            )
        return attrs


# ---------------------------------------------------------------------------
# Balance Adjustment (Admin)
# ---------------------------------------------------------------------------


class BalanceAdjustmentSerializer(serializers.Serializer):
    """Serializer for admin balance adjustment.

    Supports both positive (credit) and negative (debit) adjustments.
    A reason is required for audit trail purposes.
    """

    account_id = serializers.IntegerField(help_text="ID of the bank account to adjust.")
    amount = serializers.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text="Amount to adjust. Positive to credit, negative to debit.",
    )
    reason = serializers.CharField(
        max_length=500,
        help_text="Reason for the balance adjustment (required for audit trail).",
    )

    def validate_account_id(self, value):
        try:
            account = BankAccount.objects.select_related("user").get(pk=value)
        except BankAccount.DoesNotExist:
            raise serializers.ValidationError("Bank account does not exist.")
        if not account.is_active:
            raise serializers.ValidationError("This account is not active.")
        self._account = account
        return value

    def validate_amount(self, value):
        if value == 0:
            raise serializers.ValidationError("Amount cannot be zero.")
        return value

    def validate(self, attrs):
        account = getattr(self, "_account", None)
        amount = attrs.get("amount")
        if account and amount and amount < 0:
            # For debits, check sufficient funds
            if account.balance < abs(amount):
                raise serializers.ValidationError(
                    {"amount": "Insufficient funds for this adjustment."}
                )
        return attrs


# ---------------------------------------------------------------------------
# Admin Send Notification
# ---------------------------------------------------------------------------


class AdminNotificationSerializer(serializers.Serializer):
    """Serializer for admin to send notifications to one or more users."""

    user_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
        max_length=100,
        help_text="List of user IDs to send the notification to.",
    )
    title = serializers.CharField(max_length=200)
    message = serializers.CharField(max_length=2000)
    notification_type = serializers.ChoiceField(
        choices=["system", "security", "account"],
        default="system",
    )


# ---------------------------------------------------------------------------
# Batch Action
# ---------------------------------------------------------------------------


class BatchActionSerializer(serializers.Serializer):
    """Serializer for batch user actions (lock/unlock)."""

    user_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
        max_length=200,
        help_text="List of user IDs.",
    )


# ---------------------------------------------------------------------------
# Change Password
# ---------------------------------------------------------------------------


class ChangePasswordSerializer(serializers.Serializer):
    """Serializer for password change requests."""

    old_password = serializers.CharField(write_only=True, style={"input_type": "password"})
    new_password = serializers.CharField(write_only=True, style={"input_type": "password"})
    confirm_new_password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError(_("Current password is incorrect."))
        return value

    def validate(self, attrs):
        new_password = attrs.get("new_password")
        confirm_new_password = attrs.get("confirm_new_password")
        old_password = attrs.get("old_password")

        if new_password != confirm_new_password:
            raise serializers.ValidationError(
                {"new_password": _("New password and confirmation do not match.")}
            )

        if new_password == old_password:
            raise serializers.ValidationError(
                {"new_password": _("New password must be different from the current password.")}
            )

        _validate_password_strength(new_password)

        return attrs

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        logger.info("Password changed for user %s", user.email)
        return user
