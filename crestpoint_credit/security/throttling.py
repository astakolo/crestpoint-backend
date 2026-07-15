"""Custom throttle classes for rate-limiting API endpoints."""

from rest_framework.throttling import ScopedRateThrottle


class BurstRateThrottle(ScopedRateThrottle):
    """Short-burst rate limiter (scope: 'burst')."""
    scope = "burst"


class LoginRateThrottle(ScopedRateThrottle):
    """Rate limiter for auth endpoints (scope: 'login')."""
    scope = "login"


class TransferRateThrottle(ScopedRateThrottle):
    """Rate limiter for money-transfer endpoints (scope: 'transfer')."""
    scope = "transfer"


class TransactionRateThrottle(ScopedRateThrottle):
    """Rate limiter for general transaction endpoints (scope: 'transaction')."""
    scope = "transaction"
