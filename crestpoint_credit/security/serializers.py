"""Serializers for authentication, token management, and password reset."""

import logging
import random
import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.mail import send_mail
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


# ---------------------------------------------------------------------------
# Email OTP – Send
# ---------------------------------------------------------------------------


class OTPEmailSerializer(serializers.Serializer):
    """Validate email and generate + send a 6-digit OTP code."""

    email = serializers.EmailField(write_only=True)

    def validate(self, attrs):
        email = attrs.get("email").strip().lower()

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError(
                {"email": "No account found with this email address."},
                code="user_not_found",
            )

        # Generate a 6-digit OTP
        otp = f"{random.randint(100000, 999999)}"

        # Store in cache with 5-minute TTL
        cache_key = f"otp_{email}"
        cache.set(cache_key, otp, timeout=300)  # 5 minutes

        # Track attempts (max 5)
        attempts_key = f"otp_attempts_{email}"
        cache.set(attempts_key, 0, timeout=300)

        attrs["user"] = user
        attrs["otp"] = otp
        attrs["email"] = email
        return attrs

    def save(self):
        """Send the OTP email (synchronous — called from a Celery task or directly)."""
        email = self.validated_data["email"]
        otp = self.validated_data["otp"]

        try:
            send_mail(
                subject="CrestPoint Credit - Your Verification Code",
                message=(
                    f"Your verification code is: {otp}\n\n"
                    "This code expires in 5 minutes.\n\n"
                    "If you didn't request this, please ignore this email.\n\n"
                    "CrestPoint Credit Security Team"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )
            logger.info("OTP sent to: %s", email)
        except Exception:
            logger.exception("Failed to send OTP to: %s", email)
            raise serializers.ValidationError(
                {"email": "Failed to send verification email. Please try again."},
                code="email_send_failed",
            )


class OTPEmailRegisterSerializer(serializers.Serializer):
    """Generate + send a 6-digit OTP to a given email (for signup — user may not exist yet)."""

    email = serializers.EmailField(write_only=True)

    def validate(self, attrs):
        email = attrs.get("email").strip().lower()

        # For signup, we allow OTP to be sent even if user doesn't exist yet
        # But check if email is already taken
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError(
                {"email": "An account with this email already exists."},
                code="email_taken",
            )

        otp = f"{random.randint(100000, 999999)}"
        cache_key = f"otp_register_{email}"
        cache.set(cache_key, otp, timeout=300)

        attempts_key = f"otp_register_attempts_{email}"
        cache.set(attempts_key, 0, timeout=300)

        attrs["otp"] = otp
        attrs["email"] = email
        return attrs

    def save(self):
        email = self.validated_data["email"]
        otp = self.validated_data["otp"]
        try:
            send_mail(
                subject="CrestPoint Credit - Verify Your Email",
                message=(
                    f"Your verification code is: {otp}\n\n"
                    "This code expires in 5 minutes.\n\n"
                    "If you didn't request this, please ignore this email.\n\n"
                    "CrestPoint Credit Security Team"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )
            logger.info("Registration OTP sent to: %s", email)
        except Exception:
            logger.exception("Failed to send registration OTP to: %s", email)
            raise serializers.ValidationError(
                {"email": "Failed to send verification email. Please try again."},
                code="email_send_failed",
            )


# ---------------------------------------------------------------------------
# Email OTP – Verify
# ---------------------------------------------------------------------------


class OTPVerifySerializer(serializers.Serializer):
    """Verify a 6-digit OTP code for login."""

    email = serializers.EmailField(write_only=True)
    otp = serializers.CharField(write_only=True, min_length=6, max_length=6)

    def validate(self, attrs):
        email = attrs.get("email").strip().lower()
        otp = attrs.get("otp").strip()

        cache_key = f"otp_{email}"
        cached_otp = cache.get(cache_key)

        if not cached_otp:
            raise serializers.ValidationError(
                {"otp": "Verification code has expired. Please request a new one."},
                code="otp_expired",
            )

        # Check attempt limit
        attempts_key = f"otp_attempts_{email}"
        attempts = cache.get(attempts_key, 0)
        if attempts >= 5:
            cache.delete(cache_key)
            cache.delete(attempts_key)
            raise serializers.ValidationError(
                {"otp": "Too many failed attempts. Please request a new code."},
                code="otp_max_attempts",
            )

        if cached_otp != otp:
            cache.set(attempts_key, attempts + 1, timeout=300)
            remaining = 5 - (attempts + 1)
            raise serializers.ValidationError(
                {"otp": f"Invalid verification code. {remaining} attempt(s) remaining."},
                code="otp_invalid",
            )

        # Valid OTP — consume it
        cache.delete(cache_key)
        cache.delete(attempts_key)

        attrs["email"] = email
        return attrs


class OTPVerifyRegisterSerializer(serializers.Serializer):
    """Verify a 6-digit OTP code for registration."""

    email = serializers.EmailField(write_only=True)
    otp = serializers.CharField(write_only=True, min_length=6, max_length=6)

    def validate(self, attrs):
        email = attrs.get("email").strip().lower()
        otp = attrs.get("otp").strip()

        cache_key = f"otp_register_{email}"
        cached_otp = cache.get(cache_key)

        if not cached_otp:
            raise serializers.ValidationError(
                {"otp": "Verification code has expired. Please request a new one."},
                code="otp_expired",
            )

        attempts_key = f"otp_register_attempts_{email}"
        attempts = cache.get(attempts_key, 0)
        if attempts >= 5:
            cache.delete(cache_key)
            cache.delete(attempts_key)
            raise serializers.ValidationError(
                {"otp": "Too many failed attempts. Please request a new code."},
                code="otp_max_attempts",
            )

        if cached_otp != otp:
            cache.set(attempts_key, attempts + 1, timeout=300)
            remaining = 5 - (attempts + 1)
            raise serializers.ValidationError(
                {"otp": f"Invalid verification code. {remaining} attempt(s) remaining."},
                code="otp_invalid",
            )

        cache.delete(cache_key)
        cache.delete(attempts_key)

        attrs["email"] = email
        return attrs