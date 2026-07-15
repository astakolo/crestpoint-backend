import logging

from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    NotAcceptable,
    NotFound,
    PermissionDenied,
    ValidationError,
)
from rest_framework.views import exception_handler

logger = logging.getLogger("crestpoint_credit")


# ---------------------------------------------------------------------------
# Custom banking-domain exception classes
# ---------------------------------------------------------------------------


class InsufficientFundsError(APIException):
    """Raised when an account does not have enough balance for a transaction."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Insufficient funds in account."
    default_code = "insufficient_funds"


class AccountLockedError(APIException):
    """Raised when an operation is attempted on a locked account."""

    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "Account is currently locked."
    default_code = "account_locked"


class DailyLimitExceededError(APIException):
    """Raised when a user exceeds their daily transaction limit."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Daily transaction limit has been exceeded."
    default_code = "daily_limit_exceeded"


class TransferLimitExceededError(APIException):
    """Raised when a single transfer exceeds the allowed maximum."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Transfer amount exceeds the maximum allowed limit."
    default_code = "transfer_limit_exceeded"


class InvalidTransferError(APIException):
    """Raised when a transfer request contains invalid data (e.g. self-transfer)."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "Invalid transfer request."
    default_code = "invalid_transfer"


class KYCRequiredError(APIException):
    """Raised when an operation requires KYC verification that has not been completed."""

    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "KYC verification is required to perform this action."
    default_code = "kyc_required"


# ---------------------------------------------------------------------------
# Known custom exceptions lookup — used by the handler below
# ---------------------------------------------------------------------------

_CUSTOM_EXCEPTIONS = (
    InsufficientFundsError,
    AccountLockedError,
    DailyLimitExceededError,
    TransferLimitExceededError,
    InvalidTransferError,
    KYCRequiredError,
)


# ---------------------------------------------------------------------------
# Custom exception handler
# ---------------------------------------------------------------------------


def custom_exception_handler(exception, context):
    """
    Central exception handler for the CrestPoint Credit API.

    Provides user-friendly, consistent error responses while ensuring
    internal details are **never** leaked to clients in production.
    """
    # Log every exception for observability
    logger.error(
        "Exception in %s: %s",
        context.get("view"),
        getattr(exception, "detail", str(exception)),
        exc_info=True,
    )

    # --- Validation errors (400) ---
    if isinstance(exception, ValidationError):
        response = exception_handler(exception, context)
        if response is not None:
            response.data = {
                "error": "Validation failed",
                "details": response.data,
            }
        return response

    # --- Authentication failed (401) ---
    if isinstance(exception, AuthenticationFailed):
        response = exception_handler(exception, context)
        if response is not None:
            response.data = {"error": "Authentication failed"}
        return response

    # --- Permission denied (403) ---
    if isinstance(exception, PermissionDenied):
        response = exception_handler(exception, context)
        if response is not None:
            response.data = {"error": "Permission denied"}
        return response

    # --- Not found (404) ---
    if isinstance(exception, NotFound):
        response = exception_handler(exception, context)
        if response is not None:
            response.data = {"error": "Resource not found"}
        return response

    # --- Custom domain exceptions ---
    if isinstance(exception, _CUSTOM_EXCEPTIONS):
        response = exception_handler(exception, context)
        if response is not None:
            response.data = {
                "error": str(exception.detail)
                if hasattr(exception, "detail")
                else str(exception)
            }
        return response

    # --- Unexpected / unhandled exceptions (500) ---
    # NEVER expose traceback or internal details
    response = exception_handler(exception, context)
    if response is not None:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        response.data = {"error": "An internal error occurred"}
    return response
