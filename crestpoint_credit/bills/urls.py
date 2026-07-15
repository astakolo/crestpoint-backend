from django.urls import path

from . import views

urlpatterns = [
    path("categories/", views.BillerCategoryListView.as_view(), name="biller-category-list"),
    path("billers/", views.BillerListView.as_view(), name="biller-list"),
    path("saved/", views.SavedBillersListView.as_view(), name="saved-biller-list"),
    path("saved/save/", views.SaveBillerView.as_view(), name="save-biller"),
    path("saved/<int:pk>/", views.DeleteSavedBillerView.as_view(), name="delete-saved-biller"),
    path("pay/", views.PayBillView.as_view(), name="pay-bill"),
    path("payments/", views.BillPaymentListView.as_view(), name="bill-payment-list"),
    path("payments/<int:pk>/", views.BillPaymentDetailView.as_view(), name="bill-payment-detail"),
    # Admin
    path("admin/", views.AdminBillPaymentListView.as_view(), name="admin-bill-payment-list"),
]