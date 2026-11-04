"""Account-owned, caller-transactional browser visit persistence (EXT-08).

Service-only until the authorized write adapter in EXT-19. Never commits or
fetches a supplied URL and never creates a CSV row or application.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from uuid import uuid4

from sqlalchemy import and_, or_

from sqlalchemy import func, literal, select
from sqlalchemy.orm import Session

from ..browser_memory_schemas import (
    parse_browser_memory_payload, validate_apply_idempotency_key,
)
from ..models import BrowserApplyReceipt, CsvRow, JobTrack, JobVisit, User
from .job_identity import (
    apply_persisted_job_identity,
    canonicalize_job_url,
    find_browser_applied_matches,
)
from .lifecycle import apply_job_track_changes

MAX_BROWSER_VISITS_PER_OWNER = 10_000
MAX_BROWSER_APPLY_RECEIPTS_PER_OWNER = 10_000
BROWSER_APPLY_RECEIPT_RETENTION_DAYS = 30


def _apply_payload_hash(request) -> str:
    """Stable digest of the validated apply intent, including confirmation.

    Trim only free-text fields that the service itself persists trimmed.
    Keep the original URL, including its query, so a changed request key
    cannot silently target another URL or hide a changed payload.
    """
    payload = {
        "url": request.url,
        "company": request.company.strip(),
        "title": request.title.strip(),
        "confirmed": request.confirmed,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()



class BrowserVisitConflict(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.status_code = 503 if code == "browser_memory_unavailable" else 409
        self.code = code
        self.message = message

    def as_detail(self) -> dict:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True)
class BrowserVisitResult:
    account_id: int
    created: bool
    first_visited_at: datetime
    matching_rows_marked: int = 0

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


def _mark_matching_existing_rows(
    session: Session,
    *,
    user_id: int,
    original_url: str,
    canonical_url: str,
    digest: str,
) -> int:
    """Only existing owned rows get their first clicked timestamp.

    Existing row-click routes retain their own lifecycle event flow. Browser
    visits must not add a synthetic row-open event or inflate session counts.
    """
    rows = (
        session.query(CsvRow)
        .filter(CsvRow.user_id == user_id)
        .filter(or_(
            CsvRow.url == original_url,
            and_(
                CsvRow.canonical_url_hash == digest,
                CsvRow.canonical_url == canonical_url,
            ),
        ))
        .order_by(CsvRow.id.asc())
        .all()
    )
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    marked = 0
    for row in rows:
        if row.clicked:
            continue
        row.clicked = True
        row.clicked_at = now
        marked += 1
    session.flush()
    return marked


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
    # The caller owns the transaction. Either both the durable visit and any
    # matching pre-existing row flags commit, or neither commits.
    marked = _mark_matching_existing_rows(
        session,
        user_id=user_id,
        original_url=request.url,
        canonical_url=identity.canonical_url,
        digest=identity.canonical_url_hash,
    )
    return BrowserVisitResult(
        account_id=user_id,
        created=created,
        first_visited_at=visit.first_visited_at,
        matching_rows_marked=marked,
    )



def forget_browser_visits(session: Session, *, user_id: int) -> dict:
    """Forget only this account's external visit memory.

    Caller supplies the authenticated cookie owner's ID and owns the transaction.
    Existing CSV click facts, imported URL history and applications are not
    inferred from visits, so they are deliberately left untouched.
    """
    owner = session.query(User).filter(User.id == user_id).with_for_update().one_or_none()
    if owner is None:
        raise BrowserVisitConflict("browser_memory_unavailable", "Account unavailable.")

    deleted = (
        session.query(JobVisit)
        .filter(JobVisit.user_id == user_id)
        .delete(synchronize_session=False)
    )
    return {"protocol_version": 1, "account_id": user_id, "deleted": deleted}



def utc_z(value: datetime | None) -> str | None:
    """Encode stored naive-UTC and aware instants as RFC3339 UTC-Z."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def read_browser_memory_facts(
    session: Session,
    *,
    user_id: int,
    url: str,
    company: str | None = None,
    title: str | None = None,
) -> dict:
    """Compose independent, owner-only visit and application facts (EXT-13).

    This query does not infer an application from a visited, imported or saved
    job. Only JobTrack.applied_at proves an application. A URL may be visited
    and applied independently, and no ATS hostname is treated as an employer.
    """
    request = parse_browser_memory_payload(
        "check", {"url": url, "company": company, "title": title}
    )
    identity = canonicalize_job_url(request.url)
    same_identity = or_(
        CsvRow.url == request.url,
        and_(
            CsvRow.canonical_url_hash == identity.canonical_url_hash,
            CsvRow.canonical_url == identity.canonical_url,
        ),
    )
    visit = (
        session.query(JobVisit)
        .filter(
            JobVisit.user_id == user_id,
            JobVisit.canonical_url_hash == identity.canonical_url_hash,
            JobVisit.canonical_url == identity.canonical_url,
        )
        .one_or_none()
    )
    clicked = (
        session.query(CsvRow.clicked_at)
        .filter(
            CsvRow.user_id == user_id,
            CsvRow.clicked.is_(True),
            same_identity,
        )
        .all()
    )
    opened = (
        session.query(JobTrack.opened_at)
        .filter(
            JobTrack.user_id == user_id,
            JobTrack.opened_at.isnot(None),
            or_(
                JobTrack.url == request.url,
                and_(
                    JobTrack.canonical_url_hash == identity.canonical_url_hash,
                    JobTrack.canonical_url == identity.canonical_url,
                ),
            ),
        )
        .all()
    )
    known_times = (
        ([visit.first_visited_at] if visit is not None else [])
        + [row[0] for row in clicked if row[0] is not None]
        + [row[0] for row in opened if row[0] is not None]
    )
    # SQLite may return naive UTC while PostgreSQL returns aware instants.
    first_visit = min(
        (dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else
         dt.astimezone(timezone.utc) for dt in known_times),
        default=None,
    )
    applied = find_browser_applied_matches(
        session,
        user_id=user_id,
        url=request.url,
        company=request.company if request.company and request.company.strip() else None,
        title=request.title,
    )
    return {
        "visit": {
            "visited": visit is not None or bool(clicked) or bool(opened),
            "first_visited_at": utc_z(first_visit),
        },
        "matches": [
            {**match, "applied_at": utc_z(match["applied_at"])}
            for match in applied["matches"]
        ],
        "company_history_count": applied["company_history_count"],
        # Untrusted page metadata is either explicitly present or unknown.
        "company_known": bool(request.company and request.company.strip()),
        "lookup_complete": applied["lookup_complete"],
    }



@dataclass(frozen=True)
class BrowserApplicationResult:
    account_id: int
    application_id: int
    created: bool
    already_applied: bool
    applied_at: datetime

    def as_response(self) -> dict:
        return {
            "protocol_version": 1,
            "account_id": self.account_id,
            "application_id": self.application_id,
            "created": self.created,
            "already_applied": self.already_applied,
            "applied_at": utc_z(self.applied_at),
        }


def record_browser_application(
    session: Session,
    *,
    user_id: int,
    url: str,
    company: str,
    title: str,
    confirmed: bool,
    operation_id: str | None = None,
    now: datetime | None = None,
) -> BrowserApplicationResult:
    """Explicitly record a job application without capture or a synthetic open.

    EXT-16 is an internal service, not an HTTP route or an idempotency receipt.
    The authenticated caller owns commit/rollback; EXT-18 adds durable receipts.
    Exact/canonical already-applied history is returned without mutation.
    """
    request = parse_browser_memory_payload(
        "apply", {
            "url": url, "company": company, "title": title,
            "confirmed": confirmed,
        },
    )
    identity = canonicalize_job_url(request.url)
    owner = (
        session.query(User).filter(User.id == user_id).with_for_update()
        .one_or_none()
    )
    if owner is None:
        raise BrowserVisitConflict(
            "browser_memory_unavailable", "Account unavailable."
        )

    exact = (
        session.query(JobTrack)
        .filter(JobTrack.user_id == user_id, JobTrack.url == request.url)
        .with_for_update()
        .one_or_none()
    )
    if exact is not None and exact.applied_at is not None:
        return BrowserApplicationResult(
            account_id=user_id, application_id=exact.id, created=False,
            already_applied=True, applied_at=exact.applied_at,
        )

    # A tracking-only URL variant must not create a second application.
    # Company/title similarity alone is never sufficient to reuse a track.
    prior = (
        session.query(JobTrack)
        .filter(
            JobTrack.user_id == user_id,
            JobTrack.applied_at.isnot(None),
            JobTrack.canonical_url_hash == identity.canonical_url_hash,
            JobTrack.canonical_url == identity.canonical_url,
        )
        .order_by(JobTrack.applied_at.desc(), JobTrack.id.desc())
        .first()
    )
    if prior is not None:
        return BrowserApplicationResult(
            account_id=user_id, application_id=prior.id, created=False,
            already_applied=True, applied_at=prior.applied_at,
        )

    created = exact is None
    if created:
        item = JobTrack(
            user_id=user_id,
            url=request.url,
            company=request.company.strip(),
            title=request.title.strip(),
            status="applied",
            open_count=0,
            opened_at=None,
            last_opened_at=None,
            applied_at=None,
        )
        apply_persisted_job_identity(item)
        session.add(item)
    else:
        item = exact
        # Explicit confirmation must not replace existing curated metadata.
        if not item.company or not item.company.strip():
            item.company = request.company.strip()
        if not item.title or not item.title.strip():
            item.title = request.title.strip()
        apply_persisted_job_identity(item)

    stamp = now or datetime.now(timezone.utc)
    if stamp.tzinfo is not None:
        stamp = stamp.astimezone(timezone.utc).replace(tzinfo=None)

    change = {"mark_applied": True}
    if not created and item.status not in {"opened", "saved", "applied"}:
        # An unusual legacy advanced status with a missing applied timestamp
        # still needs first-applied evidence, but must not be reset.
        change = {"applied_at": stamp, "infer_applied_at_from_status": False}

    apply_job_track_changes(
        session,
        user_id=user_id,
        item=item,
        source="browser_memory",
        operation_id=operation_id or str(uuid4()),
        now=stamp,
        **change,
    )
    session.flush()
    return BrowserApplicationResult(
        account_id=user_id, application_id=item.id, created=created,
        already_applied=False, applied_at=item.applied_at,
    )
