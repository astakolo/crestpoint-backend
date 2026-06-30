from django.urls import path

from . import views

urlpatterns = [
    path("deposit/", views.CheckDepositCreateView.as_view(), name="check-deposit-create"),
    path("", views.CheckDepositListView.as_view(), name="check-deposit-list"),
    path("<int:pk>/", views.CheckDepositDetailView.as_view(), name="check-deposit-detail"),
    # Admin
    path("admin/", views.AdminCheckDepositListView.as_view(), name="admin-check-deposit-list"),
    path("admin/<int:pk>/process/", views.AdminProcessCheckDepositView.as_view(), name="admin-process-check-deposit"),
]