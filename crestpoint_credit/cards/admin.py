from django.contrib import admin

from .models import VirtualCard, CardTransaction, CardFunding


@admin.register(VirtualCard)
class VirtualCardAdmin(admin.ModelAdmin):
    list_display = (
        "card_number",
        "user",
        "account",
        "cardholder_name",
        "brand",
        "card_type",
        "balance",
        "spending_limit",
        "status",
        "created_at",
    )
    list_filter = ("brand", "card_type", "status", "created_at")
    search_fields = ("user__email", "card_number", "cardholder_name")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at",)


@admin.register(CardTransaction)
class CardTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "card",
        "amount",
        "merchant_name",
        "merchant_category",
        "status",
        "created_at",
    )
    list_filter = ("status", "merchant_category")
    search_fields = ("card__user__email", "reference", "merchant_name")
    readonly_fields = ("reference", "created_at", "updated_at")
    ordering = ("-created_at",)


@admin.register(CardFunding)
class CardFundingAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "card",
        "account",
        "amount",
        "status",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = ("card__user__email", "reference", "account__account_number")
    readonly_fields = ("reference", "created_at", "updated_at")
    ordering = ("-created_at",)