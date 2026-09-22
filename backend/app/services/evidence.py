from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import and_, false, func, or_, true, update
from sqlalchemy.orm import Session

from ..evidence_schemas import (
    EVIDENCE_RECEIPT_RETENTION_DAYS,
    EVIDENCE_SOFT_DELETE_RETENTION_DAYS,
    EvidenceContractError,
    EvidenceCreateData,
    evidence_create_payload_hash,
    validate_correction_reason,
)
from ..models import (
    ApplicationEvidence,
    EvidenceCreateReceipt,
    JobLifecycleEvent,
    JobTrack,
)
from .lifecycle import (
    LifecycleEventError,
    apply_job_track_changes,
    write_event,
)
from .validation import ValidationContractError, validate_status


MAX_EVIDENCE_MAINTENANCE_BATCH = 500
MAX_TIMELINE_LIMIT = 100
DEFAULT_TIMELINE_LIMIT = 50

_TIMELINE_LIFECYCLE_RANK = 0
_TIMELINE_EVIDENCE_RANK = 1
_UNSET = object()


class EvidenceServiceError(ValueError):
    def __init__(self, code: str, message: str, *, status_code: int = 422):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class EvidenceMaintenanceResult:
    bodies_blanked: int
    receipts_deleted: int


@dataclass(frozen=True)
class EvidenceCreateResult:
    evidence: ApplicationEvidence
    replayed: bool


@dataclass(frozen=True)
class EvidenceDeleteResult:
    evidence: ApplicationEvidence
    changed: bool


@dataclass(frozen=True)
class TimelineCursor:
    timestamp: datetime
    type_rank: int
    item_id: int


@dataclass(frozen=True)
class TimelinePage:
    items: list[dict[str, Any]]
    next_before: str | None


def _normalize_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise EvidenceServiceError(
            "invalid_timestamp", "Timestamp must be a valid datetime."
        )
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _iso_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _normalize_utc(value).isoformat() + "Z"


def _canonical_request_key(value: UUID | str) -> str:
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise EvidenceServiceError(
            "invalid_idempotency_key",
            "Idempotency-Key must be a valid UUID.",
        ) from exc


def require_owned_track(
    session: Session,
    *,
    user_id: int,
    track_id: int,
    for_update: bool = False,
) -> JobTrack:
    """Resolve an evidence parent only inside the authenticated account."""
    query = session.query(JobTrack).filter(
        JobTrack.id == track_id,
        JobTrack.user_id == user_id,
    )
    if for_update:
        query = query.with_for_update()
    track = query.first()
    if track is None:
        raise EvidenceServiceError(
            "inaccessible_job_track",
            "Application is not available to this account.",
            status_code=404,
        )
    return track


def require_owned_evidence(
    session: Session,
    *,
    user_id: int,
    track_id: int,
    evidence_id: int,
    for_update: bool = False,
) -> ApplicationEvidence:
    query = session.query(ApplicationEvidence).filter(
        ApplicationEvidence.id == evidence_id,
        ApplicationEvidence.user_id == user_id,
        ApplicationEvidence.track_id == track_id,
    )
    if for_update:
        query = query.with_for_update()
    evidence = query.first()
    if evidence is None:
        raise EvidenceServiceError(
            "inaccessible_evidence",
            "Evidence is not available to this account.",
            status_code=404,
        )
    return evidence


def serialize_evidence(evidence: ApplicationEvidence) -> dict[str, Any]:
    """Return the ordinary API representation without retained deleted bodies."""
    payload: dict[str, Any] = {
        "id": evidence.id,
        "track_id": evidence.track_id,
        "kind": evidence.kind,
        "occurred_at": _iso_timestamp(evidence.occurred_at),
        "created_at": _iso_timestamp(evidence.created_at),
        "updated_at": _iso_timestamp(evidence.updated_at),
        "version": evidence.version,
        "is_deleted": bool(evidence.is_deleted),
    }
    if not evidence.is_deleted:
        payload["body"] = evidence.body
    return payload


def create_evidence(
    session: Session,
    *,
    user_id: int,
    track_id: int,
    data: EvidenceCreateData,
    request_key: UUID | str,
    now: datetime,
) -> EvidenceCreateResult:
    """Create evidence, its receipt, and its immutable marker in one caller transaction."""
    track = require_owned_track(session, user_id=user_id, track_id=track_id)
    canonical_key = _canonical_request_key(request_key)
    payload_hash = evidence_create_payload_hash(track_id=track_id, data=data)

    existing_receipt = (
        session.query(EvidenceCreateReceipt)
        .filter(
            EvidenceCreateReceipt.user_id == user_id,
            EvidenceCreateReceipt.request_key == canonical_key,
        )
        .first()
    )
    if existing_receipt is not None:
        if existing_receipt.payload_hash != payload_hash:
            raise EvidenceServiceError(
                "idempotency_conflict",
                "Idempotency-Key was already used for different evidence input.",
                status_code=409,
            )
        evidence = (
            session.query(ApplicationEvidence)
            .filter(
                ApplicationEvidence.id == existing_receipt.evidence_id,
                ApplicationEvidence.user_id == user_id,
                ApplicationEvidence.track_id == track_id,
            )
            .first()
        )
        if evidence is None:
            raise EvidenceServiceError(
                "idempotency_state_missing",
                "The recorded evidence result is unavailable.",
                status_code=500,
            )
        return EvidenceCreateResult(evidence=evidence, replayed=True)

    now_utc = _normalize_utc(now)
    evidence = ApplicationEvidence(
        user_id=user_id,
        track_id=track_id,
        kind=data.kind,
        body=data.body,
        occurred_at=(
            _normalize_utc(data.occurred_at)
            if data.occurred_at is not None
            else None
        ),
        created_at=now_utc,
        updated_at=now_utc,
        version=1,
        is_deleted=False,
    )
    session.add(evidence)
    session.flush()

    write_event(
        session,
        user_id=user_id,
        job_url=track.url,
        kind="evidence_added",
        occurred_at=now_utc,
        source="user",
        payload={
            "evidence_id": evidence.id,
            "evidence_kind": evidence.kind,
        },
        csv_row_id=track.csv_row_id,
        job_track_id=track.id,
        operation_id=canonical_key,
    )
    session.add(
        EvidenceCreateReceipt(
            user_id=user_id,
            request_key=canonical_key,
            payload_hash=payload_hash,
            evidence_id=evidence.id,
            created_at=now_utc,
        )
    )
    session.flush()
    return EvidenceCreateResult(evidence=evidence, replayed=False)


def _validate_edited_evidence(
    evidence: ApplicationEvidence,
    *,
    body: Any,
    occurred_at: Any,
) -> tuple[str, datetime | None]:
    target_body = evidence.body if body is _UNSET else body
    target_occurred_at = evidence.occurred_at if occurred_at is _UNSET else occurred_at
    if not isinstance(target_body, str):
        raise EvidenceServiceError(
            "invalid_evidence",
            "Evidence body must be a non-empty string.",
        )
    try:
        validated = EvidenceCreateData(
            kind=evidence.kind,
            body=target_body,
            occurred_at=target_occurred_at,
        )
    except (ValidationError, EvidenceContractError) as exc:
        raise EvidenceServiceError(
            "invalid_evidence",
            "Evidence input is invalid for its evidence kind.",
        ) from exc
    normalized_occurred_at = (
        _normalize_utc(validated.occurred_at)
        if validated.occurred_at is not None
        else None
    )
    return validated.body, normalized_occurred_at


def edit_evidence(
    session: Session,
    *,
    user_id: int,
    track_id: int,
    evidence_id: int,
    version: int,
    operation_id: UUID | str,
    now: datetime,
    body: Any = _UNSET,
    occurred_at: Any = _UNSET,
) -> ApplicationEvidence:
    """Edit mutable evidence fields with an optimistic version guard."""
    track = require_owned_track(
        session, user_id=user_id, track_id=track_id, for_update=True
    )
    evidence = require_owned_evidence(
        session,
        user_id=user_id,
        track_id=track_id,
        evidence_id=evidence_id,
        for_update=True,
    )
    if evidence.is_deleted:
        raise EvidenceServiceError(
            "evidence_deleted",
            "Deleted evidence cannot be edited.",
            status_code=409,
        )
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise EvidenceServiceError(
            "invalid_evidence_version",
            "Evidence version must be a positive integer.",
        )
    if evidence.version != version:
        raise EvidenceServiceError(
            "stale_evidence_version",
            "Evidence changed after the supplied version. Reload and retry.",
            status_code=409,
        )
    if body is _UNSET and occurred_at is _UNSET:
        raise EvidenceServiceError(
            "empty_evidence_edit",
            "At least one evidence field must be edited.",
        )

    target_body, target_occurred_at = _validate_edited_evidence(
        evidence,
        body=body,
        occurred_at=occurred_at,
    )
    if target_body == evidence.body and target_occurred_at == evidence.occurred_at:
        return evidence

    now_utc = _normalize_utc(now)
    evidence.body = target_body
    evidence.occurred_at = target_occurred_at
    evidence.version += 1
    evidence.updated_at = now_utc
    session.flush()

    write_event(
        session,
        user_id=user_id,
        job_url=track.url,
        kind="evidence_edited",
        occurred_at=now_utc,
        source="user",
        payload={
            "evidence_id": evidence.id,
            "evidence_kind": evidence.kind,
            "version": evidence.version,
        },
        csv_row_id=track.csv_row_id,
        job_track_id=track.id,
        operation_id=operation_id,
    )
    return evidence


def delete_evidence(
    session: Session,
    *,
    user_id: int,
    track_id: int,
    evidence_id: int,
    operation_id: UUID | str,
    now: datetime,
) -> EvidenceDeleteResult:
    """Soft-delete evidence; repeated owner deletes are successful no-ops."""
    track = require_owned_track(
        session, user_id=user_id, track_id=track_id, for_update=True
    )
    evidence = require_owned_evidence(
        session,
        user_id=user_id,
        track_id=track_id,
        evidence_id=evidence_id,
        for_update=True,
    )
    if evidence.is_deleted:
        return EvidenceDeleteResult(evidence=evidence, changed=False)

    now_utc = _normalize_utc(now)
    evidence.is_deleted = True
    evidence.version += 1
    evidence.updated_at = now_utc
    session.flush()

    write_event(
        session,
        user_id=user_id,
        job_url=track.url,
        kind="evidence_deleted",
        occurred_at=now_utc,
        source="user",
        payload={
            "evidence_id": evidence.id,
            "evidence_kind": evidence.kind,
            "version": evidence.version,
        },
        csv_row_id=track.csv_row_id,
        job_track_id=track.id,
        operation_id=operation_id,
    )
    return EvidenceDeleteResult(evidence=evidence, changed=True)


def _timeline_source_label(source: str) -> str:
    lowered = (source or "").lower()
    if "legacy" in lowered:
        return "legacy"
    if "import" in lowered or "applypilot" in lowered:
        return "import"
    if lowered in {"user", "application_patch", "bulk_update", "follow_up"}:
        return "user"
    return "system"


def encode_timeline_cursor(cursor: TimelineCursor) -> str:
    raw = json.dumps(
        [
            _iso_timestamp(cursor.timestamp),
            cursor.type_rank,
            cursor.item_id,
        ],
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_timeline_cursor(value: str) -> TimelineCursor:
    if not isinstance(value, str) or not value or len(value) > 512:
        raise EvidenceServiceError(
            "invalid_timeline_cursor", "Timeline cursor is invalid."
        )
    try:
        padded = value + ("=" * (-len(value) % 4))
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
        timestamp_raw, type_rank, item_id = json.loads(decoded.decode("utf-8"))
        if (
            not isinstance(timestamp_raw, str)
            or type_rank not in {_TIMELINE_LIFECYCLE_RANK, _TIMELINE_EVIDENCE_RANK}
            or not isinstance(item_id, int)
            or isinstance(item_id, bool)
            or item_id <= 0
        ):
            raise ValueError
        parsed = datetime.fromisoformat(timestamp_raw.replace("Z", "+00:00"))
        timestamp = _normalize_utc(parsed)
    except (ValueError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceServiceError(
            "invalid_timeline_cursor", "Timeline cursor is invalid."
        ) from exc
    return TimelineCursor(
        timestamp=timestamp,
        type_rank=type_rank,
        item_id=item_id,
    )


def _before_condition(timestamp_col, id_col, rank: int, cursor: TimelineCursor | None):
    if cursor is None:
        return true()
    if rank < cursor.type_rank:
        tie_condition = true()
    elif rank == cursor.type_rank:
        tie_condition = id_col < cursor.item_id
    else:
        tie_condition = false()
    return or_(
        timestamp_col < cursor.timestamp,
        and_(timestamp_col == cursor.timestamp, tie_condition),
    )


def _lifecycle_timeline_item(event: JobLifecycleEvent) -> dict[str, Any]:
    return {
        "type": "lifecycle",
        "id": event.id,
        "timestamp": _iso_timestamp(event.occurred_at),
        "kind": event.kind,
        "source": _timeline_source_label(event.source),
        "payload": dict(event.payload or {}),
    }


def _evidence_timeline_item(
    evidence: ApplicationEvidence,
    timestamp: datetime,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "type": "evidence",
        "id": evidence.id,
        "timestamp": _iso_timestamp(timestamp),
        "kind": evidence.kind,
        "source": "user",
        "track_id": evidence.track_id,
        "version": evidence.version,
        "is_deleted": bool(evidence.is_deleted),
        "created_at": _iso_timestamp(evidence.created_at),
        "updated_at": _iso_timestamp(evidence.updated_at),
    }
    if not evidence.is_deleted:
        item["body"] = evidence.body
    return item


def get_timeline(
    session: Session,
    *,
    user_id: int,
    track_id: int,
    before: str | None = None,
    limit: int = DEFAULT_TIMELINE_LIMIT,
) -> TimelinePage:
    """Return the newest bounded page, rendered in chronological order."""
    require_owned_track(session, user_id=user_id, track_id=track_id)
    if (
        not isinstance(limit, int)
        or isinstance(limit, bool)
        or not 1 <= limit <= MAX_TIMELINE_LIMIT
    ):
        raise EvidenceServiceError(
            "invalid_timeline_limit",
            f"Timeline limit must be between 1 and {MAX_TIMELINE_LIMIT}.",
        )
    cursor = decode_timeline_cursor(before) if before else None

    lifecycle_query = session.query(JobLifecycleEvent).filter(
        JobLifecycleEvent.user_id == user_id,
        JobLifecycleEvent.job_track_id == track_id,
        _before_condition(
            JobLifecycleEvent.occurred_at,
            JobLifecycleEvent.id,
            _TIMELINE_LIFECYCLE_RANK,
            cursor,
        ),
    )
    lifecycle_rows = (
        lifecycle_query
        .order_by(JobLifecycleEvent.occurred_at.desc(), JobLifecycleEvent.id.desc())
        .limit(limit + 1)
        .all()
    )

    evidence_timestamp = func.coalesce(
        ApplicationEvidence.occurred_at,
        ApplicationEvidence.created_at,
    )
    evidence_query = session.query(ApplicationEvidence).filter(
        ApplicationEvidence.user_id == user_id,
        ApplicationEvidence.track_id == track_id,
        _before_condition(
            evidence_timestamp,
            ApplicationEvidence.id,
            _TIMELINE_EVIDENCE_RANK,
            cursor,
        ),
    )
    evidence_rows = (
        evidence_query
        .order_by(evidence_timestamp.desc(), ApplicationEvidence.id.desc())
        .limit(limit + 1)
        .all()
    )

    merged: list[tuple[datetime, int, int, dict[str, Any]]] = []
    for event in lifecycle_rows:
        merged.append(
            (
                _normalize_utc(event.occurred_at),
                _TIMELINE_LIFECYCLE_RANK,
                event.id,
                _lifecycle_timeline_item(event),
            )
        )
    for evidence in evidence_rows:
        timestamp = _normalize_utc(evidence.occurred_at or evidence.created_at)
        merged.append(
            (
                timestamp,
                _TIMELINE_EVIDENCE_RANK,
                evidence.id,
                _evidence_timeline_item(evidence, timestamp),
            )
        )

    merged.sort(key=lambda value: (value[0], value[1], value[2]), reverse=True)
    has_more = len(merged) > limit
    selected = merged[:limit]
    next_before = None
    if has_more and selected:
        oldest = selected[-1]
        next_before = encode_timeline_cursor(
            TimelineCursor(
                timestamp=oldest[0],
                type_rank=oldest[1],
                item_id=oldest[2],
            )
        )

    return TimelinePage(
        items=[value[3] for value in reversed(selected)],
        next_before=next_before,
    )


def correct_applied_date(
    session: Session,
    *,
    user_id: int,
    track_id: int,
    applied_at: datetime,
    reason: str,
    operation_id: UUID | str,
    now: datetime,
) -> JobTrack:
    """Correct an existing applied date while preserving the first-applied fact."""
    track = require_owned_track(
        session, user_id=user_id, track_id=track_id, for_update=True
    )
    try:
        bounded_reason = validate_correction_reason(reason)
    except EvidenceContractError as exc:
        raise EvidenceServiceError(exc.code, exc.message) from exc
    if track.applied_at is None:
        raise EvidenceServiceError(
            "missing_applied_date",
            "An existing applied date is required before it can be corrected.",
            status_code=409,
        )
    target = _normalize_utc(applied_at)
    if target == track.applied_at:
        raise EvidenceServiceError(
            "unchanged_applied_date",
            "Corrected applied date must differ from the current applied date.",
            status_code=409,
        )

    apply_job_track_changes(
        session,
        user_id=user_id,
        item=track,
        source="user",
        operation_id=operation_id,
        now=_normalize_utc(now),
        applied_at=target,
        infer_applied_at_from_status=False,
        applied_correction_reason=bounded_reason,
    )
    return track


def correct_latest_status(
    session: Session,
    *,
    user_id: int,
    track_id: int,
    expected_event_id: int,
    restore_status: str,
    reason: str,
    operation_id: UUID | str,
    now: datetime,
) -> JobTrack:
    """Append a compensating status event if the expected event is still latest."""
    track = require_owned_track(
        session, user_id=user_id, track_id=track_id, for_update=True
    )
    try:
        requested_status = validate_status(restore_status)
    except ValidationContractError as exc:
        raise EvidenceServiceError(exc.code, exc.message) from exc
    try:
        bounded_reason = validate_correction_reason(reason)
    except EvidenceContractError as exc:
        raise EvidenceServiceError(exc.code, exc.message) from exc

    latest = (
        session.query(JobLifecycleEvent)
        .filter(
            JobLifecycleEvent.user_id == user_id,
            JobLifecycleEvent.job_track_id == track_id,
            JobLifecycleEvent.kind == "status_changed",
        )
        .order_by(
            JobLifecycleEvent.occurred_at.desc(),
            JobLifecycleEvent.id.desc(),
        )
        .first()
    )
    if latest is None or latest.id != expected_event_id:
        raise EvidenceServiceError(
            "status_correction_conflict",
            "The expected status event is no longer the latest status change.",
            status_code=409,
        )
    payload = dict(latest.payload or {})
    previous_status = payload.get("from")
    current_status = payload.get("to")
    if track.status != current_status:
        raise EvidenceServiceError(
            "status_correction_conflict",
            "Application status changed after the expected event.",
            status_code=409,
        )
    if requested_status != previous_status:
        raise EvidenceServiceError(
            "status_restore_mismatch",
            "restore_status must match the expected event's prior status.",
            status_code=409,
        )

    now_utc = _normalize_utc(now)
    track.status = requested_status
    track.updated_at = now_utc
    session.flush()
    try:
        write_event(
            session,
            user_id=user_id,
            job_url=track.url,
            kind="status_changed",
            occurred_at=now_utc,
            source="user",
            payload={
                "from": current_status,
                "to": requested_status,
                "correction_of": latest.id,
                "reason": bounded_reason,
            },
            csv_row_id=track.csv_row_id,
            job_track_id=track.id,
            operation_id=operation_id,
        )
    except LifecycleEventError:
        raise
    return track


def purge_expired_evidence_recovery_state(
    session: Session,
    *,
    now: datetime,
    limit: int = MAX_EVIDENCE_MAINTENANCE_BATCH,
) -> EvidenceMaintenanceResult:
    """Bound recovery retention without deleting evidence history markers.

    The caller owns the transaction and scheduling. JG-033 intentionally adds
    no background scheduler. Deleted evidence keeps its row and audit metadata
    after the private body is blanked. Short-lived create receipts are removed
    after the same thirty-day window.
    """
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_EVIDENCE_MAINTENANCE_BATCH:
        raise EvidenceServiceError(
            "invalid_maintenance_limit",
            f"limit must be between 1 and {MAX_EVIDENCE_MAINTENANCE_BATCH}.",
        )
    if now.tzinfo is not None:
        now = now.astimezone(timezone.utc).replace(tzinfo=None)

    evidence_cutoff = now - timedelta(days=EVIDENCE_SOFT_DELETE_RETENTION_DAYS)
    expired_evidence = (
        session.query(ApplicationEvidence)
        .filter(
            ApplicationEvidence.is_deleted.is_(True),
            ApplicationEvidence.body.is_not(None),
            ApplicationEvidence.updated_at <= evidence_cutoff,
        )
        .order_by(ApplicationEvidence.updated_at.asc(), ApplicationEvidence.id.asc())
        .limit(limit)
        .all()
    )
    for item in expired_evidence:
        deleted_at = item.updated_at
        session.execute(
            update(ApplicationEvidence)
            .where(ApplicationEvidence.id == item.id)
            .values(body=None, updated_at=deleted_at)
            .execution_options(synchronize_session=False)
        )
        session.expire(item)

    receipt_cutoff = now - timedelta(days=EVIDENCE_RECEIPT_RETENTION_DAYS)
    remaining = max(0, limit - len(expired_evidence))
    expired_receipts = (
        session.query(EvidenceCreateReceipt)
        .filter(EvidenceCreateReceipt.created_at <= receipt_cutoff)
        .order_by(EvidenceCreateReceipt.created_at.asc(), EvidenceCreateReceipt.id.asc())
        .limit(remaining)
        .all()
        if remaining
        else []
    )
    for receipt in expired_receipts:
        session.delete(receipt)

    return EvidenceMaintenanceResult(
        bodies_blanked=len(expired_evidence),
        receipts_deleted=len(expired_receipts),
    )
