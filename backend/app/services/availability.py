from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from ..availability_schemas import (
    AvailabilityEvidence,
    apply_checker_evidence,
    check_request_retention_cutoff,
    parse_deadline_input,
)
from ..config import settings
from ..database import SessionLocal
from ..models import CsvRow, JobAvailability, JobCheckRequest, JobTrack, User
from .safe_job_fetch import SafeFetchResult, SafeJobFetcher


JOB_CHECK_PER_URL_WINDOW = timedelta(hours=1)
JOB_CHECK_DAILY_WINDOW = timedelta(days=1)
JOB_CHECK_DAILY_LIMIT = 20
MAX_JOB_CHECK_CLAIM = 10
_UNSET = object()


class AvailabilityServiceError(ValueError):
    """Safe owner-scoped availability failure suitable for API mapping."""

    def __init__(
        self,
        code: str,
        status_code: int,
        message: str,
        *,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.retry_after = retry_after

    def as_detail(self) -> dict[str, str]:
        return {"code": self.code, "message": str(self)}


def _utc_naive(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return current
    return current.astimezone(timezone.utc).replace(tzinfo=None)


def _utc_aware(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _utc_text(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _utc_aware(value).isoformat().replace("+00:00", "Z")


def owned_row_job_url(db: Session, *, user_id: int, row_id: int) -> str:
    row = (
        db.query(CsvRow)
        .filter(CsvRow.id == row_id, CsvRow.user_id == user_id)
        .first()
    )
    if row is None:
        raise AvailabilityServiceError(
            "job_not_found",
            404,
            "Job was not found.",
        )
    return row.url


def owned_track_job_url(db: Session, *, user_id: int, track_id: int) -> str:
    track = (
        db.query(JobTrack)
        .filter(JobTrack.id == track_id, JobTrack.user_id == user_id)
        .first()
    )
    if track is None:
        raise AvailabilityServiceError(
            "application_not_found",
            404,
            "Application was not found.",
        )
    return track.url


def get_job_availability(
    db: Session,
    *,
    user_id: int,
    job_url: str,
    for_update: bool = False,
) -> JobAvailability | None:
    query = db.query(JobAvailability).filter(
        JobAvailability.user_id == user_id,
        JobAvailability.job_url == job_url,
    )
    if for_update:
        query = query.with_for_update()
    return query.first()


def _latest_active_check(
    db: Session,
    *,
    user_id: int,
    availability_id: int | None,
) -> JobCheckRequest | None:
    if availability_id is None:
        return None
    return (
        db.query(JobCheckRequest)
        .filter(
            JobCheckRequest.user_id == user_id,
            JobCheckRequest.availability_id == availability_id,
            JobCheckRequest.status.in_(("pending", "running")),
        )
        .order_by(JobCheckRequest.requested_at.desc(), JobCheckRequest.id.desc())
        .first()
    )


def serialize_job_availability(
    db: Session,
    *,
    user: User,
    job_url: str,
    availability: JobAvailability | None,
    checks_enabled: bool | None = None,
) -> dict[str, Any]:
    deadline_at = availability.deadline_at if availability is not None else None
    local_deadline_date = None
    if deadline_at is not None:
        local_deadline_date = (
            _utc_aware(deadline_at)
            .astimezone(ZoneInfo(user.timezone))
            .date()
            .isoformat()
        )
    active_check = _latest_active_check(
        db,
        user_id=user.id,
        availability_id=availability.id if availability is not None else None,
    )
    return {
        "id": availability.id if availability is not None else None,
        "job_url": job_url,
        "deadline_at": _utc_text(deadline_at),
        "deadline_local_date": local_deadline_date,
        "deadline_source": availability.deadline_source if availability is not None else None,
        "state": availability.state if availability is not None else "unknown",
        "last_checked_at": (
            _utc_text(availability.last_checked_at)
            if availability is not None
            else None
        ),
        "check_reason": availability.check_reason if availability is not None else None,
        "confirmed_closed_at": (
            _utc_text(availability.confirmed_closed_at)
            if availability is not None
            else None
        ),
        "version": int(availability.version) if availability is not None else 1,
        "timezone": user.timezone,
        "deadline_interpretation": (
            f"Date-only deadlines use 23:59:59.999999 {user.timezone}."
        ),
        "checks_enabled": (
            bool(settings.JOB_URL_CHECKS_ENABLED)
            if checks_enabled is None
            else bool(checks_enabled)
        ),
        "check_status": active_check.status if active_check is not None else None,
        "check_request_id": active_check.id if active_check is not None else None,
    }


def update_manual_availability(
    db: Session,
    *,
    user_id: int,
    job_url: str,
    timezone_name: str,
    version: int,
    deadline_input: str | None | object = _UNSET,
    state: str | None = None,
    confirm_state_change: bool = False,
    now: datetime | None = None,
) -> JobAvailability:
    """Apply one optimistic manual mutation. Checker-only states are never accepted here."""

    existing = get_job_availability(
        db,
        user_id=user_id,
        job_url=job_url,
        for_update=True,
    )
    if existing is None:
        if version != 1:
            raise AvailabilityServiceError(
                "stale_version",
                409,
                "Availability changed. Reload and retry.",
            )
        existing = JobAvailability(
            user_id=user_id,
            job_url=job_url,
            state="unknown",
            version=1,
        )
        db.add(existing)
        db.flush()
    elif int(existing.version) != int(version):
        raise AvailabilityServiceError(
            "stale_version",
            409,
            "Availability changed. Reload and retry.",
        )

    changed = False
    if deadline_input is not _UNSET:
        if deadline_input is None:
            if existing.deadline_at is not None or existing.deadline_source is not None:
                existing.deadline_at = None
                existing.deadline_source = None
                changed = True
        else:
            conversion = parse_deadline_input(str(deadline_input), timezone_name)
            if (
                existing.deadline_at != conversion.deadline_at
                or existing.deadline_source != "user"
            ):
                existing.deadline_at = conversion.deadline_at
                existing.deadline_source = "user"
                changed = True

    reference = _utc_naive(now)
    if state is not None:
        if state not in {"closed", "unknown"}:
            raise AvailabilityServiceError(
                "invalid_manual_state",
                422,
                "Manual state must be closed or unknown.",
            )
        if not confirm_state_change:
            raise AvailabilityServiceError(
                "confirmation_required",
                422,
                "Explicit confirmation is required for close or reopen.",
            )
        if state == "closed":
            if existing.state != "closed":
                existing.state = "closed"
                existing.confirmed_closed_at = reference
                existing.check_reason = "user_confirmed_closed"
                changed = True
        else:
            if existing.state == "closed":
                existing.state = "unknown"
                existing.confirmed_closed_at = None
                existing.check_reason = "user_reopened"
                changed = True
            elif existing.state != "unknown":
                existing.state = "unknown"
                existing.confirmed_closed_at = None
                existing.check_reason = "user_reset_unknown"
                changed = True

    if not changed:
        return existing

    existing.version = int(existing.version) + 1
    db.flush()
    return existing


def apply_checker_result(
    availability: JobAvailability,
    *,
    checked_at: datetime,
    http_status: int | None = None,
    failure_reason: str | None = None,
) -> AvailabilityEvidence:
    """Persist one conservative checker observation without reopening user closure."""
    evidence = apply_checker_evidence(
        availability.state,
        http_status=http_status,
        failure_reason=failure_reason,
    )
    availability.last_checked_at = _utc_naive(checked_at)
    availability.check_reason = evidence.check_reason
    if availability.state != "closed":
        availability.state = evidence.state
        availability.confirmed_closed_at = None
        availability.version += 1
    return evidence


def confirm_user_closed(
    availability: JobAvailability,
    *,
    confirmed_at: datetime,
) -> None:
    availability.state = "closed"
    availability.confirmed_closed_at = _utc_naive(confirmed_at)
    availability.check_reason = "user_confirmed_closed"
    availability.version += 1


def prune_job_check_requests(
    db: Session,
    *,
    reference: datetime | None = None,
) -> int:
    """Delete only transient check metadata older than the frozen seven-day window."""
    cutoff = check_request_retention_cutoff(reference)
    return (
        db.query(JobCheckRequest)
        .filter(JobCheckRequest.requested_at < cutoff)
        .delete(synchronize_session=False)
    )


def _retry_after_seconds(requested_at: datetime, window: timedelta, now: datetime) -> int:
    remaining = requested_at + window - now
    return max(1, int(math.ceil(remaining.total_seconds())))


def enqueue_job_check(
    db: Session,
    *,
    user_id: int,
    availability: JobAvailability,
    requested_at: datetime | None = None,
) -> JobCheckRequest:
    """Serialize durable rate checks with an account row lock before insert."""

    now = _utc_naive(requested_at)
    user = (
        db.query(User)
        .filter(User.id == user_id)
        .with_for_update()
        .first()
    )
    if user is None:
        raise AvailabilityServiceError("user_not_found", 404, "Account was not found.")
    if availability.user_id != user_id:
        raise AvailabilityServiceError("job_not_found", 404, "Job was not found.")

    recent_for_url = (
        db.query(JobCheckRequest)
        .filter(
            JobCheckRequest.user_id == user_id,
            JobCheckRequest.availability_id == availability.id,
            JobCheckRequest.requested_at >= now - JOB_CHECK_PER_URL_WINDOW,
        )
        .order_by(JobCheckRequest.requested_at.asc())
        .first()
    )
    if recent_for_url is not None:
        raise AvailabilityServiceError(
            "job_check_url_rate_limited",
            429,
            "This job link can be checked at most once per hour.",
            retry_after=_retry_after_seconds(
                recent_for_url.requested_at,
                JOB_CHECK_PER_URL_WINDOW,
                now,
            ),
        )

    daily_rows = (
        db.query(JobCheckRequest)
        .filter(
            JobCheckRequest.user_id == user_id,
            JobCheckRequest.requested_at >= now - JOB_CHECK_DAILY_WINDOW,
        )
        .order_by(JobCheckRequest.requested_at.asc())
        .all()
    )
    if len(daily_rows) >= JOB_CHECK_DAILY_LIMIT:
        raise AvailabilityServiceError(
            "job_check_daily_rate_limited",
            429,
            "This account can check at most 20 job links per day.",
            retry_after=_retry_after_seconds(
                daily_rows[0].requested_at,
                JOB_CHECK_DAILY_WINDOW,
                now,
            ),
        )

    request = JobCheckRequest(
        id=str(uuid4()),
        user_id=user_id,
        availability_id=availability.id,
        requested_at=now,
        status="pending",
    )
    db.add(request)
    db.flush()
    return request


def recover_expired_job_check_claims(
    db: Session,
    *,
    now: datetime | None = None,
) -> int:
    reference = _utc_naive(now)
    rows = (
        db.query(JobCheckRequest)
        .filter(
            JobCheckRequest.status == "running",
            JobCheckRequest.lease_until.isnot(None),
            JobCheckRequest.lease_until <= reference,
        )
        .with_for_update(skip_locked=True)
        .all()
    )
    for row in rows:
        row.status = "failed"
        row.completed_at = reference
        row.lease_until = None
        row.error_code = "lease_expired"
    db.flush()
    return len(rows)


def claim_job_check_requests(
    db: Session,
    *,
    now: datetime | None = None,
    limit: int = MAX_JOB_CHECK_CLAIM,
    lease_seconds: int | None = None,
) -> list[JobCheckRequest]:
    if limit < 1 or limit > MAX_JOB_CHECK_CLAIM:
        raise ValueError("Job-check claim limit must be between 1 and 10.")

    reference = _utc_naive(now)
    recover_expired_job_check_claims(db, now=reference)
    rows = (
        db.query(JobCheckRequest)
        .filter(JobCheckRequest.status == "pending")
        .order_by(JobCheckRequest.requested_at.asc(), JobCheckRequest.id.asc())
        .with_for_update(skip_locked=True)
        .limit(limit)
        .all()
    )
    lease = max(
        30,
        min(
            600,
            int(
                lease_seconds
                if lease_seconds is not None
                else settings.JOB_URL_CHECK_LEASE_SECONDS
            ),
        ),
    )
    for row in rows:
        row.status = "running"
        row.lease_until = reference + timedelta(seconds=lease)
        row.error_code = None
    db.flush()
    return rows


def _claim_specific_job_check(
    db: Session,
    request_id: str,
    *,
    now: datetime | None = None,
) -> JobCheckRequest | None:
    reference = _utc_naive(now)
    recover_expired_job_check_claims(db, now=reference)
    row = (
        db.query(JobCheckRequest)
        .filter(
            JobCheckRequest.id == request_id,
            JobCheckRequest.status == "pending",
        )
        .with_for_update()
        .first()
    )
    if row is None:
        return None
    row.status = "running"
    row.lease_until = reference + timedelta(
        seconds=settings.JOB_URL_CHECK_LEASE_SECONDS
    )
    row.error_code = None
    db.flush()
    return row


def finish_job_check_request(
    db: Session,
    *,
    request_id: str,
    result: SafeFetchResult,
    checked_at: datetime | None = None,
) -> JobCheckRequest | None:
    reference = _utc_naive(checked_at)
    request = (
        db.query(JobCheckRequest)
        .filter(JobCheckRequest.id == request_id)
        .with_for_update()
        .first()
    )
    if request is None or request.status != "running":
        return request

    availability = (
        db.query(JobAvailability)
        .filter(
            JobAvailability.id == request.availability_id,
            JobAvailability.user_id == request.user_id,
        )
        .with_for_update()
        .first()
    )
    if availability is None:
        request.status = "failed"
        request.completed_at = reference
        request.lease_until = None
        request.error_code = "availability_missing"
        db.flush()
        return request

    apply_checker_result(
        availability,
        checked_at=reference,
        http_status=result.http_status,
        failure_reason=result.failure_reason,
    )
    request.status = "done" if result.failure_reason is None else "failed"
    request.completed_at = reference
    request.lease_until = None
    request.error_code = result.failure_reason
    db.flush()
    return request


def process_job_check_request(
    request_id: str,
    *,
    fetcher: SafeJobFetcher | None = None,
) -> None:
    """Process one user-invoked durable request without an automatic scheduler."""

    fetcher = fetcher or SafeJobFetcher()
    db = SessionLocal()
    job_url: str | None = None
    try:
        claimed = _claim_specific_job_check(db, request_id)
        if claimed is None:
            db.rollback()
            return
        availability = (
            db.query(JobAvailability)
            .filter(
                JobAvailability.id == claimed.availability_id,
                JobAvailability.user_id == claimed.user_id,
            )
            .first()
        )
        if availability is None:
            claimed.status = "failed"
            claimed.completed_at = _utc_naive()
            claimed.lease_until = None
            claimed.error_code = "availability_missing"
            db.commit()
            return
        job_url = availability.job_url
        db.commit()

        result = fetcher.check(job_url)
        finish_job_check_request(
            db,
            request_id=request_id,
            result=result,
        )
        db.commit()
    except Exception:
        db.rollback()
        try:
            claimed = (
                db.query(JobCheckRequest)
                .filter(JobCheckRequest.id == request_id)
                .with_for_update()
                .first()
            )
            if claimed is not None and claimed.status in {"pending", "running"}:
                claimed.status = "failed"
                claimed.completed_at = _utc_naive()
                claimed.lease_until = None
                claimed.error_code = "internal_error"
                availability = (
                    db.query(JobAvailability)
                    .filter(
                        JobAvailability.id == claimed.availability_id,
                        JobAvailability.user_id == claimed.user_id,
                    )
                    .first()
                )
                if availability is not None:
                    apply_checker_result(
                        availability,
                        checked_at=_utc_naive(),
                        failure_reason="internal_error",
                    )
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()
