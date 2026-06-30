from django.contrib import admin

from .models import CheckDeposit


@admin.register(CheckDeposit)
class CheckDepositAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "user",
        "account",
        "check_number",
        "amount",
        "status",
        "processed_at",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("user__email", "reference", "check_number")
    readonly_fields = (
        "reference",
        "processed_at",
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at",)