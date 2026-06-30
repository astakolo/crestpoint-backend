from django.contrib import admin

from .models import CryptoWallet, CryptoTransaction


@admin.register(CryptoWallet)
class CryptoWalletAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "wallet_address",
        "currency",
        "balance",
        "is_active",
        "created_at",
    )
    list_filter = ("currency", "is_active")
    search_fields = ("user__email", "wallet_address")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at",)


@admin.register(CryptoTransaction)
class CryptoTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "wallet",
        "transaction_type",
        "crypto_currency",
        "amount",
        "usd_amount",
        "status",
        "created_at",
    )
    list_filter = ("transaction_type", "crypto_currency", "status")
    search_fields = ("wallet__user__email", "reference", "tx_hash")
    readonly_fields = ("reference", "created_at", "updated_at")
    ordering = ("-created_at",)