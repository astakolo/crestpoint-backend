import logging
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone

from crestpoint_credit.core.models import TimestampedModel
from crestpoint_credit.core.utils import mask_account_number

logger = logging.getLogger("crestpoint_credit")


# ---------------------------------------------------------------------------
# Custom User Manager
# ---------------------------------------------------------------------------


class CustomUserManager(BaseUserManager):
    """Manager for the custom User model.

    Ensures emails are normalised and that superusers receive the correct
    flags on creation.
    """

    def create_user(self, email, first_name, last_name, password=None, **extra_fields):
        """Create and return a regular user.

        Args:
            email: Valid email address (used as USERNAME_FIELD).
            first_name: User's first name.
            last_name: User's last name.
            password: Raw password – will be hashed by Django.
            **extra_fields: Additional model fields.

        Returns:
            User instance.

        Raises:
            ValueError: If *email* is not provided.
        """
        if not email:
            raise ValueError("Users must have an email address.")
        if not first_name:
            raise ValueError("Users must have a first name.")
        if not last_name:
            raise ValueError("Users must have a last name.")

        email = self.normalize_email(email)
        user = self.model(email=email, first_name=first_name, last_name=last_name, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, first_name, last_name, password=None, **extra_fields):
        """Create and return a superuser with ``is_staff``, ``is_superuser``
        and ``is_active`` all set to ``True`` and ``role`` set to ``'admin'``.

        Args:
            email: Valid email address.
            first_name: Superuser's first name.
            last_name: Superuser's last name.
            password: Raw password.
            **extra_fields: Additional model fields.

        Returns:
            User instance.
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("role", "admin")

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, first_name, last_name, password, **extra_fields)


# ---------------------------------------------------------------------------
# User Model
# ---------------------------------------------------------------------------


class User(AbstractBaseUser, PermissionsMixin):
    """Custom user model for CrestPoint Credit.

    Uses *email* as the unique identifier instead of a username.
    """

    ROLE_CHOICES = [
        ("customer", "Customer"),
        ("admin", "Admin"),
        ("support", "Support"),
        ("auditor", "Auditor"),
    ]

    id = models.BigAutoField(primary_key=True)
    email = models.EmailField(unique=True, db_index=True, verbose_name="Email address")
    first_name = models.CharField(max_length=150, verbose_name="First name")
    last_name = models.CharField(max_length=150, verbose_name="Last name")
    phone = models.CharField(max_length=20, blank=True, default="", verbose_name="Phone number")
    is_active = models.BooleanField(default=True, verbose_name="Active")
    is_staff = models.BooleanField(default=False, verbose_name="Staff status")
    is_verified = models.BooleanField(default=False, verbose_name="Email verified")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="customer", db_index=True)
    failed_login_attempts = models.IntegerField(default=0, verbose_name="Failed login attempts")
    locked_until = models.DateTimeField(null=True, blank=True, verbose_name="Locked until")
    last_login_at = models.DateTimeField(null=True, blank=True, verbose_name="Last login at")

    objects = CustomUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    class Meta:
        db_table = "users"
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self):
        return self.email

    # ----- Properties -----

    @property
    def is_locked(self) -> bool:
        """Return ``True`` if the account is currently locked out."""
        if self.locked_until is None:
            return False
        return self.locked_until > timezone.now()

    # ----- Account lock / unlock helpers -----

    def lock_account(self, minutes: int = None):
        """Lock the account for *minutes* (defaults to
        ``settings.ACCOUNT_LOCKOUT_DURATION``).
        """
        if minutes is None:
            minutes = getattr(settings, "ACCOUNT_LOCKOUT_DURATION", 30)
        from datetime import timedelta

        self.locked_until = timezone.now() + timedelta(minutes=minutes)
        self.save(update_fields=["locked_until", "failed_login_attempts"])
        logger.warning("User %s locked until %s", self.email, self.locked_until)

    def unlock_account(self):
        """Remove the account lock and reset failed-login counter."""
        self.locked_until = None
        self.failed_login_attempts = 0
        self.save(update_fields=["locked_until", "failed_login_attempts"])
        logger.info("User %s unlocked", self.email)

    def increment_failed_login(self):
        """Increment the failed-login counter and lock the account when the
        configured threshold is reached.
        """
        max_attempts = getattr(settings, "MAX_FAILED_LOGIN_ATTEMPTS", 5)
        self.failed_login_attempts += 1
        self.save(update_fields=["failed_login_attempts"])

        if self.failed_login_attempts >= max_attempts:
            self.lock_account()
            logger.warning(
                "User %s locked after %d failed login attempts",
                self.email,
                self.failed_login_attempts,
            )

    def reset_failed_login(self):
        """Reset the failed-login counter to zero."""
        self.failed_login_attempts = 0
        self.save(update_fields=["failed_login_attempts"])


# ---------------------------------------------------------------------------
# Bank Account Model
# ---------------------------------------------------------------------------


class BankAccount(TimestampedModel):
    """Represents a customer bank account (savings or current)."""

    ACCOUNT_TYPE_CHOICES = [
        ("savings", "Savings"),
        ("current", "Current"),
    ]

    id = models.BigAutoField(primary_key=True)
    account_number = models.CharField(max_length=12, unique=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="bank_accounts",
        on_delete=models.PROTECT,
        db_index=True,
    )
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPE_CHOICES, default="savings")
    balance = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=3, default="USD")
    is_active = models.BooleanField(default=True)
    is_frozen = models.BooleanField(default=False)

    class Meta:
        db_table = "bank_accounts"
        verbose_name = "Bank Account"
        verbose_name_plural = "Bank Accounts"
        indexes = [
            models.Index(fields=["user", "account_type"], name="idx_user_account_type"),
            models.Index(fields=["account_number"], name="idx_account_number"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["user", "account_number"], name="unique_user_account_number"),
        ]

    def __str__(self):
        return self.account_number

    @property
    def masked_number(self) -> str:
        """Return the account number with all but the last 4 digits masked."""
        return mask_account_number(self.account_number)


# ---------------------------------------------------------------------------
# KYC Document Model
# ---------------------------------------------------------------------------


class KYCDocument(TimestampedModel):
    """Know-Your-Customer document uploaded by a user for identity verification."""

    DOCUMENT_TYPE_CHOICES = [
        ("passport", "Passport"),
        ("national_id", "National ID"),
        ("drivers_license", "Driver's License"),
    ]

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    id = models.BigAutoField(primary_key=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        related_name="kyc_document",
        on_delete=models.CASCADE,
    )
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPE_CHOICES)
    document_number = models.CharField(max_length=50)
    front_image = models.ImageField(upload_to="kyc/%Y/%m/")
    back_image = models.ImageField(upload_to="kyc/%Y/%m/", blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_kycs",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, default="")

    class Meta:
        db_table = "kyc_documents"
        verbose_name = "KYC Document"
        verbose_name_plural = "KYC Documents"

    def __str__(self):
        return f"KYC for {self.user.email} - {self.status}"
