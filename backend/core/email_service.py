"""
core/email_service.py — Email sending via SendGrid.

Falls back to logging the link if SENDGRID_API_KEY is not set (local dev).
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_API_KEY = os.environ.get("SENDGRID_API_KEY", "")
_FROM_EMAIL = os.environ.get("EMAIL_FROM_ADDRESS", "noreply@clearvoice.app")
_APP_NAME = "ClearVoice"


def _send_email(to_email: str, subject: str, html_content: str) -> bool:
    """Send an email via SendGrid. Returns True on success."""
    if not _API_KEY:
        logger.warning("SENDGRID_API_KEY not set — email not sent. Subject: %s, To: %s", subject, to_email)
        return False

    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail

    message = Mail(
        from_email=_FROM_EMAIL,
        to_emails=to_email,
        subject=subject,
        html_content=html_content,
    )
    try:
        sg = SendGridAPIClient(_API_KEY)
        response = sg.send(message)
        logger.info("Email sent to %s — status %s", to_email, response.status_code)
        return 200 <= response.status_code < 300
    except Exception:
        logger.exception("Failed to send email to %s", to_email)
        return False


def send_verification_email(to_email: str, token: str, frontend_base_url: str) -> bool:
    """Send an email verification link."""
    link = f"{frontend_base_url}/auth/verify-email?token={token}"
    logger.info("Verification link for %s: %s", to_email, link)

    subject = f"{_APP_NAME} — Verify your email"
    html = f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto;">
        <h2 style="color: #1c1917;">{_APP_NAME}</h2>
        <p>Click the link below to verify your email address:</p>
        <p><a href="{link}" style="display: inline-block; background: #059669; color: white;
              padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: 500;">
            Verify Email
        </a></p>
        <p style="color: #78716c; font-size: 14px;">This link expires in 24 hours.</p>
        <p style="color: #78716c; font-size: 14px;">If you didn't create an account, you can ignore this email.</p>
    </div>
    """
    return _send_email(to_email, subject, html)


def send_password_reset_email(to_email: str, token: str, frontend_base_url: str) -> bool:
    """Send a password reset link."""
    link = f"{frontend_base_url}/auth/reset-password?token={token}"
    logger.info("Password reset link for %s: %s", to_email, link)

    subject = f"{_APP_NAME} — Reset your password"
    html = f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto;">
        <h2 style="color: #1c1917;">{_APP_NAME}</h2>
        <p>Click the link below to reset your password:</p>
        <p><a href="{link}" style="display: inline-block; background: #059669; color: white;
              padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: 500;">
            Reset Password
        </a></p>
        <p style="color: #78716c; font-size: 14px;">This link expires in 1 hour.</p>
        <p style="color: #78716c; font-size: 14px;">If you didn't request a password reset, you can ignore this email.</p>
    </div>
    """
    return _send_email(to_email, subject, html)
