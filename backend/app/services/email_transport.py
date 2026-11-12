from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from ..config import settings


class SMTPNotConfigured(RuntimeError):
    pass


def render_html_email(to_email: str, subject: str, html_body: str) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.EMAIL_FROM or settings.SMTP_USER
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html"))
    return msg


def send_via_smtp(msg: MIMEMultipart) -> None:
    host = settings.SMTP_HOST
    port = settings.SMTP_PORT
    user = settings.SMTP_USER
    password = settings.SMTP_PASS

    if not host:
        raise SMTPNotConfigured("SMTP transport is not configured.")

    with smtplib.SMTP(host, port, timeout=30) as server:
        server.ehlo()
        if port == 587:
            server.starttls()
            server.ehlo()
        if user and password:
            server.login(user, password)
        server.send_message(msg)


class BrevoDeliveryError(RuntimeError):
    """Non-sensitive error: never include API keys or provider response bodies."""


def send_via_brevo(to_email: str, subject: str, html_body: str) -> None:
    """Send a transactional email through Brevo's HTTPS API (Render Free safe).

    The sending address must be verified in Brevo. This function deliberately
    does not retry: repeating a verification email can create duplicate sends.
    """
    import httpx

    if not settings.BREVO_API_KEY or not settings.BREVO_SENDER_EMAIL:
        raise BrevoDeliveryError("Brevo email delivery is not configured.")

    payload = {
        "sender": {
            "email": settings.BREVO_SENDER_EMAIL,
            "name": settings.BREVO_SENDER_NAME,
        },
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_body,
    }
    try:
        response = httpx.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "accept": "application/json",
                "content-type": "application/json",
                "api-key": settings.BREVO_API_KEY,
            },
            json=payload,
            timeout=10.0,
        )
    except httpx.HTTPError:
        raise BrevoDeliveryError("Brevo HTTPS email transport unavailable.") from None
    if response.status_code != 201:
        # Do not forward Brevo response bodies to logs: they may contain account details.
        raise BrevoDeliveryError(
            f"Brevo HTTPS email request rejected (HTTP {response.status_code})."
        )
