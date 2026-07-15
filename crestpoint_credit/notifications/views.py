from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Notification
from .serializers import NotificationSerializer, MarkAsReadSerializer


class NotificationListView(generics.ListAPIView):
    """
    GET /notifications/
    List the authenticated user's notifications.

    Query parameters:
        - is_read: Filter by read status (true/false).
        - notification_type: Filter by notification type (transaction, security, etc.).
        - channel: Filter by channel (email, sms, in_app).
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = NotificationSerializer
    ordering = ["-created_at"]

    def get_queryset(self):
        """Return notifications belonging to the authenticated user."""
        qs = Notification.objects.filter(user=self.request.user)

        # Filter by read status
        is_read = self.request.query_params.get("is_read")
        if is_read is not None:
            qs = qs.filter(is_read=is_read.lower() in ("true", "1", "yes"))

        # Filter by notification type
        notification_type = self.request.query_params.get("notification_type")
        if notification_type:
            qs = qs.filter(notification_type=notification_type)

        # Filter by channel
        channel = self.request.query_params.get("channel")
        if channel:
            qs = qs.filter(channel=channel)

        return qs


class MarkAsReadView(APIView):
    """
    POST /notifications/mark-read/
    Mark specified notifications as read.

    Body:
        {
            "notification_ids": [1, 2, 3]
        }
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = MarkAsReadSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        notification_ids = serializer.validated_data["notification_ids"]
        updated = Notification.objects.filter(
            id__in=notification_ids,
            user=request.user,
            is_read=False,
        ).update(is_read=True)

        return Response(
            {"detail": f"{updated} notification(s) marked as read."},
            status=status.HTTP_200_OK,
        )


class MarkAllAsReadView(APIView):
    """
    POST /notifications/mark-all-read/
    Mark all of the authenticated user's notifications as read.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        Notification.mark_all_as_read_for_user(request.user.id)
        return Response(
            {"detail": "All notifications marked as read."},
            status=status.HTTP_200_OK,
        )


class UnreadCountView(APIView):
    """
    GET /notifications/unread-count/
    Return the count of unread notifications for the authenticated user.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        count = Notification.objects.filter(
            user=request.user,
            is_read=False,
        ).count()
        return Response(
            {"unread_count": count},
            status=status.HTTP_200_OK,
        )
