"""Outbound email integration.

The transport is the single seam where a provider failure surfaces:
``send_email`` raises ``EmailSendError``, which the notification delivery job
catches to record the error and schedule a retry. When ``email_enabled`` is
False (dev/test default) the transport logs instead of sending, so the whole
pipeline is exercisable without a provider.
"""

from __future__ import annotations

import logging
import smtplib
import uuid
from dataclasses import dataclass
from email.message import EmailMessage as _MimeMessage

from src.core.config import settings

logger = logging.getLogger("src.integrations.email")


class EmailSendError(RuntimeError):
    """Raised when the configured transport cannot deliver a message."""


@dataclass
class EmailMessage:
    to: str
    subject: str
    body: str


def send_email(message: EmailMessage) -> str:
    """Deliver ``message`` and return a provider message id.

    Raises ``EmailSendError`` on transport failure so the caller can retry.
    """
    if not settings.email_enabled:
        logger.info("email disabled; would send %r to %s", message.subject, message.to)
        return f"disabled-{uuid.uuid4().hex}"

    if not settings.smtp_host:
        raise EmailSendError("SMTP host is not configured")

    mime = _MimeMessage()
    mime["From"] = settings.email_from_address
    mime["To"] = message.to
    mime["Subject"] = message.subject
    mime.set_content(message.body)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            if settings.smtp_use_tls:
                server.starttls()
            if settings.smtp_username:
                server.login(settings.smtp_username, settings.smtp_password or "")
            server.send_message(mime)
    except (OSError, smtplib.SMTPException) as exc:
        raise EmailSendError(str(exc)) from exc
    return f"smtp-{uuid.uuid4().hex}"
