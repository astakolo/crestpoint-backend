"""URL configuration for the security app."""

from django.urls import path

from . import views

app_name = "security"

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("refresh/", views.TokenRefreshView.as_view(), name="token-refresh"),
    path(
        "password-reset/request/",
        views.PasswordResetRequestView.as_view(),
        name="password-reset-request",
    ),
    path(
        "password-reset/confirm/",
        views.PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
    path("otp/send/", views.OTPEmailView.as_view(), name="otp-send"),
    path("otp/verify/", views.OTPVerifyView.as_view(), name="otp-verify"),
    path("otp/register/send/", views.OTPEmailRegisterView.as_view(), name="otp-register-send"),
    path("otp/register/verify/", views.OTPVerifyRegisterView.as_view(), name="otp-register-verify"),
]