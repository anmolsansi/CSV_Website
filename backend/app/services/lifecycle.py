from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ..models import CsvRow, JobLifecycleEvent, JobTrack


FIRST_EVENT_KINDS = frozenset({"first_visited", "first_applied"})
TRANSITION_EVENT_KINDS = frozenset({
    "status_changed",
    "applied_date_corrected",
    "followup_changed",
})
LIFECYCLE_EVENT_KINDS = FIRST_EVENT_KINDS | TRANSITION_EVENT_KINDS

PAYLOAD_ALLOWLISTS: dict[str, frozenset[str]] = {
    "first_visited": frozenset(),
    "first_applied": frozenset(),
    "status_changed": frozenset({"from", "to"}),
    "applied_date_corrected": frozenset({"from", "to"}),
    "followup_changed": frozenset({"from", "to"}),
}


class LifecycleEventError(ValueError):
    """Safe domain error for lifecycle validation and replay conflicts."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _normalize_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise LifecycleEventError(
            "invalid_occurred_at", "occurred_at must be a datetime."
        )
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def validate_event_payload(kind: str, payload: Mapping[str, Any] | None) -> dict[str, Any]:
    if kind not in LIFECYCLE_EVENT_KINDS:
        raise LifecycleEventError("unknown_event_kind", "Unsupported lifecycle event kind.")
    if payload is None:
        return {}
    if not isinstance(payload, Mapping):
        raise LifecycleEventError("invalid_event_payload", "Lifecycle payload must be an object.")

    safe_payload = dict(payload)
    unknown = set(safe_payload) - PAYLOAD_ALLOWLISTS[kind]
    if unknown:
        raise LifecycleEventError(
            "invalid_event_payload",
            "Lifecycle payload contains fields that are not allowed for this event kind.",
        )
    return safe_payload


def first_event_key(user_id: int, job_url: str, kind: str) -> str:
    if kind not in FIRST_EVENT_KINDS:
        raise LifecycleEventError(
            "invalid_first_event_kind",
            "Only first_visited and first_applied use deterministic first-event keys.",
        )
    if not job_url:
        raise LifecycleEventError("invalid_job_url", "job_url is required.")
    material = f"{user_id}\0{job_url}\0{kind}".encode("utf-8")
    return f"first:{hashlib.sha256(material).hexdigest()}"


def transition_event_key(operation_id: UUID | str) -> str:
    try:
        parsed = UUID(str(operation_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise LifecycleEventError(
            "invalid_operation_id", "Transition events require a valid UUID operation ID."
        ) from exc
    return f"operation:{parsed}"


def _validate_owned_links(
    session: Session,
    *,
    user_id: int,
    csv_row_id: int | None,
    job_track_id: int | None,
) -> None:
    if csv_row_id is not None:
        owned_row = (
            session.query(CsvRow.id)
            .filter(CsvRow.id == csv_row_id, CsvRow.user_id == user_id)
            .first()
        )
        if owned_row is None:
            raise LifecycleEventError(
                "inaccessible_csv_row", "CSV row is not available to this account."
            )

    if job_track_id is not None:
        owned_track = (
            session.query(JobTrack.id)
            .filter(JobTrack.id == job_track_id, JobTrack.user_id == user_id)
            .first()
        )
        if owned_track is None:
            raise LifecycleEventError(
                "inaccessible_job_track", "Application is not available to this account."
            )


def _insert_ignore(session: Session, values: dict[str, Any]) -> None:
    table = JobLifecycleEvent.__table__
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        statement = postgresql_insert(table).values(**values).on_conflict_do_nothing(
            index_elements=["user_id", "event_key"]
        )
    elif dialect == "sqlite":
        statement = sqlite_insert(table).values(**values).on_conflict_do_nothing(
            index_elements=["user_id", "event_key"]
        )
    else:
        raise LifecycleEventError(
            "unsupported_database",
            "Lifecycle replay is supported only on PostgreSQL and SQLite.",
        )
    session.execute(statement)


def _transition_replay_matches(
    existing: JobLifecycleEvent,
    *,
    values: dict[str, Any],
) -> bool:
    return all(
        getattr(existing, field) == values[field]
        for field in (
            "job_url",
            "csv_row_id",
            "job_track_id",
            "kind",
            "occurred_at",
            "source",
            "payload",
        )
    )


def write_event(
    session: Session,
    *,
    user_id: int,
    job_url: str,
    kind: str,
    occurred_at: datetime,
    source: str,
    payload: Mapping[str, Any] | None = None,
    csv_row_id: int | None = None,
    job_track_id: int | None = None,
    operation_id: UUID | str | None = None,
) -> JobLifecycleEvent:
    """Write one lifecycle fact without committing the caller-owned transaction."""
    if not isinstance(user_id, int) or user_id <= 0:
        raise LifecycleEventError("invalid_user", "A valid authenticated user is required.")
    if not isinstance(job_url, str) or not job_url:
        raise LifecycleEventError("invalid_job_url", "job_url is required.")
    if not isinstance(source, str) or not source or len(source) > 32:
        raise LifecycleEventError(
            "invalid_source", "source must be a non-empty string of at most 32 characters."
        )

    safe_payload = validate_event_payload(kind, payload)
    occurred_at_utc = _normalize_utc(occurred_at)
    _validate_owned_links(
        session,
        user_id=user_id,
        csv_row_id=csv_row_id,
        job_track_id=job_track_id,
    )

    if kind in FIRST_EVENT_KINDS:
        event_key = first_event_key(user_id, job_url, kind)
    else:
        if operation_id is None:
            raise LifecycleEventError(
                "missing_operation_id",
                "Transition events require a stable UUID operation ID.",
            )
        event_key = transition_event_key(operation_id)

    values = {
        "user_id": user_id,
        "event_key": event_key,
        "job_url": job_url,
        "csv_row_id": csv_row_id,
        "job_track_id": job_track_id,
        "kind": kind,
        "occurred_at": occurred_at_utc,
        "recorded_at": datetime.utcnow(),
        "source": source,
        "payload": safe_payload,
    }
    _insert_ignore(session, values)

    existing = (
        session.query(JobLifecycleEvent)
        .filter(
            JobLifecycleEvent.user_id == user_id,
            JobLifecycleEvent.event_key == event_key,
        )
        .one()
    )
    if kind in TRANSITION_EVENT_KINDS and not _transition_replay_matches(
        existing, values=values
    ):
        raise LifecycleEventError(
            "event_key_conflict",
            "Operation ID was already used for a different lifecycle event.",
        )
    return existing


def _apply_time_window(query, column, start: datetime | None, end: datetime | None):
    if start is not None:
        query = query.filter(column >= _normalize_utc(start))
    if end is not None:
        query = query.filter(column < _normalize_utc(end))
    return query


def count_saved(
    session: Session,
    *,
    user_id: int,
    start: datetime | None = None,
    end: datetime | None = None,
) -> int:
    """Saved means a JobTrack exists; time windows use its creation instant."""
    query = session.query(func.count(JobTrack.id)).filter(JobTrack.user_id == user_id)
    query = _apply_time_window(query, JobTrack.created_at, start, end)
    return int(query.scalar() or 0)


def _count_first_events(
    session: Session,
    *,
    user_id: int,
    kind: str,
    start: datetime | None,
    end: datetime | None,
) -> int:
    query = session.query(func.count(JobLifecycleEvent.id)).filter(
        JobLifecycleEvent.user_id == user_id,
        JobLifecycleEvent.kind == kind,
    )
    query = _apply_time_window(query, JobLifecycleEvent.occurred_at, start, end)
    return int(query.scalar() or 0)


def count_visited(
    session: Session,
    *,
    user_id: int,
    start: datetime | None = None,
    end: datetime | None = None,
) -> int:
    """Visited means one durable first_visited lifecycle fact."""
    return _count_first_events(
        session, user_id=user_id, kind="first_visited", start=start, end=end
    )


def count_applied(
    session: Session,
    *,
    user_id: int,
    start: datetime | None = None,
    end: datetime | None = None,
) -> int:
    """Applied means one durable first_applied lifecycle fact."""
    return _count_first_events(
        session, user_id=user_id, kind="first_applied", start=start, end=end
    )
