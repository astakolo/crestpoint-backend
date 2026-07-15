from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"admin", views.AdminPaymentViewSet, basename="admin-payments")

urlpatterns = [
    path("initiate/", views.InitiatePaymentView.as_view(), name="initiate-payment"),
    path("", views.PaymentListView.as_view(), name="payment-list"),
    path("<int:pk>/", views.PaymentDetailView.as_view(), name="payment-detail"),
    path("<int:pk>/verify/", views.VerifyPaymentView.as_view(), name="verify-payment"),
    path("<int:pk>/refund/", views.RefundPaymentView.as_view(), name="refund-payment"),
    path("", include(router.urls)),
]
