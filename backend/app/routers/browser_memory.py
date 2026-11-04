"""Authenticated, read-only account handshake for the opt-in JobGrid extension.

No extension token is issued: the browser's existing HttpOnly session cookie
remains the sole authority for the selected JobGrid account.
"""
from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from ..auth import get_current_user
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
