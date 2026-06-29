from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    """Serializer for reading notification data."""

    class Meta:
        model = Notification
        fields = [
            "id",
            "title",
            "message",
            "notification_type",
            "channel",
            "status",
            "is_read",
            "created_at",
            "read_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "created_at",
            "read_at",
        ]


class MarkAsReadSerializer(serializers.Serializer):
    """Serializer for marking one or more notifications as read."""

    notification_ids = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False,
    )

    def validate_notification_ids(self, value):
        """Validate that all notification IDs belong to the requesting user."""
        from .models import Notification

        request = self.context.get("request")
        if not request:
            return value

        user = request.user
        notifications = Notification.objects.filter(
            id__in=value,
            user=user,
        )
        found_ids = set(notifications.values_list("id", flat=True))
        requested_ids = set(value)

        missing_ids = requested_ids - found_ids
        if missing_ids:
            raise serializers.ValidationError(
                f"Notification IDs {sorted(missing_ids)} do not belong to you or do not exist."
            )
        return value
