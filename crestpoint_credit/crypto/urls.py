from django.urls import path

from . import views

urlpatterns = [
    path("wallet/", views.CryptoWalletView.as_view(), name="crypto-wallet"),
    path("deposit/", views.CryptoDepositCreateView.as_view(), name="crypto-deposit-create"),
    path("transactions/", views.CryptoTransactionListView.as_view(), name="crypto-transaction-list"),
    # Admin
    path("admin/", views.AdminCryptoTransactionListView.as_view(), name="admin-crypto-transaction-list"),
    path("admin/<int:pk>/process/", views.AdminProcessCryptoDepositView.as_view(), name="admin-process-crypto-deposit"),
]