from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"accounts", views.BankAccountViewSet, basename="bank-account")

urlpatterns = [
    path("", include(router.urls)),
    path("profile/", views.UserDetailView.as_view(), name="user-profile"),
    path("change-password/", views.ChangePasswordView.as_view(), name="change-password"),
    path("kyc/upload/", views.KYCUploadView.as_view(), name="kyc-upload"),
    path("kyc/review/", views.KYCReviewView.as_view(), name="kyc-review"),
    path(
        "admin/users/",
        views.AdminUserViewSet.as_view({"get": "list", "post": "create"}),
        name="admin-users",
    ),
    path(
        "admin/users/batch-lock/",
        views.AdminUserViewSet.as_view({"post": "batch_lock"}),
        name="admin-batch-lock",
    ),
    path(
        "admin/users/batch-unlock/",
        views.AdminUserViewSet.as_view({"post": "batch_unlock"}),
        name="admin-batch-unlock",
    ),
    path(
        "admin/users/<int:pk>/",
        views.AdminUserViewSet.as_view({"get": "retrieve", "patch": "update", "delete": "destroy"}),
        name="admin-user-detail",
    ),
    path(
        "admin/users/<int:pk>/lock/",
        views.AdminUserViewSet.as_view({"post": "lock_user"}),
        name="admin-lock-user",
    ),
    path(
        "admin/users/<int:pk>/unlock/",
        views.AdminUserViewSet.as_view({"post": "unlock_user"}),
        name="admin-unlock-user",
    ),
    path(
        "admin/users/<int:pk>/verify/",
        views.AdminUserViewSet.as_view({"post": "verify_user"}),
        name="admin-verify-user",
    ),
    path(
        "admin/users/<int:pk>/adjust-balance/",
        views.AdminUserViewSet.as_view({"post": "adjust_balance"}),
        name="admin-adjust-balance",
    ),
    path(
        "admin/send-notification/",
        views.AdminSendNotificationView.as_view(),
        name="admin-send-notification",
    ),
]