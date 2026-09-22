from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..availability_schemas import (
    AvailabilityEvidence,
    apply_checker_evidence,
    check_request_retention_cutoff,
)
from ..models import JobAvailability, JobCheckRequest


def _utc_naive(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return current
    return current.astimezone(timezone.utc).replace(tzinfo=None)


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
