"""Authentication and password-reset views for the security app."""

import logging

from django.conf import settings
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status, views
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from rest_framework_simplejwt.tokens import RefreshToken

from .throttling import LoginRateThrottle
from .serializers import (
    LoginSerializer,
    OTPVerifySerializer,
    OTPVerifyRegisterSerializer,
    OTPEmailRegisterSerializer,
    OTPEmailSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
)

logger = logging.getLogger("crestpoint_credit")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _set_auth_cookies(response, access_token, refresh_token):
    """Attach JWT access and refresh tokens as httpOnly cookies."""
    secure = not settings.DEBUG

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=secure,
        samesite="Lax",
        path="/",
        max_age=900,  # 15 minutes
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=secure,
        samesite="Lax",
        path="/",
        max_age=604800,  # 7 days
    )


def _delete_auth_cookies(response):
    """Remove JWT cookies from the response."""
    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="refresh_token", path="/")


# ---------------------------------------------------------------------------
# Login View
# ---------------------------------------------------------------------------


class LoginView(views.APIView):
    """
    Authenticate a user and return JWT tokens.

    Accepts ``email`` and ``password`` in the request body.  On success the
    tokens are set as httpOnly cookies **and** returned in the JSON body so
    that pure-API clients can also consume them.
    """

    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]

    def post(self, request, *args, **kwargs):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data["user"]

        # Generate JWT tokens.
        refresh = RefreshToken.for_user(user)

        # Inject role into the access token payload.
        access = refresh.access_token
        access["role"] = user.role

        response_data = {
            "access": str(access),
            "refresh": str(refresh),
            "user": {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "role": user.role,
            },
        }

        response = Response(response_data, status=status.HTTP_200_OK)
        _set_auth_cookies(response, str(access), str(refresh))

        logger.info("Successful login for user: %s (role=%s)", user.email, user.role)
        return response


# ---------------------------------------------------------------------------
# Logout View
# ---------------------------------------------------------------------------


class LogoutView(views.APIView):
    """
    Blacklist the current refresh token and clear auth cookies.

    Accepts an optional ``refresh`` field in the request body.  If not
    provided the refresh token is read from the cookie.
    """

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        refresh_token = request.data.get("refresh")

        # Fall back to the cookie if the body doesn't contain the token.
        if not refresh_token:
            refresh_token = request.COOKIES.get("refresh_token")

        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                # Blacklist the outstanding token entry.
                outstanding = OutstandingToken.objects.filter(
                    token__icontains=str(token),
                ).first()
                if outstanding:
                    BlacklistedToken.objects.get_or_create(token=outstanding)
                    logger.info("Refresh token blacklisted during logout")
            except TokenError:
                logger.warning("Invalid refresh token submitted during logout")

        response = Response(
            {"message": "Successfully logged out"},
            status=status.HTTP_200_OK,
        )
        _delete_auth_cookies(response)
        return response


# ---------------------------------------------------------------------------
# Token Refresh View
# ---------------------------------------------------------------------------


class TokenRefreshView(views.APIView):
    """
    Generate a new access token from a refresh token.

    The refresh token may be supplied in the request body (``refresh`` key)
    **or** as an httpOnly cookie.
    """

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        refresh_token = request.data.get("refresh") or request.COOKIES.get(
            "refresh_token"
        )

        if not refresh_token:
            return Response(
                {"error": "Refresh token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            refresh = RefreshToken(refresh_token)
        except TokenError as exc:
            return Response(
                {"error": f"Invalid refresh token: {exc}"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # When BLACKLIST_AFTER_ROTATION is enabled the old token is
        # automatically blacklisted by ``refresh.access_token``.
        access = refresh.access_token

        # Inject role into the new access token.
        # request.user is NOT authenticated here (AllowAny), so look up
        # the user from the JWT payload instead.
        try:
            from crestpoint_credit.accounts.models import User
            user_obj = User.objects.get(id=refresh.payload.get("user_id"))
            access["role"] = user_obj.role
        except Exception:
            pass

        response_data = {
            "access": str(access),
            "refresh": str(refresh),
        }

        response = Response(response_data, status=status.HTTP_200_OK)
        # MUST set BOTH cookies — ROTATE_REFRESH_TOKENS blacklists the old
        # refresh token, so the new one must be stored in the cookie.
        _set_auth_cookies(response, str(access), str(refresh))
        return response


# ---------------------------------------------------------------------------
# Password Reset – Request
# ---------------------------------------------------------------------------


class PasswordResetRequestView(views.APIView):
    """
    Request a password-reset email.

    Always returns **200** regardless of whether the email address is
    registered – this prevents user-enumeration attacks.
    """

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data.get("user")
        token = serializer.validated_data.get("token")

        if user and token:
            # Enqueue the email-sending task (from the notifications app).
            try:
                from crestpoint_credit.notifications.tasks import send_password_reset_email

                send_password_reset_email.delay(
                    user_id=user.id,
                    email=user.email,
                    token=token,
                )
                logger.info("Password reset email queued for: %s", user.email)
            except ImportError:
                logger.warning(
                    "notifications.tasks.send_password_reset_email not available; "
                    "skipping email enqueue for %s",
                    user.email,
                )
            except Exception:
                logger.exception(
                    "Failed to enqueue password reset email for: %s", user.email
                )

        # Always return 200 – never reveal whether the account exists.
        return Response(
            {
                "message": (
                    "If an account exists with this email, you will receive a "
                    "password reset link."
                )
            },
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Password Reset – Confirm
# ---------------------------------------------------------------------------


class PasswordResetConfirmView(views.APIView):
    """
    Confirm a password reset by providing the email, token, and new password.
    """

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        serializer.save()

        # Invalidate **all** outstanding / non-blacklisted tokens for the user
        # so existing sessions are terminated.
        user = serializer.validated_data["user"]
        self._invalidate_all_user_tokens(user)

        return Response(
            {"message": "Password reset successful"},
            status=status.HTTP_200_OK,
        )

    @staticmethod
    def _invalidate_all_user_tokens(user):
        """Blacklist every outstanding token that belongs to *user*."""
        try:
            tokens = OutstandingToken.objects.filter(
                user_id=user.id,
                blacklistedtoken__isnull=True,
            )
            blacklist_entries = [
                BlacklistedToken(token=token) for token in tokens
            ]
            BlacklistedToken.objects.bulk_create(blacklist_entries)
            logger.info(
                "Invalidated %d outstanding tokens for user: %s",
                len(blacklist_entries),
                user.email,
            )
        except Exception:
            logger.exception("Failed to invalidate tokens for user: %s", user.email)


# ---------------------------------------------------------------------------
# OTP – Send (Login)
# ---------------------------------------------------------------------------


class OTPEmailView(views.APIView):
    """
    Send a 6-digit OTP to the user's email for login verification.

    The email must belong to an existing account.  A rate-limit of 1 request
    per 60 seconds is enforced via the ``LoginRateThrottle``.
    """

    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]

    def post(self, request, *args, **kwargs):
        serializer = OTPEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"message": "Verification code sent to your email."},
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# OTP – Send (Registration)
# ---------------------------------------------------------------------------


class OTPEmailRegisterView(views.APIView):
    """
    Send a 6-digit OTP to the given email for registration verification.

    The email must NOT already be registered.
    """

    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]

    def post(self, request, *args, **kwargs):
        serializer = OTPEmailRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"message": "Verification code sent to your email."},
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# OTP – Verify (Login)
# ---------------------------------------------------------------------------


class OTPVerifyView(views.APIView):
    """
    Verify a 6-digit OTP code for login.

    On success the view issues JWT tokens directly (credentials were already
    validated when the OTP was requested).  The frontend does **not** need a
    separate login call.
    """

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = OTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data["user"]

        # Update last_login_at
        user.last_login_at = timezone.now()
        user.save(update_fields=["last_login_at"])

        # Generate JWT tokens.
        refresh = RefreshToken.for_user(user)
        access = refresh.access_token
        access["role"] = user.role

        response_data = {
            "access": str(access),
            "refresh": str(refresh),
            "user": {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "role": user.role,
            },
            "message": "Verification successful.",
        }

        response = Response(response_data, status=status.HTTP_200_OK)
        _set_auth_cookies(response, str(access), str(refresh))

        logger.info("Successful OTP-login for user: %s (role=%s)", user.email, user.role)
        return response


# ---------------------------------------------------------------------------
# OTP – Verify (Registration)
# ---------------------------------------------------------------------------


class OTPVerifyRegisterView(views.APIView):
    """
    Verify a 6-digit OTP code for registration.
    """

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = OTPVerifyRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            {"message": "Verification successful."},
            status=status.HTTP_200_OK,
        )
