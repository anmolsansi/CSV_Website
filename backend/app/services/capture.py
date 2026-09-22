from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..capture_schemas import (
    CaptureContractError,
    CaptureRequestIn,
    capture_payload_hash,
    normalize_request_key,
)
from ..models import (
    CaptureRequest,
    CsvRow,
    JobTrack,
    RequestWindowCounter,
    User,
)
from .job_identity import (
    JobIdentityError,
    apply_persisted_job_identity,
    canonicalize_job_url,
    classify_identity_match,
)
from .validation import validate_text_limits


CAPTURE_SCOPE = "job_capture"
CAPTURE_RATE_LIMIT = 60
CAPTURE_RECEIPT_RETENTION_DAYS = 30
CAPTURE_COUNTER_RETENTION_HOURS = 48
CAPTURE_MATCH_LIMIT = 10
CAPTURE_MATCH_SCAN_LIMIT = 100


class CaptureServiceError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        field: str | None = None,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.field = field
        self.retry_after = retry_after


@dataclass(frozen=True)
class CaptureResult:
    row: CsvRow
    created: bool
    replayed: bool
    matches: list[dict[str, Any]]
    company_history_count: int


def _hour_start(now: datetime) -> datetime:
    return now.replace(minute=0, second=0, microsecond=0)


def increment_capture_window(
    db: Session,
    *,
    user_id: int,
    now: datetime | None = None,
) -> None:
    """Count one authenticated attempt in its own committed DB transaction."""
    now = now or datetime.utcnow()
    window_start = _hour_start(now)
    retry_after = max(
        1,
        int(((window_start + timedelta(hours=1)) - now).total_seconds()),
    )
    bind = db.get_bind()
    engine = getattr(bind, "engine", bind)
    limiter = Session(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        with limiter.begin():
            limiter.query(User).filter(User.id == user_id).with_for_update().one()
            counter = (
                limiter.query(RequestWindowCounter)
                .filter_by(
                    user_id=user_id,
                    scope=CAPTURE_SCOPE,
                    window_start=window_start,
                )
                .first()
            )
            if counter is None:
                counter = RequestWindowCounter(
                    user_id=user_id,
                    scope=CAPTURE_SCOPE,
                    window_start=window_start,
                    count=1,
                )
                limiter.add(counter)
                limiter.flush()
            else:
                counter.count += 1
            current_count = counter.count
            limiter.query(RequestWindowCounter).filter(
                RequestWindowCounter.window_start
                < now - timedelta(hours=CAPTURE_COUNTER_RETENTION_HOURS)
            ).delete(synchronize_session=False)
        if current_count > CAPTURE_RATE_LIMIT:
            raise CaptureServiceError(
                "capture_rate_limited",
                "Capture limit exceeded for the current UTC hour.",
                status_code=429,
                retry_after=retry_after,
            )
    finally:
        limiter.close()


def _capture_matches(
    session: Session,
    *,
    user_id: int,
    payload: CaptureRequestIn,
) -> tuple[list[dict[str, Any]], int]:
    try:
        identity = canonicalize_job_url(payload.job_url)
    except JobIdentityError as exc:
        raise CaptureServiceError(
            "invalid_job_url",
            str(exc),
            status_code=422,
            field="job_url",
        ) from exc

    company_key = payload.company.strip().lower()
    candidates = (
        session.query(JobTrack)
        .filter(
            JobTrack.user_id == user_id,
            or_(
                JobTrack.url == payload.job_url,
                JobTrack.canonical_url_hash == identity.canonical_url_hash,
                func.lower(func.trim(JobTrack.company)) == company_key,
            ),
        )
        .order_by(JobTrack.applied_at.desc(), JobTrack.id.desc())
        .limit(CAPTURE_MATCH_SCAN_LIMIT)
        .all()
    )
    rank = {"exact": 0, "canonical": 1, "possible": 2}
    matches: list[dict[str, Any]] = []
    for item in candidates:
        try:
            match = classify_identity_match(
                payload.job_url,
                item.url,
                candidate_company=payload.company,
                existing_company=item.company,
                candidate_title=payload.title,
                existing_title=item.title,
            )
        except JobIdentityError:
            continue
        if match.confidence is None:
            continue
        matches.append({
            "track_id": item.id,
            "row_id": item.csv_row_id,
            "confidence": match.confidence,
            "reason": match.reason,
            "company": item.company,
            "title": item.title,
            "status": item.status,
            "applied_at": (
                item.applied_at.isoformat() + ("Z" if item.applied_at.tzinfo is None else "")
                if item.applied_at
                else None
            ),
        })

    matches.sort(
        key=lambda item: (
            rank[item["confidence"]],
            -(next(
                (
                    candidate.applied_at.timestamp()
                    for candidate in candidates
                    if candidate.id == item["track_id"] and candidate.applied_at
                ),
                0,
            )),
            -(item["track_id"] or 0),
        )
    )
    history_count = (
        session.query(func.count(JobTrack.id))
        .filter(
            JobTrack.user_id == user_id,
            func.lower(func.trim(JobTrack.company)) == company_key,
        )
        .scalar()
        or 0
    )
    return matches[:CAPTURE_MATCH_LIMIT], int(history_count)


def capture_job(
    session: Session,
    *,
    user_id: int,
    payload: CaptureRequestIn,
    request_key: str,
    now: datetime | None = None,
) -> CaptureResult:
    """Create/replay one capture. Caller owns commit/rollback."""
    now = now or datetime.utcnow()
    try:
        normalized_key = normalize_request_key(request_key)
    except CaptureContractError as exc:
        raise CaptureServiceError(
            exc.code,
            str(exc),
            status_code=422,
            field=exc.field,
        ) from exc
    digest = capture_payload_hash(payload)

    # Serialize duplicate lookup and row creation per account.
    session.query(User).filter(User.id == user_id).with_for_update().one()

    cutoff = now - timedelta(days=CAPTURE_RECEIPT_RETENTION_DAYS)
    session.query(CaptureRequest).filter(
        CaptureRequest.user_id == user_id,
        CaptureRequest.created_at < cutoff,
    ).delete(synchronize_session=False)

    receipt = (
        session.query(CaptureRequest)
        .filter_by(user_id=user_id, request_key=normalized_key)
        .first()
    )
    if receipt is not None:
        if receipt.payload_hash != digest:
            raise CaptureServiceError(
                "idempotency_conflict",
                "Idempotency-Key was already used for a different capture payload.",
                status_code=409,
                field="Idempotency-Key",
            )
        if receipt.row_id is None:
            raise CaptureServiceError(
                "capture_replay_unavailable",
                "The original captured row no longer exists.",
                status_code=409,
            )
        row = (
            session.query(CsvRow)
            .filter(CsvRow.id == receipt.row_id, CsvRow.user_id == user_id)
            .first()
        )
        if row is None:
            raise CaptureServiceError(
                "capture_replay_unavailable",
                "The original captured row no longer exists.",
                status_code=409,
            )
        matches, history_count = _capture_matches(
            session, user_id=user_id, payload=payload
        )
        return CaptureResult(
            row=row,
            created=False,
            replayed=True,
            matches=matches,
            company_history_count=history_count,
        )

    matches, history_count = _capture_matches(
        session, user_id=user_id, payload=payload
    )
    existing = (
        session.query(CsvRow)
        .filter(CsvRow.user_id == user_id, CsvRow.url == payload.job_url)
        .first()
    )
    if existing is not None:
        session.add(CaptureRequest(
            user_id=user_id,
            request_key=normalized_key,
            payload_hash=digest,
            row_id=existing.id,
            created_at=now,
        ))
        session.flush()
        return CaptureResult(
            row=existing,
            created=False,
            replayed=False,
            matches=matches,
            company_history_count=history_count,
        )

    row = CsvRow(
        user_id=user_id,
        upload_batch_id=str(uuid4()),
        url=payload.job_url,
        title=payload.title,
        company_guess=payload.company,
        capture_source=payload.source,
        captured_at=now,
        capture_notes=payload.notes,
        clicked=False,
        clicked_at=None,
    )
    apply_persisted_job_identity(row)
    session.add(row)
    session.flush()
    session.add(CaptureRequest(
        user_id=user_id,
        request_key=normalized_key,
        payload_hash=digest,
        row_id=row.id,
        created_at=now,
    ))
    session.flush()
    return CaptureResult(
        row=row,
        created=True,
        replayed=False,
        matches=matches,
        company_history_count=history_count,
    )


def transfer_capture_notes(
    existing_notes: str | None,
    capture_notes: str | None,
    *,
    append: bool,
) -> str | None:
    """Transfer draft capture notes without silently replacing application notes."""
    if capture_notes is None or not capture_notes.strip():
        return existing_notes
    if existing_notes is None or not existing_notes.strip():
        candidate = capture_notes
    elif append:
        candidate = f"{existing_notes}\n\n{capture_notes}"
    else:
        return existing_notes
    return validate_text_limits({"notes": candidate})["notes"]
