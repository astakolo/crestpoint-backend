from django.urls import path
from . import views

urlpatterns = [
    path("", views.NotificationListView.as_view(), name="notification-list"),
    path("mark-read/", views.MarkAsReadView.as_view(), name="mark-as-read"),
    path("mark-all-read/", views.MarkAllAsReadView.as_view(), name="mark-all-read"),
    path("unread-count/", views.UnreadCountView.as_view(), name="unread-count"),
]
