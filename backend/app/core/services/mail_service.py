"""Sending email (stage 98: forgot-password links), with Python's built-in smtplib.

Configured by environment variables, kept on the server only:
    SMTP_USER       the Gmail address that sends (e.g. you@gmail.com)
    SMTP_PASSWORD   a Gmail APP PASSWORD (Google account > Security > App passwords),
                    never your normal password
    SMTP_HOST / SMTP_PORT   default smtp.gmail.com / 465 (SSL)
    MAIL_FROM       optional display sender, default SMTP_USER
    APP_URL         the website's address, used to build links (default localhost:3000)

When SMTP isn't configured, nothing is sent and the server log says so; the link itself
is never logged (a log is not a safe place for a password-reset link).
"""

import logging
import os
import smtplib
from email.message import EmailMessage

log = logging.getLogger(__name__)


def configured() -> bool:
    return bool((os.getenv("SMTP_USER") or "").strip() and (os.getenv("SMTP_PASSWORD") or "").strip())


def app_url() -> str:
    return (os.getenv("APP_URL") or "http://localhost:3000").strip().rstrip("/")


def send_email(to: str, subject: str, body: str) -> bool:
    """Send a plain-text email. True if handed to the mail server; never raises (a mail
    problem must not turn into a page error, and must not reveal whether an account exists)."""
    if not configured():
        log.warning("Email not sent (SMTP_USER / SMTP_PASSWORD not set): %r", subject)
        return False
    user = os.getenv("SMTP_USER", "").strip()
    message = EmailMessage()
    message["From"] = (os.getenv("MAIL_FROM") or "").strip() or user
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    try:
        host = (os.getenv("SMTP_HOST") or "smtp.gmail.com").strip()
        port = int(os.getenv("SMTP_PORT") or "465")
        with smtplib.SMTP_SSL(host, port, timeout=20) as server:
            server.login(user, os.getenv("SMTP_PASSWORD", "").strip())
            server.send_message(message)
        return True
    except (OSError, smtplib.SMTPException) as error:
        log.warning("Email not sent (%s): %r", type(error).__name__, subject)
        return False


def reset_email(name: str | None, link: str, minutes: int) -> tuple[str, str]:
    """(subject, body) of the forgot-password email. It holds the link, never a password."""
    hello = f"Hi {name}," if name else "Hi,"
    body = (
        f"{hello}\n\n"
        "Someone asked to reset the password of your Career AI account. To choose a new one, open this link:\n\n"
        f"{link}\n\n"
        f"The link works once, for {minutes} minutes. If you didn't ask for this, ignore this email: "
        "your password stays the same.\n\n"
        "Career AI\n"
    )
    return "Reset your Career AI password", body
