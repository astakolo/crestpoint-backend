"""
Django settings for CrestPoint Credit - Production-grade digital banking platform.
"""

import os
from datetime import timedelta
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-fdjkj9834jksdsdction-x9$k2m!@#z7",
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get("DJANGO_DEBUG", "False").lower() == "true"

ALLOWED_HOSTS = os.environ.get(
    "DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,backend,crestpoint-backend.vercel.app,api.crestpointcredit.online"
).split(",")

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    # Local apps
    "crestpoint_credit.core",
    "crestpoint_credit.accounts",
    "crestpoint_credit.security",
    "crestpoint_credit.transactions",
    "crestpoint_credit.payments",
    "crestpoint_credit.notifications",
    "crestpoint_credit.loans",
    "crestpoint_credit.investments",
    "crestpoint_credit.checks",
    "crestpoint_credit.crypto",
    "crestpoint_credit.bills",
    "crestpoint_credit.cards",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    # CsrfViewMiddleware removed — pure API backend uses JWT auth,
    # not session/cookie auth. DRF's JSONParser handles request bodies.
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Custom security middleware
    "crestpoint_credit.security.middleware.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "crestpoint_credit.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "crestpoint_credit" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "crestpoint_credit.wsgi.application"
ASGI_APPLICATION = "crestpoint_credit.asgi.application"

# ==============================
# DATABASE CONFIGURATION
# ==============================
# Change ENGINE to 'django.db.backends.postgresql' and fill in the
# POSTGRES_* values below when you're ready to use Postgres.
# For local dev, SQLite (the default here) works out of the box.
# ==============================

DATABASES = {
    "default": {
        "ENGINE": os.environ.get("DB_ENGINE", "django.db.backends.sqlite3"),
        "NAME": os.environ.get("DB_NAME", str(BASE_DIR / "db.sqlite3")),
        "USER": os.environ.get("DB_USER", ""),           # Postgres only
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),   # Postgres only
        "HOST": os.environ.get("DB_HOST", ""),           # e.g. db.aymvwwemwijpdybqqpsu.supabase.co
        "PORT": os.environ.get("DB_PORT", ""),           # e.g. 5432
        "CONN_MAX_AGE": int(os.environ.get("DB_CONN_MAX_AGE", "0")),
    }
}

# --- SUPABASE POSTGRES (uncomment and fill in to use) ---
# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.postgresql",
#         "NAME": "postgres",
#         "USER": "postgres.aymvwwemwijpdybqqpsu",
#         "PASSWORD": "EmX3STJi6pQj",
#         "HOST": "aws-1-eu-central-2.pooler.supabase.com",
#         "PORT": "5432",
#         "CONN_MAX_AGE": 60,
#     }
# }

# ==============================
# CACHING
# ==============================
_redis_url = os.environ.get("REDIS_URL", "")
if _redis_url:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": _redis_url,
            "KEY_PREFIX": "crestpoint_",
            "TIMEOUT": 300,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "KEY_PREFIX": "crestpoint_",
            "TIMEOUT": 300,
        }
    }

# ==============================
# CELERY - Redis Broker
# ==============================
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/1")
CELERY_RESULT_BACKEND = os.environ.get(
    "CELERY_RESULT_BACKEND", "redis://redis:6379/2"
)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_ENABLE_UTC = True
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes hard limit
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60  # 25 minutes soft limit

# ==============================
# AUTH PASSWORD VALIDATION
# ==============================
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Custom user model
AUTH_USER_MODEL = "accounts.User"

# ==============================
# REST FRAMEWORK
# ==============================
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "crestpoint_credit.core.pagination.StandardPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_CLASSES": [],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/minute",
        "user": "120/minute",
        "burst": "10/minute",
        "login": "5/minute",
        "transfer": "10/minute",
        "transaction": "30/minute",
    },
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "DEFAULT_PARSER_CLASSES": (
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_EXCEPTION_HANDLER": "crestpoint_credit.core.exceptions.custom_exception_handler",
    "NON_FIELD_ERRORS_KEY": "error",
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

# ==============================
# JWT SETTINGS
# ==============================
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": os.environ.get(
        "JWT_SIGNING_KEY", SECRET_KEY
    ),
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),
    "TOKEN_USER_CLASS": "accounts.User",
    "COOKIE_SECURE": not DEBUG,
    "COOKIE_HTTP_ONLY": True,
    "COOKIE_SAMESITE": "Lax",
    "COOKIE_DOMAIN": os.environ.get("COOKIE_DOMAIN", None),
}

# ==============================
# INTERNATIONALIZATION
# ==============================
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ==============================
# STATIC & MEDIA FILES
# ==============================
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ==============================
# CORS SETTINGS
# ==============================
CORS_ALLOWED_ORIGINS = os.environ.get(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,https://crestpoint-backend.vercel.app,https://crestpointcredit.online,https://www.crestpointcredit.online,https://api.crestpointcredit.online",
).split(",")
CORS_ALLOW_CREDENTIALS = True
CORS_PREFLIGHT_MAX_AGE = 86400

# ==============================
# SECURITY HEADERS
# ==============================
SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "False").lower() == "true"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "False").lower() == "true"
CSRF_COOKIE_SECURE = os.environ.get("CSRF_COOKIE_SECURE", "False").lower() == "true"
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = bool(SECURE_HSTS_SECONDS)
SECURE_HSTS_PRELOAD = bool(SECURE_HSTS_SECONDS)
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

# ==============================
# LOGGING
# ==============================
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "simple": {
            "format": "{levelname} {asctime} {message}",
            "style": "{",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "filters": {
        "require_debug_true": {
            "()": "django.utils.log.RequireDebugTrue",
        },
        "require_debug_false": {
            "()": "django.utils.log.RequireDebugFalse",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO"),
            "propagate": True,
        },
        "django.security": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "crestpoint_credit": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": True,
        },
    },
}

# ==============================
# SPECTACULAR (OpenAPI Schema)
# ==============================
SPECTACULAR_SETTINGS = {
    "TITLE": "CrestPoint Credit API",
    "DESCRIPTION": "Production-grade digital banking API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SECURITY": [{"Bearer": []}],
}

# ==============================
# EMAIL (Backend for notifications)
# ==============================
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend"
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.zoho.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL", "info@crestpointcredit.online"
)

# ==============================
# KYC / DOCUMENT UPLOAD
# ==============================
KYC_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
KYC_ALLOWED_FILE_TYPES = ["image/jpeg", "image/png", "application/pdf"]

# ==============================
# TRANSACTION LIMITS
# ==============================
DAILY_TRANSFER_LIMIT = 50000.00
SINGLE_TRANSFER_LIMIT = 10000.00
DAILY_WITHDRAWAL_LIMIT = 20000.00
MAX_FAILED_LOGIN_ATTEMPTS = 5
ACCOUNT_LOCKOUT_DURATION = 30  # minutes

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"