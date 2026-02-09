"""Email sending via SMTP (Gmail) or Resend API."""

import logging
import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from browserfriend.config import get_config

logger = logging.getLogger(__name__)


def _send_via_smtp(to_email: str, subject: str, html_content: str) -> bool:
    """Send email via SMTP (e.g., Gmail).

    Requires SMTP_USERNAME and SMTP_PASSWORD in .env.
    For Gmail, use an App Password: https://myaccount.google.com/apppasswords

    Returns:
        True if sent successfully, False otherwise
    """
    config = get_config()
    username = config.smtp_username
    password = config.smtp_password

    if not username or not password:
        logger.error(
            "SMTP credentials not configured. " "Set SMTP_USERNAME and SMTP_PASSWORD in .env"
        )
        return False

    host = config.smtp_host
    port = config.smtp_port

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"BrowserFriend <{username}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html_content, "html"))

    try:
        logger.info("Sending email via SMTP (%s:%d) to %s", host, port, to_email)
        context = ssl.create_default_context()
        with smtplib.SMTP(host, port) as server:
            server.starttls(context=context)
            server.login(username, password)
            server.sendmail(username, to_email, msg.as_string())
        logger.info("Email sent successfully via SMTP to %s", to_email)
        return True
    except Exception as exc:
        logger.error("SMTP send failed: %s", exc)
        return False


def _send_via_resend(to_email: str, subject: str, html_content: str) -> bool:
    """Send email via Resend API.

    Returns:
        True if sent successfully, False otherwise
    """
    import os

    import resend

    config = get_config()
    api_key = config.resend_api_key or os.getenv("RESEND_API_KEY")
    if not api_key or api_key == "your_resend_api_key_here":
        logger.error("RESEND_API_KEY not configured. Set it in .env or environment.")
        return False

    resend.api_key = api_key
    from_email = os.getenv("RESEND_FROM_EMAIL", "BrowserFriend <onboarding@resend.dev>")

    try:
        logger.info("Sending email via Resend to %s", to_email)
        response = resend.Emails.send(
            {
                "from": from_email,
                "to": to_email,
                "subject": subject,
                "html": html_content,
            }
        )
        email_id = response.get("id", "unknown") if isinstance(response, dict) else "sent"
        logger.info("Email sent successfully via Resend - ID: %s", email_id)
        return True
    except Exception as exc:
        logger.error("Resend send failed: %s", exc)
        return False


def send_dashboard_email(to_email: str, html_content: str) -> bool:
    """Send dashboard email using the configured provider (smtp or resend).

    The provider is set via EMAIL_PROVIDER in .env (default: smtp).

    Args:
        to_email: Recipient email address
        html_content: Rendered HTML dashboard

    Returns:
        True if email sent successfully, False otherwise
    """
    config = get_config()
    provider = config.email_provider.lower()
    subject = f"Your BrowserFriend Dashboard - {datetime.now().strftime('%B %d, %Y')}"

    if provider == "resend":
        return _send_via_resend(to_email, subject, html_content)
    else:
        return _send_via_smtp(to_email, subject, html_content)
