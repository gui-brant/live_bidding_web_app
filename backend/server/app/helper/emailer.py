from __future__ import annotations

import asyncio
import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "donotreply.kognativesales7@gmail.com")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "tnof pqwg ihhk pqxl")
SMTP_FROM = os.getenv("SMTP_FROM", "donotreply.kognativesales7@gmail.com") or SMTP_USERNAME
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() != "false"


def _send_sync(to_email: str, subject: str, body: str) -> None:
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        logger.warning("SMTP credentials not configured; skipping email.")
        return

    msg = EmailMessage()
    msg["From"] = SMTP_FROM or SMTP_USERNAME
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
        server.ehlo()
        if SMTP_USE_TLS:
            server.starttls()
            server.ehlo()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(msg)


async def send_notification_email(to_email: str, subject: str, body: str) -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _send_sync, to_email, subject, body)
