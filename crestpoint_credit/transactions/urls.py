from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"admin", views.AdminTransactionViewSet, basename="admin-transactions")

urlpatterns = [
    path("deposit/", views.DepositView.as_view(), name="deposit"),
    path("withdraw/", views.WithdrawalView.as_view(), name="withdraw"),
    path("transfer/", views.TransferView.as_view(), name="transfer"),
    path("history/", views.TransactionHistoryView.as_view(), name="transaction-history"),
    path("<int:pk>/", views.TransactionDetailView.as_view(), name="transaction-detail"),
    path("<int:pk>/flag/", views.FlagTransactionView.as_view(), name="flag-transaction"),
    path("<int:pk>/unflag/", views.UnflagTransactionView.as_view(), name="unflag-transaction"),
    path("<int:pk>/reverse/", views.ReverseTransactionView.as_view(), name="reverse-transaction"),
    path("admin/stats/", views.AdminTransactionStatsView.as_view(), name="admin-transaction-stats"),
    path("admin/export-csv/", views.AdminCSVExportView.as_view(), name="admin-export-csv"),
    # Withdrawal requests
    path("withdrawal-requests/", views.WithdrawalRequestCreateView.as_view(), name="withdrawal-request-create"),
    path("withdrawal-requests/list/", views.WithdrawalRequestListView.as_view(), name="withdrawal-request-list"),
    path("withdrawal-requests/<int:pk>/", views.WithdrawalRequestDetailView.as_view(), name="withdrawal-request-detail"),
    path("withdrawal-requests/admin/", views.AdminWithdrawalRequestListView.as_view(), name="admin-withdrawal-request-list"),
    path("withdrawal-requests/<int:pk>/review/", views.AdminReviewWithdrawalView.as_view(), name="admin-review-withdrawal"),
    path("", include(router.urls)),
]