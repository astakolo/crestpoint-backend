from django.urls import path

from . import views

urlpatterns = [
    path("", views.CardListView.as_view(), name="card-list"),
    path("create/", views.CardCreateView.as_view(), name="card-create"),
    path("<int:pk>/", views.CardDetailView.as_view(), name="card-detail"),
    path("<int:pk>/freeze/", views.CardFreezeView.as_view(), name="card-freeze"),
    path("<int:pk>/fund/", views.CardFundView.as_view(), name="card-fund"),
    path("<int:pk>/transactions/", views.CardTransactionListView.as_view(), name="card-transaction-list"),
    # Admin
    path("admin/", views.AdminCardListView.as_view(), name="admin-card-list"),
]