"""Serializers for authentication, token management, and password reset."""

import logging
import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

logger = logging.getLogger("crestpoint_credit")

User = get_user_model()


# ---------------------------------------------------------------------------
# Login Serializer
# ---------------------------------------------------------------------------


class LoginSerializer(serializers.Serializer):
    """Validate login credentials with failed-login tracking and account locking."""

    email = serializers.EmailField(write_only=True)
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate(self, attrs):
        """Authenticate the user and enforce account-lockout policy.

        Returns:
            dict with the authenticated ``User`` instance keyed as ``user``.

        Raises:
            AuthenticationFailed: On invalid credentials, inactive account, or
                locked account.
        """
        email = attrs.get("email").strip().lower()
        password = attrs.get("password")

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            logger.warning("Login attempt for non-existent email: %s", email)
            # Do NOT reveal whether the email exists – raise a generic error.
            raise AuthenticationFailed(
                "Invalid email or password.",
                code="authentication_failed",
            )

        # Check whether the account is currently locked.
        if user.is_locked:
            logger.warning("Locked account login attempt: %s", email)
            raise AuthenticationFailed(
                "Account temporarily locked. Please try again later.",
                code="account_locked",
            )

        # Verify the password.
        if not user.check_password(password):
            user.increment_failed_login()
            logger.warning(
                "Failed login attempt (%d) for: %s",
                user.failed_login_attempts,
                email,
            )
            # If the increment just pushed the count over the threshold the
            # account will have been locked inside ``increment_failed_login``.
            if user.is_locked:
                raise AuthenticationFailed(
                    "Account temporarily locked. Please try again later.",
                    code="account_locked",
                )
            raise AuthenticationFailed(
                "Invalid email or password.",
                code="authentication_failed",
            )

        if not user.is_active:
            logger.warning("Inactive account login attempt: %s", email)
            raise AuthenticationFailed(
                "This account has been deactivated.",
                code="account_inactive",
            )

        # Successful authentication – reset the failed-login counter.
        user.reset_failed_login()

        attrs["user"] = user
        return attrs


# ---------------------------------------------------------------------------
# JWT Token Obtain Pair Serializer (with failed-login tracking)
# ---------------------------------------------------------------------------


class TokenObtainPairSerializer(TokenObtainPairSerializer):
    """Extended JWT serializer that adds failed-login tracking and enriches the
    response payload with user metadata.
    """

    username_field = User.USERNAME_FIELD  # 'email'

    def validate(self, attrs):
        """Authenticate, track failed logins, and return enriched tokens."""
        email = attrs.get(self.username_field).strip().lower()

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            logger.warning("JWT token attempt for non-existent email: %s", email)
            raise AuthenticationFailed(
                "Invalid email or password.",
                code="authentication_failed",
            )

        # Account lock check.
        if user.is_locked:
            logger.warning("Locked account JWT attempt: %s", email)
            raise AuthenticationFailed(
                "Account temporarily locked. Please try again later.",
                code="account_locked",
            )

        # Password verification.
        password = attrs.get("password")
        if not user.check_password(password):
            user.increment_failed_login()
            logger.warning(
                "Failed JWT login (%d) for: %s",
                user.failed_login_attempts,
                email,
            )
            if user.is_locked:
                raise AuthenticationFailed(
                    "Account temporarily locked. Please try again later.",
                    code="account_locked",
                )
            raise AuthenticationFailed(
                "Invalid email or password.",
                code="authentication_failed",
            )

        if not user.is_active:
            raise AuthenticationFailed(
                "This account has been deactivated.",
                code="account_inactive",
            )

        # Success – reset counter.
        user.reset_failed_login()

        # Let the parent class generate the raw tokens.
        data = super().validate(attrs)

        # Enrich the response with user information.
        data["user"] = {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role,
        }

        return data


# ---------------------------------------------------------------------------
# Password Reset – Request
# ---------------------------------------------------------------------------


class PasswordResetRequestSerializer(serializers.Serializer):
    """Validate the email address and generate a time-limited reset token
    stored in the cache.
    """

    email = serializers.EmailField(write_only=True)

    def validate(self, attrs):
        email = attrs.get("email").strip().lower()

        # Always return 200 for security – never reveal whether the email exists.
        # Only generate a token if the user actually exists so the email is sent.
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            logger.info("Password reset requested for non-existent email: %s", email)
            # Return the email so the view can respond generically.
            attrs["user"] = None
            attrs["token"] = None
            return attrs

        token = secrets.token_urlsafe(32)
        cache_key = f"password_reset_{email}"
        cache.set(cache_key, token, timeout=3600)  # 1 hour

        logger.info("Password reset token generated for: %s", email)
        attrs["user"] = user
        attrs["token"] = token
        return attrs


# ---------------------------------------------------------------------------
# Password Reset – Confirm
# ---------------------------------------------------------------------------


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Validate the reset token and apply the new password."""

    email = serializers.EmailField(write_only=True)
    token = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs.get("email").strip().lower()
        token = attrs.get("token")
        new_password = attrs.get("new_password")
        confirm_password = attrs.get("confirm_password")

        if new_password != confirm_password:
            raise serializers.ValidationError(
                {"confirm_password": "Passwords do not match."},
                code="password_mismatch",
            )

        # Verify the cached token.
        cache_key = f"password_reset_{email}"
        cached_token = cache.get(cache_key)

        if cached_token is None or cached_token != token:
            logger.warning("Invalid or expired password reset token for: %s", email)
            raise serializers.ValidationError(
                {"token": "Invalid or expired reset token."},
                code="invalid_token",
            )

        # Retrieve the user.
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError(
                {"email": "No account found with this email address."},
                code="user_not_found",
            )

        # Validate password strength via Django's built-in validators.
        try:
            from django.contrib.auth.password_validation import validate_password

            validate_password(new_password, user=user)
        except serializers.ValidationError as exc:
            raise serializers.ValidationError({"new_password": exc.messages})

        attrs["user"] = user
        return attrs

    def save(self):
        """Apply the new password and clean up."""
        user = self.validated_data["user"]
        email = self.validated_data["email"]

        user.set_password(self.validated_data["new_password"])
        user.reset_failed_login()
        user.save()

        # Invalidate the token so it cannot be reused.
        cache_key = f"password_reset_{email}"
        cache.delete(cache_key)

        logger.info("Password reset completed for: %s", email)
