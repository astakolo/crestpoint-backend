import logging
import os

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_email_notification(self, notification_id):
    """Asynchronously send an email notification."""
    try:
        from .models import Notification

        notification = Notification.objects.get(id=notification_id)
        from .services import EmailService

        success = EmailService.send_email(
            to=notification.user.email,
            subject=notification.title,
            body=notification.message,
        )
        if success:
            notification.status = "delivered"
            notification.sent_at = timezone.now()
            notification.save(update_fields=["status", "sent_at"])
        else:
            notification.status = "failed"
            notification.save(update_fields=["status"])
    except Exception as exc:
        logger.error(f"Email notification failed: {exc}")
        self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def send_sms_notification(self, notification_id):
    """Asynchronously send an SMS notification."""
    try:
        from .models import Notification

        notification = Notification.objects.get(id=notification_id)
        from .services import MockSMSService

        success = MockSMSService.send_sms(
            phone=notification.user.phone,
            message=notification.message,
        )
        if success:
            notification.status = "delivered"
            notification.sent_at = timezone.now()
            notification.save(update_fields=["status", "sent_at"])
        else:
            notification.status = "failed"
            notification.save(update_fields=["status"])
    except Exception as exc:
        logger.error(f"SMS notification failed: {exc}")
        self.retry(exc=exc)


@shared_task
def send_bulk_notification(user_ids, title, message, notification_type, channel="in_app"):
    """Send a notification to multiple users at once."""
    from .models import Notification
    from .services import NotificationService

    notifications = []
    for user_id in user_ids:
        notification = NotificationService.create_notification(
            user=user_id,
            title=title,
            message=message,
            notification_type=notification_type,
            channel=channel,
        )
        notifications.append(notification)
    return [n.id for n in notifications]


@shared_task
def send_password_reset_email(user_email, reset_token):
    """Send a password reset email to the specified user."""
    subject = "CrestPoint Credit - Password Reset"
    reset_url = (
        f"{os.environ.get('FRONTEND_URL', 'http://localhost:3000')}"
        f"/reset-password?token={reset_token}"
    )
    body = f"""
    Hello,

    You requested a password reset for your CrestPoint Credit account.

    Click the link below to reset your password:
    {reset_url}

    This link will expire in 1 hour.

    If you didn't request this, please ignore this email.

    CrestPoint Credit Security Team
    """

    send_mail(
        subject=subject,
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user_email],
        fail_silently=False,
    )
