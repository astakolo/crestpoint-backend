from django.conf import settings
from django.db import models
from django.utils import timezone

from crestpoint_credit.core.models import TimestampedModel


class NotificationChannel(models.TextChoices):
    EMAIL = "email", "Email"
    SMS = "sms", "SMS"
    IN_APP = "in_app", "In-App"


class NotificationType(models.TextChoices):
    TRANSACTION = "transaction", "Transaction"
    SECURITY = "security", "Security"
    ACCOUNT = "account", "Account"
    SYSTEM = "system", "System"
    KYC = "kyc", "KYC"
    PAYMENT = "payment", "Payment"


class NotificationStatus(models.TextChoices):
    SENT = "sent", "Sent"
    DELIVERED = "delivered", "Delivered"
    FAILED = "failed", "Failed"
    READ = "read", "Read"


class Notification(TimestampedModel):
    """Represents a notification sent to a user via one or more channels."""

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="notifications",
        on_delete=models.CASCADE,
        db_index=True,
    )
    title = models.CharField(max_length=200)
    message = models.TextField()
    notification_type = models.CharField(
        max_length=20,
        choices=NotificationType.choices,
    )
    channel = models.CharField(
        max_length=20,
        choices=NotificationChannel.choices,
    )
    status = models.CharField(
        max_length=20,
        choices=NotificationStatus.choices,
        default=NotificationStatus.SENT,
    )
    is_read = models.BooleanField(default=False)
    data = models.JSONField(default=dict, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "created_at"], name="ix_notif_user_created"),
            models.Index(fields=["user", "is_read"], name="ix_notif_user_is_read"),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} - {self.user.email}"

    def mark_as_read(self):
        """Mark this notification as read with a timestamp."""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.status = NotificationStatus.READ
            self.save(update_fields=["is_read", "read_at", "status", "updated_at"])

    @classmethod
    def mark_all_as_read_for_user(cls, user_id):
        """Mark all unread notifications as read for a given user."""
        cls.objects.filter(
            user_id=user_id,
            is_read=False,
        ).update(
            is_read=True,
            read_at=timezone.now(),
            status=NotificationStatus.READ,
        )
