from django.contrib import admin

from .models import LoanType, LoanApplication, Loan, LoanRepayment


@admin.register(LoanType)
class LoanTypeAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "min_amount",
        "max_amount",
        "interest_rate",
        "max_term_months",
        "is_active",
        "created_at",
    )
    list_filter = ("is_active",)
    search_fields = ("name",)
    readonly_fields = ("created_at", "updated_at")
    ordering = ("name",)


@admin.register(LoanApplication)
class LoanApplicationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "loan_type",
        "amount_requested",
        "status",
        "term_months",
        "submitted_at",
    )
    list_filter = ("status", "loan_type", "submitted_at")
    search_fields = ("user__email", "purpose")
    readonly_fields = (
        "submitted_at",
        "reviewed_at",
        "created_at",
        "updated_at",
    )
    ordering = ("-submitted_at",)


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "loan_application",
        "account",
        "principal",
        "interest_rate",
        "outstanding_balance",
        "status",
        "disbursement_date",
        "created_at",
    )
    list_filter = ("status", "disbursement_date")
    search_fields = ("account__account_number", "loan_application__user__email")
    readonly_fields = (
        "disbursement_date",
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at",)


@admin.register(LoanRepayment)
class LoanRepaymentAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "loan",
        "amount",
        "principal_portion",
        "interest_portion",
        "status",
        "payment_date",
    )
    list_filter = ("status",)
    search_fields = ("reference", "loan__id")
    readonly_fields = (
        "reference",
        "payment_date",
        "created_at",
        "updated_at",
    )
    ordering = ("-payment_date",)