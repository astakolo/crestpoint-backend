from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "user",
        "notification_type",
        "channel",
        "status",
        "is_read",
        "created_at",
    )
    list_filter = (
        "notification_type",
        "channel",
        "status",
        "is_read",
        "created_at",
    )
    search_fields = ("title", "message", "user__email")
    readonly_fields = ("created_at", "updated_at", "sent_at", "read_at")
    ordering = ("-created_at",)
