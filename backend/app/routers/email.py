import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import settings
from ..database import get_db
from ..email_templates import weekly_digest
from ..models import User
from ..services.email_transport import SMTPNotConfigured, render_html_email, send_via_smtp
from .crm import weekly_report, goal_progress

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/crm/email", tags=["email"])


def _collect_digest_data(db: Session, user: User) -> dict:
    """Gather all data needed for the weekly digest email."""
    report = weekly_report(db=db, user=user)
    goals = goal_progress(db=db, user=user)
    return {**report, "goal_progress": goals}


# Compatibility aliases keep the existing digest route/tests stable while the
# transport itself lives in the service layer and is shared by reminders.
_render_email = render_html_email
_send_via_smtp = send_via_smtp


@router.post("/weekly-digest")
def send_weekly_digest(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    data = _collect_digest_data(db, user)
    subject = f"JobGrid Weekly Digest — {data.get('applied', 0)} applied, {data.get('opened', 0)} visited"
    html = weekly_digest(subject, data)
    msg = _render_email(user.email, subject, html)

    try:
        _send_via_smtp(msg)
        return {"status": "sent", "to": user.email, "subject": subject}
    except SMTPNotConfigured:
        logger.info(
            "SMTP not configured — email logged to console.\n"
            "Subject: %s\nTo: %s\nConfigure SMTP_HOST to enable sending.",
            subject, user.email,
        )
        return {"status": "logged", "to": user.email, "subject": subject, "html": html}
    except Exception as exc:
        logger.error("Failed to send digest email: %s", exc)
        raise HTTPException(502, f"Email send failed: {exc}")


@router.get("/preview")
def preview_weekly_digest(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    data = _collect_digest_data(db, user)
    subject = f"JobGrid Weekly Digest — {data.get('applied', 0)} applied, {data.get('opened', 0)} opened"
    html = weekly_digest(subject, data)
    return HTMLResponse(content=html)
