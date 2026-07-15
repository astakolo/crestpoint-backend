from django.contrib import admin

from .models import Stock, InvestmentAccount, StockHolding, InvestmentTransaction


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = (
        "symbol",
        "name",
        "current_price",
        "previous_close",
        "change_percent",
        "volume",
        "updated_at",
    )
    list_filter = ("updated_at",)
    search_fields = ("symbol", "name")
    readonly_fields = ("updated_at",)
    ordering = ("symbol",)


@admin.register(InvestmentAccount)
class InvestmentAccountAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "balance",
        "total_invested",
        "total_returns",
        "is_active",
        "created_at",
    )
    list_filter = ("is_active",)
    search_fields = ("user__email",)
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at",)


@admin.register(StockHolding)
class StockHoldingAdmin(admin.ModelAdmin):
    list_display = (
        "investment_account",
        "stock",
        "quantity",
        "average_buy_price",
        "current_value",
        "pnl",
        "created_at",
    )
    list_filter = ("stock",)
    search_fields = ("investment_account__user__email", "stock__symbol")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at",)


@admin.register(InvestmentTransaction)
class InvestmentTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "investment_account",
        "transaction_type",
        "stock",
        "quantity",
        "amount",
        "status",
        "created_at",
    )
    list_filter = ("transaction_type", "status")
    search_fields = ("reference", "investment_account__user__email", "stock__symbol")
    readonly_fields = ("reference", "created_at", "updated_at")
    ordering = ("-created_at",)