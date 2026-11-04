"""Authenticated, read-only account handshake for the opt-in JobGrid extension.

No extension token is issued: the browser's existing HttpOnly session cookie
remains the sole authority for the selected JobGrid account.
"""
import json
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ..auth import get_current_user
from ..browser_memory_schemas import BrowserMemoryValidationError, parse_browser_memory_payload
from ..database import get_db
from ..services.browser_memory import read_browser_memory_facts, utc_z
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
        raise HTTPException(status_code=422, detail=exc.as_detail()) from exc
    except SQLAlchemyError as exc:
        # Never include SQL parameter values or private URL metadata in logs.
        raise HTTPException(
            status_code=503,
            detail={
                "code": "browser_memory_unavailable",
                "message": "Browser memory is temporarily unavailable.",
            },
        ) from exc
    return BrowserMemoryCheckOut(
        protocol_version=1,
        checked_at=utc_z(datetime.now(timezone.utc)),
        account_id=user.id,
        **facts,
    )
