import logging

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import BankAccount, KYCDocument, User

logger = logging.getLogger("crestpoint_credit")


# ---------------------------------------------------------------------------
# User Admin
# ---------------------------------------------------------------------------


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Custom admin interface for the User model."""

    list_display = [
        "email",
        "first_name",
        "last_name",
        "role",
        "is_active",
        "is_verified",
        "is_staff",
        "failed_login_attempts",
        "is_locked",
        "last_login_at",
    ]
    list_filter = [
        "role",
        "is_active",
        "is_verified",
        "is_staff",
        "is_superuser",
    ]
    search_fields = ["email", "first_name", "last_name", "phone"]
    ordering = ["-id"]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal Info", {"fields": ("first_name", "last_name", "phone")}),
        ("Permissions", {
            "fields": (
                "is_active",
                "is_staff",
                "is_superuser",
                "is_verified",
                "role",
                "groups",
                "user_permissions",
            ),
        }),
        ("Security", {
            "fields": (
                "failed_login_attempts",
                "locked_until",
                "last_login_at",
            ),
        }),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "first_name", "last_name", "password1", "password2"),
        }),
    )

    readonly_fields = ["last_login_at"]

    def is_locked(self, obj):
        """Display the locked status in the admin list."""
        return obj.is_locked

    is_locked.boolean = True
    is_locked.short_description = "Locked"

    actions = [
        "activate_users",
        "deactivate_users",
        "verify_users",
    ]

    @admin.action(description="Activate selected users")
    def activate_users(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} user(s) activated.")

    @admin.action(description="Deactivate selected users")
    def deactivate_users(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} user(s) deactivated.")

    @admin.action(description="Verify selected users")
    def verify_users(self, request, queryset):
        updated = queryset.update(is_verified=True)
        self.message_user(request, f"{updated} user(s) verified.")


# ---------------------------------------------------------------------------
# Bank Account Admin
# ---------------------------------------------------------------------------


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    """Admin interface for the BankAccount model."""

    list_display = [
        "account_number",
        "user",
        "account_type",
        "balance",
        "currency",
        "is_active",
        "is_frozen",
        "created_at",
    ]
    list_filter = [
        "account_type",
        "is_active",
        "is_frozen",
        "currency",
    ]
    search_fields = ["account_number", "user__email", "user__first_name", "user__last_name"]
    ordering = ["-created_at"]
    readonly_fields = ["account_number", "balance", "created_at", "updated_at"]

    actions = [
        "freeze_accounts",
        "unfreeze_accounts",
        "deactivate_accounts",
    ]

    @admin.action(description="Freeze selected accounts")
    def freeze_accounts(self, request, queryset):
        updated = queryset.update(is_frozen=True)
        self.message_user(request, f"{updated} account(s) frozen.")

    @admin.action(description="Unfreeze selected accounts")
    def unfreeze_accounts(self, request, queryset):
        updated = queryset.update(is_frozen=False)
        self.message_user(request, f"{updated} account(s) unfrozen.")

    @admin.action(description="Deactivate selected accounts")
    def deactivate_accounts(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} account(s) deactivated.")


# ---------------------------------------------------------------------------
# KYC Document Admin
# ---------------------------------------------------------------------------


@admin.register(KYCDocument)
class KYCDocumentAdmin(admin.ModelAdmin):
    """Admin interface for the KYCDocument model."""

    list_display = [
        "id",
        "user",
        "document_type",
        "document_number",
        "status",
        "submitted_at",
        "reviewed_by",
        "reviewed_at",
    ]
    list_filter = [
        "status",
        "document_type",
        "submitted_at",
    ]
    search_fields = [
        "user__email",
        "document_number",
        "document_type",
    ]
    ordering = ["-submitted_at"]
    readonly_fields = ["submitted_at", "reviewed_at"]

    actions = [
        "bulk_approve",
        "bulk_reject",
    ]

    @admin.action(description="Approve selected KYC documents")
    def bulk_approve(self, request, queryset):
        from django.utils import timezone

        updated = queryset.update(
            status="approved",
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
            rejection_reason="",
        )
        self.message_user(request, f"{updated} KYC document(s) approved.")
        logger.info(
            "Admin %s bulk-approved %d KYC documents",
            request.user.email,
            updated,
        )

    @admin.action(description="Reject selected KYC documents")
    def bulk_reject(self, request, queryset):
        from django.utils import timezone

        updated = queryset.update(
            status="rejected",
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
            rejection_reason="Rejected by admin via bulk action.",
        )
        self.message_user(request, f"{updated} KYC document(s) rejected.")
        logger.info(
            "Admin %s bulk-rejected %d KYC documents",
            request.user.email,
            updated,
        )
