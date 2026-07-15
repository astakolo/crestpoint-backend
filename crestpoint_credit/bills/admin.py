from django.contrib import admin

from .models import BillerCategory, Biller, BillerSaved, BillPayment


@admin.register(BillerCategory)
class BillerCategoryAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "icon",
        "is_active",
        "created_at",
    )
    list_filter = ("is_active",)
    search_fields = ("name",)
    readonly_fields = ("created_at", "updated_at")
    ordering = ("name",)


@admin.register(Biller)
class BillerAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "category",
        "biller_code",
        "account_number",
        "is_active",
        "created_at",
    )
    list_filter = ("category", "is_active")
    search_fields = ("name", "biller_code")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("name",)


@admin.register(BillerSaved)
class BillerSavedAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "biller",
        "nickname",
        "account_number",
        "created_at",
    )
    list_filter = ("biller__category",)
    search_fields = ("user__email", "biller__name", "nickname")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at",)


@admin.register(BillPayment)
class BillPaymentAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "user",
        "biller",
        "account",
        "amount",
        "status",
        "created_at",
    )
    list_filter = ("status", "biller__category", "created_at")
    search_fields = ("user__email", "reference", "biller__name")
    readonly_fields = ("reference", "created_at", "updated_at")
    ordering = ("-created_at",)