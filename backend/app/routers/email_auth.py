"""Email/password authentication with verified mailbox ownership.

New signups never claim an existing OAuth account or create a User until the
mailbox owner explicitly verifies a one-time token.
"""
import hashlib
import secrets
from datetime import datetime, timedelta
from html import escape
from urllib.parse import quote

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import create_token
from ..config import cookie_security_options, settings
from ..database import get_db
from ..models import EmailActionToken, EmailAuthRateLimit, PasswordCredential, User
from ..services.email_transport import render_html_email, send_via_brevo, send_via_smtp

router = APIRouter(prefix="/auth/email", tags=["auth"])
_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
_GENERIC_SENT = "If this email is eligible, check your inbox for a link."
_DUMMY_PASSWORD_HASH = _hasher.hash("not-a-real-password-used-for-timing")


class EmailInput(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class EmailPasswordInput(EmailInput):
    password: str = Field(min_length=15, max_length=128)


class TokenInput(BaseModel):
    token: str = Field(min_length=30, max_length=128)


class ResetPasswordInput(TokenInput):
    password: str = Field(min_length=15, max_length=128)


def _enabled(request: Request) -> None:
    if not settings.EMAIL_PASSWORD_AUTH_ENABLED:
        raise HTTPException(404, "Not found")
    # JSON-only API + explicit origin checks prevent cross-site login CSRF.
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") not in [item.rstrip("/") for item in settings.CORS_ORIGINS]:
        raise HTTPException(403, "Origin not allowed")


def _normalized_email(value: str) -> str:
    email = value.strip().lower()
    if len(email) > 320 or email.count("@") != 1 or any(c.isspace() for c in email):
        raise HTTPException(422, "Invalid email address")
    local, domain = email.rsplit("@", 1)
    if (
        not local or len(local) > 64 or not domain or len(domain) > 255
        or "." not in domain or domain.startswith(".") or domain.endswith(".")
        or ".." in domain or any(c in domain for c in "/\\:")
    ):
        raise HTTPException(422, "Invalid email address")
    return email


def _mail_available() -> None:
    if settings.EMAIL_AUTH_TRANSPORT == "brevo":
        if not settings.BREVO_API_KEY or not settings.BREVO_SENDER_EMAIL:
            raise HTTPException(503, "Email delivery has not been configured")
    elif settings.EMAIL_AUTH_TRANSPORT == "smtp":
        if not settings.SMTP_HOST or not (settings.EMAIL_FROM or settings.SMTP_USER):
            raise HTTPException(503, "Email delivery has not been configured")
    else:
        raise HTTPException(503, "Email delivery transport is not supported")


def _user(db: Session, email: str) -> User | None:
    return db.query(User).filter(func.lower(User.email) == email).first()


def _rate_guard(db: Session, request: Request, action: str, email: str) -> None:
    """Postgres/SQLite atomic shared counters, not an in-memory worker limit."""
    now = datetime.utcnow()
    window = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
    peer = request.client.host if request.client else "unknown"
    for identifier, limit in ((f"peer:{peer}", 80), (f"email:{email}", 5)):
        key_hash = hashlib.sha256(f"{action}:{identifier}".encode()).hexdigest()
        count = db.execute(
            text(
                "INSERT INTO email_auth_rate_limits (key_hash, window_start, attempts) "
                "VALUES (:key_hash, :window_start, 1) "
                "ON CONFLICT (key_hash, window_start) "
                "DO UPDATE SET attempts = email_auth_rate_limits.attempts + 1 "
                "RETURNING attempts"
            ),
            {"key_hash": key_hash, "window_start": window},
        ).scalar_one()
        db.commit()
        if count > limit:
            seconds = max(1, int((window + timedelta(minutes=15) - now).total_seconds()))
            raise HTTPException(
                429, "Too many attempts. Try again later.",
                headers={"Retry-After": str(seconds), "Cache-Control": "no-store"},
            )


def _send_link(email: str, token: str, purpose: str) -> None:
    # A URL fragment keeps the token out of frontend/CDN request logs.
    url = (
        settings.FRONTEND_URL.rstrip("/") + "/login#email_action=" + purpose
        + "&token=" + quote(token, safe="")
    )
    title = "Verify your JobGrid email" if purpose == "verify" else "Reset your JobGrid password"
    body = (
        "<p>Use this one-time link to " +
        ("verify your email" if purpose == "verify" else "set a new password") +
        ":</p><p><a href=\"" + escape(url, quote=True) + "\">" +
        escape(title) + "</a></p><p>If you didn't request this, ignore it. "
        "The link expires in 30 minutes.</p>"
    )
    if settings.EMAIL_AUTH_TRANSPORT == "brevo":
        send_via_brevo(email, title, body)
    else:
        send_via_smtp(render_html_email(email, title, body))


def _remember_token(db: Session, email: str, purpose: str, password_hash: str | None = None):
    now = datetime.utcnow()
    # Do not accumulate unused tokens forever.
    db.query(EmailActionToken).filter(EmailActionToken.expires_at < now).delete(
        synchronize_session=False
    )
    db.query(EmailActionToken).filter_by(email=email, purpose=purpose).delete(
        synchronize_session=False
    )
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
    db.add(EmailActionToken(
        email=email, purpose=purpose, token_hash=token_hash,
        password_hash=password_hash, expires_at=now + timedelta(minutes=30),
    ))
    db.commit()
    return token, token_hash


def _issue_session(user: User) -> JSONResponse:
    response = JSONResponse({"id": user.id, "email": user.email})
    response.set_cookie(
        "session_token", create_token(user), max_age=7 * 24 * 60 * 60,
        httponly=True, **cookie_security_options(settings.ENVIRONMENT),
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post("/register", status_code=202)
def register(payload: EmailPasswordInput, request: Request, db: Session = Depends(get_db)):
    _enabled(request)
    _mail_available()
    email = _normalized_email(payload.email)
    _rate_guard(db, request, "register", email)
    # Always hash to make the account-existence response less distinguishable.
    password_hash = _hasher.hash(payload.password)
    if _user(db, email) is None:
        token, token_hash = _remember_token(db, email, "verify", password_hash)
        try:
            _send_link(email, token, "verify")
        except Exception:
            db.query(EmailActionToken).filter_by(token_hash=token_hash).delete()
            db.commit()
            raise HTTPException(503, "Email delivery is unavailable. Please retry later.")
    return {"message": _GENERIC_SENT}


@router.post("/verify")
def verify(payload: TokenInput, request: Request, db: Session = Depends(get_db)):
    _enabled(request)
    token_hash = hashlib.sha256(payload.token.encode()).hexdigest()
    pending = db.query(EmailActionToken).filter_by(
        token_hash=token_hash, purpose="verify"
    ).with_for_update().first()
    if pending is None or pending.expires_at <= datetime.utcnow():
        raise HTTPException(400, "Verification link is invalid or expired")
    if _user(db, pending.email) is not None:
        # Never bind a newly registered password to an existing OAuth identity.
        db.delete(pending)
        db.commit()
        raise HTTPException(400, "This address already has an account. Use password reset.")
    try:
        user = User(email=pending.email)
        db.add(user)
        db.flush()
        db.add(PasswordCredential(user_id=user.id, password_hash=pending.password_hash))
        db.delete(pending)
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(400, "This address already has an account. Use password reset.")
    return _issue_session(user)


@router.post("/login")
def login(payload: EmailPasswordInput, request: Request, db: Session = Depends(get_db)):
    _enabled(request)
    email = _normalized_email(payload.email)
    _rate_guard(db, request, "login", email)
    user = _user(db, email)
    credential = (
        db.get(PasswordCredential, user.id) if user is not None else None
    )
    candidate_hash = credential.password_hash if credential else _DUMMY_PASSWORD_HASH
    try:
        valid = _hasher.verify(candidate_hash, payload.password)
    except (VerificationError, InvalidHashError):
        valid = False
    if not valid or user is None or credential is None:
        raise HTTPException(
            401, "Invalid email or password", headers={"Cache-Control": "no-store"}
        )
    if _hasher.check_needs_rehash(credential.password_hash):
        credential.password_hash = _hasher.hash(payload.password)
        db.commit()
    return _issue_session(user)


@router.post("/forgot", status_code=202)
def forgot(payload: EmailInput, request: Request, db: Session = Depends(get_db)):
    _enabled(request)
    _mail_available()
    email = _normalized_email(payload.email)
    _rate_guard(db, request, "forgot", email)
    # Existing OAuth users can establish a password by proving mailbox control.
    if _user(db, email) is not None:
        token, token_hash = _remember_token(db, email, "reset")
        try:
            _send_link(email, token, "reset")
        except Exception:
            db.query(EmailActionToken).filter_by(token_hash=token_hash).delete()
            db.commit()
            raise HTTPException(503, "Email delivery is unavailable. Please retry later.")
    return {"message": _GENERIC_SENT}


@router.post("/reset")
def reset(payload: ResetPasswordInput, request: Request, db: Session = Depends(get_db)):
    _enabled(request)
    token_hash = hashlib.sha256(payload.token.encode()).hexdigest()
    pending = db.query(EmailActionToken).filter_by(
        token_hash=token_hash, purpose="reset"
    ).with_for_update().first()
    if pending is None or pending.expires_at <= datetime.utcnow():
        raise HTTPException(400, "Reset link is invalid or expired")
    user = _user(db, pending.email)
    if user is None:
        raise HTTPException(400, "Reset link is invalid or expired")
    credential = db.get(PasswordCredential, user.id)
    new_hash = _hasher.hash(payload.password)
    if credential is None:
        db.add(PasswordCredential(user_id=user.id, password_hash=new_hash))
    else:
        credential.password_hash = new_hash
    db.query(EmailActionToken).filter_by(email=pending.email, purpose="reset").delete(
        synchronize_session=False
    )
    db.commit()
    return _issue_session(user)
