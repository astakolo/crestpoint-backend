from django.contrib import admin

from .models import Payment, PaymentStatus, PaymentProvider, PaymentMethod


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    """Django admin configuration for the Payment model."""

    list_display = (
        "reference",
        "user",
        "account",
        "amount",
        "currency",
        "status",
        "provider",
        "payment_method",
        "created_at",
    )
    list_filter = (
        "status",
        "provider",
        "payment_method",
        "created_at",
    )
    search_fields = (
        "reference",
        "user__email",
        "account__account_number",
        "provider_payment_id",
    )
    readonly_fields = (
        "reference",
        "provider_payment_id",
        "provider_response",
        "completed_at",
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at",)

    fieldsets = (
        (
            "Payment Information",
            {
                "fields": (
                    "reference",
                    "user",
                    "account",
                    "amount",
                    "currency",
                    "payment_method",
                    "provider",
                    "status",
                )
            },
        ),
        (
            "Provider Details",
            {
                "fields": (
                    "provider_payment_id",
                    "provider_response",
                )
            },
        ),
        (
            "Status & Timing",
            {
                "fields": (
                    "completed_at",
                    "error_message",
                    "created_at",
                    "updated_at",
                )
            },
        ),
        (
            "Metadata",
            {
                "fields": ("metadata",),
                "classes": ("collapse",),
            },
        ),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user", "account")
