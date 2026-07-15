import logging

from django.conf import settings
from django.core.mail import send_mail

from crestpoint_credit.accounts.models import User

logger = logging.getLogger(__name__)


class EmailService:
    """Service for sending email notifications."""

    @staticmethod
    def send_email(to, subject, body, html_body=None):
        """
        Send an email notification.

        Args:
            to: Recipient email address.
            subject: Email subject line.
            body: Plain-text email body.
            html_body: Optional HTML email body.

        Returns:
            bool: True if the email was sent successfully, False otherwise.
        """
        try:
            send_mail(
                subject=subject,
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[to],
                fail_silently=False,
                html_message=html_body,
            )
            logger.info("Email sent successfully to %s: %s", to, subject)
            return True
        except Exception as exc:
            logger.error("Failed to send email to %s: %s", to, exc)
            return False


class MockSMSService:
    """Mock SMS service for development and testing."""

    @staticmethod
    def send_sms(phone, message):
        """
        Send an SMS notification (mock implementation).

        Args:
            phone: Recipient phone number.
            message: SMS message content.

        Returns:
            bool: Always True (simulating success).
        """
        logger.info(
            "MOCK SMS sent to %s: %s",
            phone,
            message,
        )
        return True


class NotificationService:
    """Central service for creating and dispatching notifications."""

    @staticmethod
    def create_notification(user, title, message, notification_type, channel="in_app", data=None):
        """
        Create a notification record and dispatch it.

        Args:
            user: User instance or user ID.
            title: Notification title.
            message: Notification message body.
            notification_type: One of the NotificationType choices.
            channel: One of the NotificationChannel choices (default: in_app).
            data: Optional dict payload for the notification.

        Returns:
            Notification: The created notification instance.
        """
        from .models import Notification

        if isinstance(user, int):
            user = User.objects.get(id=user)

        notification = Notification.objects.create(
            user=user,
            title=title,
            message=message,
            notification_type=notification_type,
            channel=channel,
            data=data or {},
        )
        NotificationService.dispatch_notification(notification)
        return notification

    @staticmethod
    def dispatch_notification(notification):
        """
        Dispatch a notification based on its channel.

        Email and SMS notifications are sent asynchronously via Celery tasks.
        In-app notifications are already persisted in the database.
        """
        from .tasks import send_email_notification, send_sms_notification

        if notification.channel == "email":
            send_email_notification.delay(notification.id)
        elif notification.channel == "sms":
            send_sms_notification.delay(notification.id)
        # in_app notifications are already saved, no further dispatch needed

    @staticmethod
    def send_transaction_notification(user, transaction):
        """
        Create and dispatch a notification for a transaction event.

        Args:
            user: User instance.
            transaction: Transaction instance with type, amount, etc.
        """
        txn_type = transaction.transaction_type
        amount = float(transaction.amount)

        type_messages = {
            "deposit": {
                "title": "Deposit Received",
                "message": f"Your account has been credited with ${amount:,.2f}. Reference: {transaction.reference}",
            },
            "withdrawal": {
                "title": "Withdrawal Processed",
                "message": f"Your withdrawal of ${amount:,.2f} has been processed. Reference: {transaction.reference}",
            },
            "transfer_in": {
                "title": "Transfer Received",
                "message": f"You received a transfer of ${amount:,.2f}. Reference: {transaction.reference}",
            },
            "transfer_out": {
                "title": "Transfer Sent",
                "message": f"Your transfer of ${amount:,.2f} has been sent. Reference: {transaction.reference}",
            },
            "payment": {
                "title": "Payment Processed",
                "message": f"Your payment of ${amount:,.2f} has been processed. Reference: {transaction.reference}",
            },
        }

        msg_data = type_messages.get(
            txn_type,
            {
                "title": "Transaction Update",
                "message": f"Transaction {transaction.reference} of ${amount:,.2f} has been processed.",
            },
        )

        # Create in-app notification
        NotificationService.create_notification(
            user=user,
            title=msg_data["title"],
            message=msg_data["message"],
            notification_type="transaction",
            channel="in_app",
            data={"transaction_id": transaction.id, "reference": transaction.reference},
        )

        # Also send email asynchronously
        from .tasks import send_email_notification
        from .models import Notification

        email_notification = Notification.objects.create(
            user=user,
            title=msg_data["title"],
            message=msg_data["message"],
            notification_type="transaction",
            channel="email",
            data={"transaction_id": transaction.id, "reference": transaction.reference},
        )
        send_email_notification.delay(email_notification.id)

    @staticmethod
    def send_security_alert(user, alert_type, details=""):
        """
        Create and dispatch a security alert notification.

        Args:
            user: User instance.
            alert_type: One of login_success, login_failed, password_changed,
                        account_locked, kyc_status.
            details: Additional details about the alert.
        """
        alert_messages = {
            "login_success": {
                "title": "New Login Detected",
                "message": f"A new login to your CrestPoint Credit account was detected. {details}",
            },
            "login_failed": {
                "title": "Failed Login Attempt",
                "message": f"A failed login attempt was made on your CrestPoint Credit account. {details}",
            },
            "password_changed": {
                "title": "Password Changed",
                "message": "Your CrestPoint Credit account password has been changed successfully.",
            },
            "account_locked": {
                "title": "Account Locked",
                "message": f"Your CrestPoint Credit account has been locked. {details}",
            },
            "kyc_status": {
                "title": "KYC Status Update",
                "message": f"Your KYC verification status has been updated. {details}",
            },
        }

        msg_data = alert_messages.get(
            alert_type,
            {
                "title": "Security Alert",
                "message": f"A security event occurred on your account. {details}",
            },
        )

        # Send via in_app + email
        NotificationService.create_notification(
            user=user,
            title=msg_data["title"],
            message=msg_data["message"],
            notification_type="security",
            channel="in_app",
            data={"alert_type": alert_type},
        )

        from .tasks import send_email_notification
        from .models import Notification

        email_notification = Notification.objects.create(
            user=user,
            title=msg_data["title"],
            message=msg_data["message"],
            notification_type="security",
            channel="email",
            data={"alert_type": alert_type},
        )
        send_email_notification.delay(email_notification.id)

    @staticmethod
    def send_kyc_notification(user, status, rejection_reason=""):
        """
        Create and dispatch a KYC status change notification.

        Args:
            user: User instance.
            status: The new KYC status (approved, rejected, pending).
            rejection_reason: Reason for rejection (if applicable).
        """
        if status == "approved":
            title = "KYC Verification Approved"
            message = (
                "Congratulations! Your KYC verification has been approved. "
                "You now have full access to all CrestPoint Credit services."
            )
        elif status == "rejected":
            title = "KYC Verification Rejected"
            message = (
                f"Your KYC verification has been rejected. "
                f"Reason: {rejection_reason or 'Not specified'}. "
                "Please resubmit your documents for verification."
            )
        else:
            title = "KYC Verification Pending"
            message = (
                "Your KYC verification is currently under review. "
                "We will notify you once the review is complete."
            )

        data_payload = {"kyc_status": status}
        if rejection_reason:
            data_payload["rejection_reason"] = rejection_reason

        # Send via in_app + email
        NotificationService.create_notification(
            user=user,
            title=title,
            message=message,
            notification_type="kyc",
            channel="in_app",
            data=data_payload,
        )

        from .tasks import send_email_notification
        from .models import Notification

        email_notification = Notification.objects.create(
            user=user,
            title=title,
            message=message,
            notification_type="kyc",
            channel="email",
            data=data_payload,
        )
        send_email_notification.delay(email_notification.id)
