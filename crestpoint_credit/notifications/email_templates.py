"""
Utility functions for rendering CrestPoint-branded HTML email templates.

Usage:
    from crestpoint_credit.notifications.email_templates import (
        render_otp_email,
        render_password_reset_email,
        render_notification_email,
    )
"""

from django.template.loader import render_to_string


def _strip_trailing_newlines(text):
    """Remove excessive trailing whitespace from rendered template."""
    lines = text.splitlines()
    # Find last non-empty line
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines) + "\n"


def render_otp_email(otp_code, user_name=None, heading=None, intro_text=None):
    """
    Render a branded HTML email for OTP verification codes.

    Args:
        otp_code: The 6-digit OTP code string.
        user_name: Optional user's first name for greeting.
        heading: Optional heading (default: "Verify Your Identity").
        intro_text: Optional intro paragraph.

    Returns:
        str: Complete HTML email content.
    """
    html = render_to_string("emails/otp_email.html", {
        "otp_code": otp_code,
        "user_name": user_name,
        "heading": heading or "Verify Your Identity",
        "intro_text": intro_text,
    })
    return _strip_trailing_newlines(html)


def render_password_reset_email(reset_url, user_name=None):
    """
    Render a branded HTML email for password reset.

    Args:
        reset_url: The full URL for the password reset link.
        user_name: Optional user's first name for greeting.

    Returns:
        str: Complete HTML email content.
    """
    html = render_to_string("emails/password_reset.html", {
        "reset_url": reset_url,
        "user_name": user_name,
    })
    return _strip_trailing_newlines(html)


def render_notification_email(title, message, user_name=None, details=None,
                                cta_url=None, cta_text=None,
                                is_success=False, success_message=None,
                                warning_text=None):
    """
    Render a branded HTML email for general notifications (transactions,
    security alerts, KYC updates, etc.).

    Args:
        title: Notification title.
        message: Notification body message.
        user_name: Optional user's first name for greeting.
        details: Optional dict of label-value detail rows.
        cta_url: Optional CTA button URL.
        cta_text: Optional CTA button text.
        is_success: Whether this is a success notification.
        success_message: Optional success message for green box.
        warning_text: Optional warning message for yellow box.

    Returns:
        str: Complete HTML email content.
    """
    html = render_to_string("emails/notification_email.html", {
        "title": title,
        "message": message,
        "user_name": user_name,
        "details": details or {},
        "cta_url": cta_url,
        "cta_text": cta_text,
        "is_success": is_success,
        "success_message": success_message,
        "warning_text": warning_text,
    })
    return _strip_trailing_newlines(html)
