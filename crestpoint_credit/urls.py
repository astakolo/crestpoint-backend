"""
Root URL configuration for CrestPoint Credit.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView

urlpatterns = [
    path("admin/", admin.site.urls),
    # API authentication
    path("api/auth/", include("crestpoint_credit.security.urls")),
    # API endpoints
    path("api/accounts/", include("crestpoint_credit.accounts.urls")),
    path("api/transactions/", include("crestpoint_credit.transactions.urls")),
    path("api/payments/", include("crestpoint_credit.payments.urls")),
    path("api/notifications/", include("crestpoint_credit.notifications.urls")),
    # API schema
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularRedocView.as_view(url_name="schema"), name="docs"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
