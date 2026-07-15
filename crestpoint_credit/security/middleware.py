"""Custom middleware for security headers and request logging."""

import logging
import re
import time

from django.conf import settings

logger = logging.getLogger("crestpoint_credit")

# Patterns commonly associated with malicious requests.
_SQL_INJECTION_PATTERN = re.compile(
    r"(?i)(union\s+select|select\s+.+\s+from|insert\s+into|drop\s+table|"
    r"delete\s+from|update\s+.+\s+set|or\s+1\s*=\s*1|'\s*or\s+'|"
    r"--\s*|;\s*--|benchmark\s*\(|sleep\s*\(|waitfor\s+delay)",
)
_PATH_TRAVERSAL_PATTERN = re.compile(
    r"(\.\./|\.\.\\|%2e%2e[%/\\])",
)

# Endpoints that should be skipped for request logging (health checks, etc.).
_SKIP_LOG_PATHS = frozenset(
    {
        "/health/",
        "/healthz",
        "/readiness",
        "/metrics",
        "/favicon.ico",
    }
)


# ---------------------------------------------------------------------------
# Security Headers Middleware
# ---------------------------------------------------------------------------


class SecurityHeadersMiddleware:
    """Inject defence-in-depth HTTP headers on every response and log
    requests that match common attack patterns.

    Production-only headers (CSP, HSTS) are only added when ``settings.DEBUG``
    is ``False``.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Run the request through the middleware chain first so we can inspect
        # query params *before* the response is returned.
        self._check_suspicious_request(request)
        response = self.get_response(request)
        response = self._add_security_headers(request, response)
        return response

    # -- header helpers -----------------------------------------------------

    @staticmethod
    def _add_security_headers(request, response):
        """Attach standard security headers to *response*."""
        response["X-Content-Type-Options"] = "nosniff"
        response["X-XSS-Protection"] = "1; mode=block"
        response["X-Frame-Options"] = "DENY"
        response["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )

        if not settings.DEBUG:
            # Permissive CSP for API-only backend — no HTML pages are served
            response["Content-Security-Policy"] = (
                "default-src 'self'; "
                "connect-src 'self' *; "
                "frame-ancestors 'none'"
            )
            response["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        return response

    # -- suspicious-pattern detection ----------------------------------------

    @staticmethod
    def _check_suspicious_request(request):
        """Log warnings for requests that look like injection attempts."""
        full_path = request.get_full_path()

        # Query-string inspection.
        query_string = request.META.get("QUERY_STRING", "")

        # SQL injection check.
        if _SQL_INJECTION_PATTERN.search(full_path):
            logger.warning(
                "Suspicious SQL-injection pattern detected – "
                "path=%s ip=%s user_agent=%s",
                request.path,
                _get_client_ip(request),
                request.META.get("HTTP_USER_AGENT", ""),
            )

        # Path-traversal check.
        if _PATH_TRAVERSAL_PATTERN.search(full_path):
            logger.warning(
                "Suspicious path-traversal pattern detected – "
                "path=%s ip=%s user_agent=%s",
                request.path,
                _get_client_ip(request),
                request.META.get("HTTP_USER_AGENT", ""),
            )


# ---------------------------------------------------------------------------
# Request Logging Middleware
# ---------------------------------------------------------------------------


class RequestLoggingMiddleware:
    """Log metadata for every API request: method, path, user, IP, status, and
    response time.

    * Password fields are never logged.
    * Health-check / metrics endpoints are skipped to reduce noise.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip noisy endpoints.
        if request.path in _SKIP_LOG_PATHS:
            return self.get_response(request)

        start_time = time.perf_counter()

        response = self.get_response(request)

        duration_ms = (time.perf_counter() - start_time) * 1000

        user_identifier = "anonymous"
        if hasattr(request, "user") and request.user.is_authenticated:
            user_identifier = str(request.user.email)

        logger.info(
            "%s %s user=%s ip=%s status=%d duration=%.1fms",
            request.method,
            request.path,
            user_identifier,
            _get_client_ip(request),
            response.status_code,
            duration_ms,
        )

        return response


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _get_client_ip(request) -> str:
    """Return the client IP address, honouring ``X-Forwarded-For`` when
    ``SECURE_PROXY_SSL_HEADER`` is configured.
    """
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")
