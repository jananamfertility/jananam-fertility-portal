"""
Best-effort out-of-band email alert for when the WhatsApp bot flags a
message as needing human attention (a possible medical emergency, or an
explicit request to talk to a person).

This is deliberately optional and safe-by-default: without SMTP settings
configured, `send_emergency_email` just logs and returns False — the alert
still lands in the `staff_alerts` table and shows in the admin portal
either way (see bot_flow._raise_staff_alert), this only adds an email on
top of that when a mail server is available.
"""
import logging
import smtplib
from email.message import EmailMessage

from .config import get_settings

logger = logging.getLogger("alerting")


def _configured() -> bool:
    s = get_settings()
    return bool(s.smtp_host and s.smtp_from and s.staff_alert_email_to)


def send_emergency_email(phone: str, excerpt: str) -> bool:
    if not _configured():
        logger.warning(
            "Emergency/needs-human alert NOT emailed (SMTP not configured) — phone=%s excerpt=%r. "
            "It is still recorded in staff_alerts and visible in the admin portal.",
            phone,
            excerpt,
        )
        return False

    settings = get_settings()
    msg = EmailMessage()
    msg["Subject"] = f"⚠️ WhatsApp bot flagged a message needing attention ({phone})"
    msg["From"] = settings.smtp_from
    msg["To"] = settings.staff_alert_email_to
    msg.set_content(
        "The Jananam Fertility Centre WhatsApp bot flagged an inbound message as needing human "
        f"attention (possible medical emergency, or an explicit request to speak to a person).\n\n"
        f"From: {phone}\n"
        f"Message: {excerpt}\n\n"
        "Open the admin portal's Marketing tab -> Alerts to see the full conversation and "
        "acknowledge this."
    )
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            if settings.smtp_use_tls:
                server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        return True
    except Exception:
        logger.exception("Failed to send emergency alert email to %s", settings.staff_alert_email_to)
        return False
