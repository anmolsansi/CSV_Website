from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, aliased

from ..evidence_schemas import (
    EvidenceContractError,
    validate_correction_reason,
)
from ..models import CsvRow, JobLifecycleEvent, JobTrack


FIRST_EVENT_KINDS = frozenset({"first_visited", "first_applied"})
TRANSITION_EVENT_KINDS = frozenset({
    "status_changed",
    "applied_date_corrected",
    "followup_changed",
    "evidence_added",
    "evidence_edited",
    "evidence_deleted",
})
EVIDENCE_EVENT_KINDS = frozenset({
    "evidence_added",
    "evidence_edited",
    "evidence_deleted",
})
LIFECYCLE_EVENT_KINDS = FIRST_EVENT_KINDS | TRANSITION_EVENT_KINDS

PAYLOAD_ALLOWLISTS: dict[str, frozenset[str]] = {
    "first_visited": frozenset(),
    "first_applied": frozenset(),
    "status_changed": frozenset({"from", "to", "correction_of", "reason"}),
    "applied_date_corrected": frozenset({"from", "to", "reason"}),
    "followup_changed": frozenset({"from", "to"}),
    "evidence_added": frozenset({"evidence_id", "evidence_kind"}),
    "evidence_edited": frozenset({"evidence_id", "evidence_kind", "version"}),
    "evidence_deleted": frozenset({"evidence_id", "evidence_kind", "version"}),
}


class LifecycleEventError(ValueError):
    """Safe domain error for lifecycle validation and replay conflicts."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


_UNSET = object()


def coerce_operation_id(value: UUID | str | None = None) -> UUID:
    """Return a validated request operation ID, generating one when omitted."""
    if value is None:
        return uuid4()
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise LifecycleEventError(
            "invalid_operation_id", "Operation ID must be a valid UUID."
        ) from exc


def child_operation_id(operation_id: UUID | str, *parts: object) -> UUID:
    """Derive a stable per-entity/per-transition ID from one request operation ID."""
    root = coerce_operation_id(operation_id)
    suffix = "|".join(str(part) for part in parts)
    return uuid5(NAMESPACE_URL, f"jobgrid:{root}|{suffix}")


def _payload_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _normalize_utc(value).isoformat()


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

    if kind in EVIDENCE_EVENT_KINDS:
        evidence_id = safe_payload.get("evidence_id")
        evidence_kind = safe_payload.get("evidence_kind")
        if not isinstance(evidence_id, int) or isinstance(evidence_id, bool) or evidence_id <= 0:
            raise LifecycleEventError(
                "invalid_event_payload",
                "Evidence lifecycle events require a positive evidence_id.",
            )
        if evidence_kind not in {"confirmation_url", "confirmation_text", "note"}:
            raise LifecycleEventError(
                "invalid_event_payload",
                "Evidence lifecycle events require a supported evidence_kind.",
            )
        if kind in {"evidence_edited", "evidence_deleted"}:
            version = safe_payload.get("version")
            if not isinstance(version, int) or isinstance(version, bool) or version < 1:
                raise LifecycleEventError(
                    "invalid_event_payload",
                    "Edited/deleted evidence events require a positive version.",
                )

    reason = safe_payload.get("reason")
    if reason is not None:
        try:
            safe_payload["reason"] = validate_correction_reason(reason)
        except EvidenceContractError as exc:
            raise LifecycleEventError(exc.code, exc.message) from exc

    correction_of = safe_payload.get("correction_of")
    if kind == "status_changed" and (
        correction_of is not None or reason is not None
    ):
        if (
            not isinstance(correction_of, int)
            or isinstance(correction_of, bool)
            or correction_of <= 0
            or reason is None
        ):
            raise LifecycleEventError(
                "invalid_event_payload",
                "Status correction payloads require correction_of and a bounded reason.",
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


def record_visit(
    session: Session,
    *,
    user_id: int,
    row: CsvRow,
    occurred_at: datetime,
    source: str = "row_click",
) -> bool:
    """Record the first real browser visit and mutate the row in one transaction."""
    if row.user_id != user_id:
        raise LifecycleEventError(
            "inaccessible_csv_row", "CSV row is not available to this account."
        )
    if row.clicked:
        return False

    occurred_at_utc = _normalize_utc(occurred_at)
    row.clicked = True
    row.clicked_at = occurred_at_utc
    write_event(
        session,
        user_id=user_id,
        job_url=row.url,
        kind="first_visited",
        occurred_at=occurred_at_utc,
        source=source,
        csv_row_id=row.id,
    )
    return True


def apply_job_track_changes(
    session: Session,
    *,
    user_id: int,
    item: JobTrack,
    source: str,
    operation_id: UUID | str,
    now: datetime,
    status: Any = _UNSET,
    applied_at: Any = _UNSET,
    follow_up_at: Any = _UNSET,
    mark_applied: bool = False,
    infer_applied_at_from_status: bool = True,
) -> dict[str, bool]:
    """Apply lifecycle state changes without committing the caller-owned transaction."""
    if item.user_id != user_id:
        raise LifecycleEventError(
            "inaccessible_job_track", "Application is not available to this account."
        )
    if item.id is None:
        session.flush()

    now_utc = _normalize_utc(now)
    root_operation_id = coerce_operation_id(operation_id)

    previous_status = item.status
    previous_applied_at = item.applied_at
    previous_follow_up_at = item.follow_up_at

    target_status = previous_status if status is _UNSET else status
    explicit_applied_at = applied_at is not _UNSET
    explicit_follow_up_at = follow_up_at is not _UNSET

    if explicit_applied_at:
        target_applied_at = (
            None if applied_at is None else _normalize_utc(applied_at)
        )
    else:
        target_applied_at = previous_applied_at

    if explicit_follow_up_at:
        target_follow_up_at = (
            None if follow_up_at is None else _normalize_utc(follow_up_at)
        )
    else:
        target_follow_up_at = previous_follow_up_at

    if mark_applied:
        target_status = "applied"

    if (
        infer_applied_at_from_status
        and target_status == "applied"
        and target_applied_at is None
        and (mark_applied or status is not _UNSET)
    ):
        target_applied_at = now_utc

    status_changed = target_status != previous_status
    applied_changed = target_applied_at != previous_applied_at
    follow_up_changed = target_follow_up_at != previous_follow_up_at

    if status is not _UNSET or mark_applied:
        item.status = target_status
    if explicit_applied_at or (
        infer_applied_at_from_status
        and target_status == "applied"
        and previous_applied_at is None
        and target_applied_at is not None
    ):
        item.applied_at = target_applied_at
    if explicit_follow_up_at:
        item.follow_up_at = target_follow_up_at
    item.updated_at = now_utc

    if previous_applied_at is None and target_applied_at is not None:
        write_event(
            session,
            user_id=user_id,
            job_url=item.url,
            kind="first_applied",
            occurred_at=target_applied_at,
            source=source,
            csv_row_id=item.csv_row_id,
            job_track_id=item.id,
        )
    elif (
        explicit_applied_at
        and previous_applied_at is not None
        and applied_changed
    ):
        write_event(
            session,
            user_id=user_id,
            job_url=item.url,
            kind="applied_date_corrected",
            occurred_at=now_utc,
            source=source,
            payload={
                "from": _payload_datetime(previous_applied_at),
                "to": _payload_datetime(target_applied_at),
            },
            csv_row_id=item.csv_row_id,
            job_track_id=item.id,
            operation_id=child_operation_id(
                root_operation_id, item.id, "applied_date_corrected"
            ),
        )

    if status_changed:
        write_event(
            session,
            user_id=user_id,
            job_url=item.url,
            kind="status_changed",
            occurred_at=now_utc,
            source=source,
            payload={"from": previous_status, "to": target_status},
            csv_row_id=item.csv_row_id,
            job_track_id=item.id,
            operation_id=child_operation_id(
                root_operation_id, item.id, "status_changed"
            ),
        )

    if explicit_follow_up_at and follow_up_changed:
        write_event(
            session,
            user_id=user_id,
            job_url=item.url,
            kind="followup_changed",
            occurred_at=now_utc,
            source=source,
            payload={
                "from": _payload_datetime(previous_follow_up_at),
                "to": _payload_datetime(target_follow_up_at),
            },
            csv_row_id=item.csv_row_id,
            job_track_id=item.id,
            operation_id=child_operation_id(
                root_operation_id, item.id, "followup_changed"
            ),
        )

    return {
        "status_changed": status_changed,
        "applied_changed": applied_changed,
        "follow_up_changed": follow_up_changed,
    }


MAX_LEGACY_BACKFILL_BATCH_SIZE = 500

LEGACY_BACKFILL_REVIEW_QUERIES = {
    "clicked_without_date": (
        "SELECT id, url FROM csv_rows "
        "WHERE user_id = :user_id AND clicked = true AND clicked_at IS NULL "
        "ORDER BY id"
    ),
    "applied_without_date": (
        "SELECT id, url, status FROM job_tracks "
        "WHERE user_id = :user_id AND status = 'applied' AND applied_at IS NULL "
        "ORDER BY id"
    ),
    "duplicate_csv_urls": (
        "SELECT url, COUNT(*) FROM csv_rows WHERE user_id = :user_id "
        "GROUP BY url HAVING COUNT(*) > 1 ORDER BY COUNT(*) DESC"
    ),
    "duplicate_track_urls": (
        "SELECT url, COUNT(*) FROM job_tracks WHERE user_id = :user_id "
        "GROUP BY url HAVING COUNT(*) > 1 ORDER BY COUNT(*) DESC"
    ),
}


def validate_timezone_name(value: str) -> str:
    """Return one validated IANA timezone name without accepting raw offsets."""
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > 64:
        raise LifecycleEventError(
            "invalid_timezone",
            "timezone must be a valid IANA timezone name of at most 64 characters.",
        )
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise LifecycleEventError(
            "invalid_timezone",
            "timezone must be a valid IANA timezone name.",
        ) from exc
    return value


def _aware_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if not isinstance(value, datetime):
        raise LifecycleEventError(
            "invalid_reference_time", "reference time must be a datetime."
        )
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def local_day_utc_bounds(
    timezone_name: str,
    *,
    reference: datetime | None = None,
) -> tuple[datetime, datetime]:
    """Map the reference instant's local calendar day to stored naive UTC bounds."""
    tz = ZoneInfo(validate_timezone_name(timezone_name))
    local_reference = _aware_utc(reference).astimezone(tz)
    start_local = datetime.combine(
        local_reference.date(), datetime.min.time(), tzinfo=tz
    )
    end_local = datetime.combine(
        local_reference.date() + timedelta(days=1),
        datetime.min.time(),
        tzinfo=tz,
    )
    return (
        start_local.astimezone(timezone.utc).replace(tzinfo=None),
        end_local.astimezone(timezone.utc).replace(tzinfo=None),
    )


def rolling_week_utc_bounds(
    timezone_name: str,
    *,
    reference: datetime | None = None,
) -> tuple[datetime, datetime]:
    """Return the previous seven local-calendar days ending at the reference instant."""
    tz = ZoneInfo(validate_timezone_name(timezone_name))
    end_utc = _aware_utc(reference)
    local_end = end_utc.astimezone(tz)
    local_start = local_end - timedelta(days=7)
    return (
        local_start.astimezone(timezone.utc).replace(tzinfo=None),
        end_utc.replace(tzinfo=None),
    )


def legacy_backfill_warning_counts(session: Session, *, user_id: int) -> dict[str, int]:
    """Return aggregate reconciliation warnings without exposing private record values."""
    duplicate_csv_urls = (
        session.query(CsvRow.url)
        .filter(CsvRow.user_id == user_id)
        .group_by(CsvRow.url)
        .having(func.count(CsvRow.id) > 1)
        .count()
    )
    duplicate_track_urls = (
        session.query(JobTrack.url)
        .filter(JobTrack.user_id == user_id)
        .group_by(JobTrack.url)
        .having(func.count(JobTrack.id) > 1)
        .count()
    )
    return {
        "clicked_without_date": int(
            session.query(func.count(CsvRow.id))
            .filter(
                CsvRow.user_id == user_id,
                CsvRow.clicked.is_(True),
                CsvRow.clicked_at.is_(None),
            )
            .scalar()
            or 0
        ),
        "applied_without_date": int(
            session.query(func.count(JobTrack.id))
            .filter(
                JobTrack.user_id == user_id,
                JobTrack.status == "applied",
                JobTrack.applied_at.is_(None),
            )
            .scalar()
            or 0
        ),
        "duplicate_csv_urls": int(duplicate_csv_urls),
        "duplicate_track_urls": int(duplicate_track_urls),
    }


def _duplicate_urls(session: Session, model: Any, *, user_id: int) -> set[str]:
    id_column = model.id
    return {
        url
        for (url,) in (
            session.query(model.url)
            .filter(model.user_id == user_id)
            .group_by(model.url)
            .having(func.count(id_column) > 1)
            .all()
        )
    }


def _first_event_exists(
    session: Session,
    *,
    user_id: int,
    job_url: str,
    kind: str,
) -> bool:
    key = first_event_key(user_id, job_url, kind)
    return (
        session.query(JobLifecycleEvent.id)
        .filter(
            JobLifecycleEvent.user_id == user_id,
            JobLifecycleEvent.event_key == key,
        )
        .first()
        is not None
    )


def backfill_legacy_visits(
    session: Session,
    *,
    user_id: int,
    after_id: int = 0,
    limit: int = MAX_LEGACY_BACKFILL_BATCH_SIZE,
    dry_run: bool = False,
) -> dict[str, int | bool]:
    """Scan one bounded legacy visit batch. Caller owns commit/rollback."""
    if limit < 1 or limit > MAX_LEGACY_BACKFILL_BATCH_SIZE:
        raise LifecycleEventError(
            "invalid_backfill_limit",
            f"Backfill batch size must be between 1 and {MAX_LEGACY_BACKFILL_BATCH_SIZE}.",
        )
    rows = (
        session.query(CsvRow)
        .filter(
            CsvRow.user_id == user_id,
            CsvRow.id > max(0, int(after_id)),
            ((CsvRow.clicked_at.isnot(None)) | (CsvRow.clicked.is_(True))),
        )
        .order_by(CsvRow.id.asc())
        .limit(limit)
        .all()
    )
    duplicates = _duplicate_urls(session, CsvRow, user_id=user_id)
    result: dict[str, int | bool] = {
        "scanned": len(rows),
        "eligible": 0,
        "created": 0,
        "already_present": 0,
        "missing_dates": 0,
        "duplicate_conflicts": 0,
        "last_id": rows[-1].id if rows else max(0, int(after_id)),
        "has_more": False,
    }
    for row in rows:
        if row.url in duplicates:
            result["duplicate_conflicts"] = int(result["duplicate_conflicts"]) + 1
            continue
        if row.clicked_at is None:
            result["missing_dates"] = int(result["missing_dates"]) + 1
            continue
        result["eligible"] = int(result["eligible"]) + 1
        if _first_event_exists(
            session,
            user_id=user_id,
            job_url=row.url,
            kind="first_visited",
        ):
            result["already_present"] = int(result["already_present"]) + 1
            continue
        if not dry_run:
            write_event(
                session,
                user_id=user_id,
                job_url=row.url,
                kind="first_visited",
                occurred_at=row.clicked_at,
                source="legacy_backfill",
                csv_row_id=row.id,
            )
        result["created"] = int(result["created"]) + 1

    last_id = int(result["last_id"])
    result["has_more"] = (
        session.query(CsvRow.id)
        .filter(
            CsvRow.user_id == user_id,
            CsvRow.id > last_id,
            ((CsvRow.clicked_at.isnot(None)) | (CsvRow.clicked.is_(True))),
        )
        .first()
        is not None
    )
    return result


def backfill_legacy_applications(
    session: Session,
    *,
    user_id: int,
    after_id: int = 0,
    limit: int = MAX_LEGACY_BACKFILL_BATCH_SIZE,
    dry_run: bool = False,
) -> dict[str, int | bool]:
    """Scan one bounded legacy application batch. Caller owns commit/rollback."""
    if limit < 1 or limit > MAX_LEGACY_BACKFILL_BATCH_SIZE:
        raise LifecycleEventError(
            "invalid_backfill_limit",
            f"Backfill batch size must be between 1 and {MAX_LEGACY_BACKFILL_BATCH_SIZE}.",
        )
    tracks = (
        session.query(JobTrack)
        .filter(
            JobTrack.user_id == user_id,
            JobTrack.id > max(0, int(after_id)),
            ((JobTrack.applied_at.isnot(None)) | (JobTrack.status == "applied")),
        )
        .order_by(JobTrack.id.asc())
        .limit(limit)
        .all()
    )
    duplicates = _duplicate_urls(session, JobTrack, user_id=user_id)
    result: dict[str, int | bool] = {
        "scanned": len(tracks),
        "eligible": 0,
        "created": 0,
        "already_present": 0,
        "missing_dates": 0,
        "duplicate_conflicts": 0,
        "last_id": tracks[-1].id if tracks else max(0, int(after_id)),
        "has_more": False,
    }
    for track in tracks:
        if track.url in duplicates:
            result["duplicate_conflicts"] = int(result["duplicate_conflicts"]) + 1
            continue
        if track.applied_at is None:
            result["missing_dates"] = int(result["missing_dates"]) + 1
            continue
        result["eligible"] = int(result["eligible"]) + 1
        if _first_event_exists(
            session,
            user_id=user_id,
            job_url=track.url,
            kind="first_applied",
        ):
            result["already_present"] = int(result["already_present"]) + 1
            continue
        if not dry_run:
            write_event(
                session,
                user_id=user_id,
                job_url=track.url,
                kind="first_applied",
                occurred_at=track.applied_at,
                source="legacy_backfill",
                csv_row_id=track.csv_row_id,
                job_track_id=track.id,
            )
        result["created"] = int(result["created"]) + 1

    last_id = int(result["last_id"])
    result["has_more"] = (
        session.query(JobTrack.id)
        .filter(
            JobTrack.user_id == user_id,
            JobTrack.id > last_id,
            ((JobTrack.applied_at.isnot(None)) | (JobTrack.status == "applied")),
        )
        .first()
        is not None
    )
    return result


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


def metric_counts(
    session: Session,
    *,
    user_id: int,
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict[str, int]:
    """Return the shared saved/visited/applied definitions for one account.

    Saved records use JobTrack.created_at. Visited and applied use the durable
    lifecycle occurrence timestamp so every read path shares the same semantics.
    """
    event_query = session.query(
        JobLifecycleEvent.kind,
        func.count(JobLifecycleEvent.id),
    ).filter(
        JobLifecycleEvent.user_id == user_id,
        JobLifecycleEvent.kind.in_(FIRST_EVENT_KINDS),
    )
    event_query = _apply_time_window(
        event_query, JobLifecycleEvent.occurred_at, start, end
    )
    by_kind = {
        kind: int(count)
        for kind, count in event_query.group_by(JobLifecycleEvent.kind).all()
    }
    return {
        "saved": count_saved(session, user_id=user_id, start=start, end=end),
        "visited": by_kind.get("first_visited", 0),
        "applied": by_kind.get("first_applied", 0),
    }


def count_visited_without_applied(
    session: Session,
    *,
    user_id: int,
) -> int:
    """Count durable first visits whose exact URL has no first-application fact."""
    visited = aliased(JobLifecycleEvent)
    applied = aliased(JobLifecycleEvent)
    applied_exists = (
        session.query(applied.id)
        .filter(
            applied.user_id == user_id,
            applied.kind == "first_applied",
            applied.job_url == visited.job_url,
        )
        .exists()
    )
    return int(
        session.query(func.count(visited.id))
        .filter(
            visited.user_id == user_id,
            visited.kind == "first_visited",
            ~applied_exists,
        )
        .scalar()
        or 0
    )
