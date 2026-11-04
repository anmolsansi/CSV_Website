"""Authenticated, read-only account handshake for the opt-in JobGrid extension.

No extension token is issued: the browser's existing HttpOnly session cookie
remains the sole authority for the selected JobGrid account.
"""
import json
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ..auth import get_current_user
from ..config import settings
from ..browser_memory_schemas import (
    BrowserMemoryValidationError, parse_browser_memory_payload,
    validate_apply_idempotency_key,
)
from ..database import get_db
from ..services.browser_memory import (
    BrowserVisitConflict, apply_browser_application_once,
    count_browser_memory_attempt, forget_browser_visits,
    read_browser_memory_facts, save_browser_visit, utc_z,
)
from ..models import User


router = APIRouter(prefix="/crm/browser-memory", tags=["browser-memory"])


class BrowserMemorySession(BaseModel):
    protocol_version: int
    account_id: int
    account_label: str


@router.get("/session", response_model=BrowserMemorySession)
def get_browser_memory_session(
    response: Response,
    user: User = Depends(get_current_user),
) -> BrowserMemorySession:
    """Return a minimal account identity, never a cookie, token or email."""
    response.headers["Cache-Control"] = "no-store"
    return BrowserMemorySession(
        protocol_version=1,
        account_id=user.id,
        account_label=f"JobGrid account {user.id}",
    )



class BrowserMemoryVisitOut(BaseModel):
    visited: bool
    first_visited_at: str | None


class BrowserMemoryMatchOut(BaseModel):
    track_id: int
    confidence: Literal["exact", "canonical", "possible"]
    reason: str
    company: str | None
    title: str | None
    status: str
    applied_at: str


class BrowserMemoryCheckOut(BaseModel):
    protocol_version: Literal[1]
    checked_at: str
    account_id: int
    visit: BrowserMemoryVisitOut
    matches: list[BrowserMemoryMatchOut]
    company_history_count: int
    company_known: bool
    lookup_complete: bool


@router.post("/check", response_model=BrowserMemoryCheckOut)
async def check_browser_memory(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BrowserMemoryCheckOut:
    """Read the authenticated owner's independent memory facts, never write."""
    response.headers["Cache-Control"] = "no-store"
    try:
        # The shared, committed counter includes malformed authenticated checks.
        # It must not be rolled back with the read-only request transaction.
        _count_or_reject(db, user_id=user.id, action="check")
        raw = await request.body()
        # The extension protocol has an 8 KiB transport envelope.
        if len(raw) > 8192:
            raise BrowserMemoryValidationError("Invalid browser-memory input.")
        try:
            payload = json.loads(raw)
        except (ValueError, UnicodeDecodeError) as exc:
            raise BrowserMemoryValidationError("Invalid browser-memory JSON.") from exc
        parsed = parse_browser_memory_payload("check", payload)
        facts = read_browser_memory_facts(
            db,
            user_id=user.id,
            url=parsed.url,
            company=parsed.company,
            title=parsed.title,
        )
    except BrowserMemoryValidationError as exc:
        raise _safe_error(exc.status_code, exc.code, exc.message, field=exc.field) from exc
    except BrowserVisitConflict as exc:
        raise _safe_error(exc.status_code, exc.code, exc.message) from exc
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        # Never include SQL parameter values or private URL metadata in logs.
        raise _safe_error(
            503, "browser_memory_unavailable",
            "Browser memory is temporarily unavailable.",
        ) from exc
    return BrowserMemoryCheckOut(
        protocol_version=1,
        checked_at=utc_z(datetime.now(timezone.utc)),
        account_id=user.id,
        **facts,
    )


# Browser-memory writes are guarded by exact frontend origin, fixed protocol
# header and the cookie-owner account expectation. Session cookies stay server-only.
def _safe_error(status: int, code: str, message: str, *, field: str | None = None,
                retry_after: int | None = None) -> HTTPException:
    detail = {"code": code, "message": message}
    if field is not None:
        detail["field"] = field
    headers = {"Cache-Control": "no-store"}
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return HTTPException(status_code=status, detail=detail, headers=headers)


def _browser_write_guard(request: Request, *, account_id: int) -> None:
    """Never trust a page-supplied account as authority or accept an arbitrary Origin."""
    expected = urlsplit(settings.FRONTEND_URL)
    allowed_origin = f"{expected.scheme}://{expected.netloc}"
    # Duplicate trust headers must never be interpreted differently by a
    # reverse proxy and the application. Reject them instead of picking one.
    origins = request.headers.getlist("origin")
    browser_headers = request.headers.getlist("x-jobgrid-browser")
    if (
        len(origins) != 1 or origins[0] != allowed_origin
        or len(browser_headers) != 1 or browser_headers[0] != "1"
    ):
        raise _safe_error(403, "origin_not_allowed", "Browser write origin not allowed.")
    account_headers = request.headers.getlist("x-jobgrid-account-id")
    asserted = account_headers[0] if len(account_headers) == 1 else None
    if asserted is None or not asserted.isascii() or not asserted.isdecimal():
        raise _safe_error(
            422, "invalid_browser_memory_payload",
            "Expected account header is required.", field="X-JobGrid-Account-ID",
        )
    if int(asserted) != account_id:
        raise _safe_error(
            409, "account_changed", "Selected JobGrid account changed."
        )


async def _read_browser_mutation_json(request: Request, kind: Literal["visit", "apply"]):
    raw = await request.body()
    if len(raw) > 8192:
        raise BrowserMemoryValidationError("Invalid browser-memory input.")
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise BrowserMemoryValidationError("Invalid browser-memory JSON.") from exc
    return parse_browser_memory_payload(kind, payload)


def _count_or_reject(db: Session, *, user_id: int, action: str) -> None:
    retry_after = count_browser_memory_attempt(db, user_id=user_id, action=action)
    if retry_after:
        raise _safe_error(
            429, "browser_memory_rate_limited",
            "Browser memory attempt limit reached.", retry_after=retry_after,
        )


def _mutation_error(db: Session, exc: Exception) -> HTTPException:
    db.rollback()
    if isinstance(exc, BrowserMemoryValidationError):
        return _safe_error(exc.status_code, exc.code, exc.message, field=exc.field)
    if isinstance(exc, BrowserVisitConflict):
        return _safe_error(exc.status_code, exc.code, exc.message)
    if isinstance(exc, HTTPException):
        return exc
    return _safe_error(
        503, "browser_memory_unavailable", "Browser memory is temporarily unavailable."
    )


@router.post("/visit")
async def visit_browser_memory(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    try:
        _count_or_reject(db, user_id=user.id, action="visit")
        _browser_write_guard(request, account_id=user.id)
        parsed = await _read_browser_mutation_json(request, "visit")
        result = save_browser_visit(db, user_id=user.id, url=parsed.url)
        body = result.as_response()
        db.commit()
        return body
    except (BrowserMemoryValidationError, BrowserVisitConflict, HTTPException, SQLAlchemyError) as exc:
        raise _mutation_error(db, exc) from exc


@router.post("/apply")
async def apply_browser_memory(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    try:
        _count_or_reject(db, user_id=user.id, action="apply")
        _browser_write_guard(request, account_id=user.id)
        key = validate_apply_idempotency_key(request.headers.get("idempotency-key"))
        parsed = await _read_browser_mutation_json(request, "apply")
        result = apply_browser_application_once(
            db, user_id=user.id, request_key=key, **parsed.model_dump(),
        )
        db.commit()
        return result
    except (BrowserMemoryValidationError, BrowserVisitConflict, HTTPException, SQLAlchemyError) as exc:
        raise _mutation_error(db, exc) from exc


@router.delete("/visits")
async def delete_browser_visits(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    try:
        _count_or_reject(db, user_id=user.id, action="forget")
        _browser_write_guard(request, account_id=user.id)
        if await request.body():
            raise BrowserMemoryValidationError(
                "Forget visits must not include a request body."
            )
        result = forget_browser_visits(db, user_id=user.id)
        db.commit()
        return result
    except (BrowserMemoryValidationError, BrowserVisitConflict, HTTPException, SQLAlchemyError) as exc:
        raise _mutation_error(db, exc) from exc
