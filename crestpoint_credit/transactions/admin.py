from django.contrib import admin

from .models import Transaction


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "transaction_type",
        "account",
        "amount",
        "status",
        "is_flagged",
        "created_at",
    )
    list_filter = (
        "transaction_type",
        "status",
        "is_flagged",
        "created_at",
    )
    search_fields = (
        "reference",
        "description",
    )
    readonly_fields = (
        "reference",
        "balance_before",
        "balance_after",
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at",)

    @admin.action(description="Flag selected transactions")
    def flag_selected(self, request, queryset):
        updated = queryset.update(is_flagged=True)
        self.message_user(
            request,
            f"{updated} transaction{'s' if updated != 1 else ''} flagged.",
        )

    @admin.action(description="Unflag selected transactions")
    def unflag_selected(self, request, queryset):
        updated = queryset.update(is_flagged=False, flag_reason="")
        self.message_user(
            request,
            f"{updated} transaction{'s' if updated != 1 else ''} unflagged.",
        )

    actions = [flag_selected, unflag_selected]
