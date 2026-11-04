"""Account-owned, caller-transactional browser visit persistence (EXT-08).

Service-only until the authorized write adapter in EXT-19. Never commits or
fetches a supplied URL and never creates a CSV row or application.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, literal, select
from sqlalchemy.orm import Session

from ..browser_memory_schemas import parse_browser_memory_payload
from ..models import JobVisit, User
from .job_identity import canonicalize_job_url

MAX_BROWSER_VISITS_PER_OWNER = 10_000


class BrowserVisitConflict(ValueError):
    status_code = 409

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def as_detail(self) -> dict:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True)
class BrowserVisitResult:
    account_id: int
    created: bool
    first_visited_at: datetime

    def as_response(self) -> dict:
        first = self.first_visited_at
        if first.tzinfo is None:
            first = first.replace(tzinfo=timezone.utc)
        return {
            "protocol_version": 1,
            "account_id": self.account_id,
            "created": self.created,
            "first_visited_at": first.isoformat().replace("+00:00", "Z"),
        }


def _one_owner_visit(session: Session, *, user_id: int, canonical_url: str, digest: str) -> tuple[JobVisit, bool]:
    """Serialize PG owners and use a single bounded atomic insert on SQLite.

    The unique index handles identical writers. The conditional insert caps
    distinct writer races even on SQLite, where SELECT FOR UPDATE is ignored.
    """
    owner = session.query(User).filter(User.id == user_id).with_for_update().one_or_none()
    if owner is None:
        raise BrowserVisitConflict("browser_memory_unavailable", "Account unavailable.")

    found = session.query(JobVisit).filter_by(
        user_id=user_id, canonical_url_hash=digest
    ).one_or_none()
    if found is not None:
        if found.canonical_url != canonical_url:
            raise BrowserVisitConflict("identity_conflict", "Canonical identity conflict.")
        return found, False

    capacity = (
        select(func.count(JobVisit.id))
        .where(JobVisit.user_id == user_id)
        .scalar_subquery()
    )
    source = select(literal(user_id), literal(canonical_url), literal(digest)).where(
        capacity < MAX_BROWSER_VISITS_PER_OWNER
    )
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        raise RuntimeError("Browser visits require a supported database dialect.")

    statement = (
        insert(JobVisit)
        .from_select(["user_id", "canonical_url", "canonical_url_hash"], source)
        .on_conflict_do_nothing(index_elements=["user_id", "canonical_url_hash"])
    )
    created = session.execute(statement).rowcount == 1
    row = session.query(JobVisit).filter_by(
        user_id=user_id, canonical_url_hash=digest
    ).one_or_none()
    if row is None:
        raise BrowserVisitConflict("visit_limit_reached", "Visit memory limit reached.")
    if row.canonical_url != canonical_url:
        raise BrowserVisitConflict("identity_conflict", "Canonical identity conflict.")
    return row, created


def save_browser_visit(session: Session, *, user_id: int, url: str) -> BrowserVisitResult:
    """Insert/replay one owner visit. Caller commits or rolls back once.

    No session or lifecycle event is written. A later route authenticates the
    cookie owner, checks exact Origin and expected account before invoking this.
    """
    request = parse_browser_memory_payload("visit", {"url": url})
    identity = canonicalize_job_url(request.url)
    visit, created = _one_owner_visit(
        session,
        user_id=user_id,
        canonical_url=identity.canonical_url,
        digest=identity.canonical_url_hash,
    )
    return BrowserVisitResult(
        account_id=user_id,
        created=created,
        first_visited_at=visit.first_visited_at,
    )
