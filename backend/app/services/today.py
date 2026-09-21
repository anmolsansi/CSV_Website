from __future__ import annotations

from dataclasses import fields
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import UUID

from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import CsvRow, JobTrack, SavedView, WorkItem, WorkItemOverride
from ..today_schemas import (
    WorkItemCreate,
    canonical_utc_timestamp,
    followup_action_key,
    manual_action_key,
    validate_owned_action_key,
    validate_owned_work_item_sources,
)
from .lifecycle import apply_job_track_changes, local_day_utc_bounds
from .row_queries import RowQuery, build_row_query, order_row_query

TERMINAL_FOLLOWUP_STATUSES = frozenset({"rejected", "offer", "not_applying"})
TODAY_CURSOR_SALT = "jobgrid-today-cursor-v1"
TODAY_CURSOR_VERSION = 1
MAX_TODAY_LIMIT = 100
MAX_FROM_VIEW_LIMIT = 20
MAX_SNOOZE_DAYS = 365


class TodayServiceError(ValueError):
    """Safe service-layer failure that can be mapped directly to an HTTP result."""

    def __init__(self, code: str, status_code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code

    def as_detail(self) -> dict[str, str]:
        return {"code": self.code, "message": str(self)}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _naive_utc(value: datetime) -> datetime:
    return _aware_utc(value).replace(tzinfo=None)


def _cursor_serializer(secret_key: str) -> URLSafeSerializer:
    return URLSafeSerializer(secret_key, salt=TODAY_CURSOR_SALT)


def _item_sort_key(item: dict[str, Any]) -> tuple[int, str, int, str, int]:
    due_at = item.get("due_at")
    return (
        1 if due_at is None else 0,
        due_at or "",
        -int(item.get("priority") or 0),
        str(item["type"]),
        int(item["id"]),
    )


def _encode_cursor(secret_key: str, *, as_of: datetime, item: dict[str, Any]) -> str:
    payload = {
        "v": TODAY_CURSOR_VERSION,
        "as_of": canonical_utc_timestamp(as_of),
        "last": list(_item_sort_key(item)),
    }
    return _cursor_serializer(secret_key).dumps(payload)


def _parse_iso_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise TodayServiceError("invalid_cursor", 422, "Invalid Today cursor.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TodayServiceError("invalid_cursor", 422, "Invalid Today cursor.")
    return parsed.astimezone(timezone.utc)


def _decode_cursor(
    secret_key: str,
    cursor: str,
) -> tuple[datetime, tuple[int, str, int, str, int]]:
    try:
        payload = _cursor_serializer(secret_key).loads(cursor)
    except BadSignature as exc:
        raise TodayServiceError("invalid_cursor", 422, "Invalid Today cursor.") from exc
    if not isinstance(payload, dict) or payload.get("v") != TODAY_CURSOR_VERSION:
        raise TodayServiceError("invalid_cursor", 422, "Invalid Today cursor.")
    last = payload.get("last")
    if (
        not isinstance(last, list)
        or len(last) != 5
        or isinstance(last[0], bool)
        or not isinstance(last[0], int)
        or not isinstance(last[1], str)
        or isinstance(last[2], bool)
        or not isinstance(last[2], int)
        or not isinstance(last[3], str)
        or isinstance(last[4], bool)
        or not isinstance(last[4], int)
    ):
        raise TodayServiceError("invalid_cursor", 422, "Invalid Today cursor.")
    return _parse_iso_utc(payload.get("as_of")), tuple(last)


def _manual_source_fields(item: WorkItem) -> tuple[str | None, str | None, str]:
    company: str | None = None
    role: str | None = None
    source = "Manual"
    if item.track is not None:
        company = item.track.company
        role = item.track.title
        source = "Application"
    elif item.row is not None:
        company = item.row.company_guess
        role = item.row.title
        source = "Job"
    if item.source_view is not None:
        source = item.source_view.name
    return company, role, source


def serialize_work_item(
    item: WorkItem,
    override: WorkItemOverride | None = None,
) -> dict[str, Any]:
    company, role, source = _manual_source_fields(item)
    return {
        "action_key": manual_action_key(item.id),
        "type": "manual",
        "id": item.id,
        "description": item.description,
        "due_at": canonical_utc_timestamp(item.due_at) if item.due_at else None,
        "priority": int(item.priority or 0),
        "version": int(item.version),
        "snooze_version": int(override.version) if override else 1,
        "snoozed_until": (
            canonical_utc_timestamp(override.snoozed_until) if override else None
        ),
        "track_id": item.track_id,
        "row_id": item.row_id,
        "source_view_id": item.source_view_id,
        "origin_label": source,
        "company": company,
        "role": role,
    }


def _serialize_followup(
    track: JobTrack,
    override: WorkItemOverride | None,
) -> dict[str, Any]:
    return {
        "action_key": followup_action_key(track.id, track.follow_up_at),
        "type": "followup",
        "id": track.id,
        "description": (
            f"Follow up with {track.company or 'company'} "
            f"about {track.title or 'role'}"
        ),
        "due_at": canonical_utc_timestamp(track.follow_up_at),
        "priority": 1,
        "version": 1,
        "snooze_version": int(override.version) if override else 1,
        "snoozed_until": (
            canonical_utc_timestamp(override.snoozed_until) if override else None
        ),
        "track_id": track.id,
        "row_id": track.csv_row_id,
        "source_view_id": None,
        "origin_label": "Follow-up",
        "company": track.company,
        "role": track.title,
    }


def _visible_after_snooze(
    item: dict[str, Any],
    *,
    as_of: datetime,
    include_snoozed: bool,
) -> bool:
    if include_snoozed or not item.get("snoozed_until"):
        return True
    return _parse_iso_utc(item["snoozed_until"]) <= as_of


def _counts(
    items: list[dict[str, Any]],
    *,
    day_start: datetime,
    day_end: datetime,
) -> dict[str, int]:
    start = _aware_utc(day_start)
    end = _aware_utc(day_end)
    result = {"total": len(items), "overdue": 0, "due_today": 0, "undated": 0}
    for item in items:
        due_text = item.get("due_at")
        if due_text is None:
            result["undated"] += 1
            continue
        due = _parse_iso_utc(due_text)
        if due < start:
            result["overdue"] += 1
        elif due < end:
            result["due_today"] += 1
    return result


def build_today_queue(
    db: Session,
    *,
    user_id: int,
    timezone_name: str,
    secret_key: str,
    cursor: str | None = None,
    limit: int = 50,
    include_snoozed: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    if limit < 1 or limit > MAX_TODAY_LIMIT:
        raise TodayServiceError(
            "invalid_limit",
            422,
            "Today limit must be between 1 and 100.",
        )

    if cursor:
        as_of, last_key = _decode_cursor(secret_key, cursor)
    else:
        as_of = _aware_utc(now or utc_now())
        last_key = None

    day_start_naive, day_end_naive = local_day_utc_bounds(
        timezone_name,
        reference=as_of,
    )
    day_start = day_start_naive.replace(tzinfo=timezone.utc)
    day_end = day_end_naive.replace(tzinfo=timezone.utc)

    manual_items = (
        db.query(WorkItem)
        .filter(
            WorkItem.user_id == user_id,
            WorkItem.state == "pending",
            or_(WorkItem.due_at.is_(None), WorkItem.due_at < day_end_naive),
        )
        .all()
    )
    followups = (
        db.query(JobTrack)
        .filter(
            JobTrack.user_id == user_id,
            JobTrack.follow_up_at.isnot(None),
            JobTrack.follow_up_at < day_end_naive,
            ~JobTrack.status.in_(TERMINAL_FOLLOWUP_STATUSES),
        )
        .all()
    )

    keys = [manual_action_key(item.id) for item in manual_items]
    keys.extend(
        followup_action_key(track.id, track.follow_up_at)
        for track in followups
    )
    overrides: dict[str, WorkItemOverride] = {}
    if keys:
        overrides = {
            row.action_key: row
            for row in db.query(WorkItemOverride)
            .filter(
                WorkItemOverride.user_id == user_id,
                WorkItemOverride.action_key.in_(keys),
            )
            .all()
        }

    items = [
        serialize_work_item(item, overrides.get(manual_action_key(item.id)))
        for item in manual_items
    ]
    items.extend(
        _serialize_followup(
            track,
            overrides.get(followup_action_key(track.id, track.follow_up_at)),
        )
        for track in followups
    )
    items = [
        item
        for item in items
        if _visible_after_snooze(
            item,
            as_of=as_of,
            include_snoozed=include_snoozed,
        )
    ]
    items.sort(key=_item_sort_key)

    counts = _counts(items, day_start=day_start, day_end=day_end)
    if last_key is not None:
        items = [item for item in items if _item_sort_key(item) > last_key]

    page = items[:limit]
    next_cursor = None
    if len(items) > limit and page:
        next_cursor = _encode_cursor(
            secret_key,
            as_of=as_of,
            item=page[-1],
        )

    return {
        "items": page,
        "next_cursor": next_cursor,
        "as_of": canonical_utc_timestamp(as_of),
        "timezone": timezone_name,
        "counts": counts,
    }


def create_work_item(
    db: Session,
    *,
    user_id: int,
    payload: WorkItemCreate,
) -> WorkItem:
    validate_owned_work_item_sources(
        db,
        user_id,
        track_id=payload.track_id,
        row_id=payload.row_id,
        source_view_id=payload.source_view_id,
    )
    item = WorkItem(
        user_id=user_id,
        description=payload.description,
        due_at=payload.due_at,
        priority=payload.priority,
        track_id=payload.track_id,
        row_id=payload.row_id,
        source_view_id=payload.source_view_id,
        state="pending",
        version=1,
    )
    db.add(item)
    db.flush()
    return item


def update_work_item(
    db: Session,
    *,
    user_id: int,
    item_id: int,
    version: int,
    changes: dict[str, Any],
    now: datetime | None = None,
) -> WorkItem:
    existing = (
        db.query(WorkItem)
        .filter_by(id=item_id, user_id=user_id)
        .first()
    )
    if existing is None:
        raise TodayServiceError(
            "work_item_not_found",
            404,
            "Work item was not found.",
        )
    if not changes:
        raise TodayServiceError(
            "empty_patch",
            422,
            "At least one work-item field must change.",
        )

    values = dict(changes)
    target_state = values.get("state", existing.state)
    reference = _aware_utc(now or utc_now())
    if target_state not in {"pending", "done"}:
        raise TodayServiceError(
            "invalid_state",
            422,
            "Work item state must be pending or done.",
        )
    if "state" in values:
        values["completed_at"] = (
            reference if target_state == "done" else None
        )
    values["updated_at"] = reference
    values["version"] = int(version) + 1

    updated = (
        db.query(WorkItem)
        .filter(
            WorkItem.id == item_id,
            WorkItem.user_id == user_id,
            WorkItem.version == version,
        )
        .update(values, synchronize_session=False)
    )
    if updated != 1:
        db.expire_all()
        if (
            db.query(WorkItem.id)
            .filter_by(id=item_id, user_id=user_id)
            .first()
            is None
        ):
            raise TodayServiceError(
                "work_item_not_found",
                404,
                "Work item was not found.",
            )
        raise TodayServiceError(
            "stale_version",
            409,
            "Work item changed. Reload and retry.",
        )
    db.flush()
    db.expire_all()
    return (
        db.query(WorkItem)
        .filter_by(id=item_id, user_id=user_id)
        .one()
    )


def snooze_action(
    db: Session,
    *,
    user_id: int,
    action_key: str,
    until: datetime,
    version: int,
    now: datetime | None = None,
) -> WorkItemOverride:
    reference = _aware_utc(now or utc_now())
    until_utc = _aware_utc(until)
    if (
        until_utc <= reference
        or until_utc > reference + timedelta(days=MAX_SNOOZE_DAYS)
    ):
        raise TodayServiceError(
            "invalid_snooze_until",
            422,
            "Snooze time must be in the future and no more than 365 days away.",
        )

    kind, source = validate_owned_action_key(
        db,
        user_id,
        action_key,
    )
    if kind == "manual" and source.state != "pending":
        raise TodayServiceError(
            "action_not_available",
            409,
            "Today action is no longer pending.",
        )
    if (
        kind == "followup"
        and source.status in TERMINAL_FOLLOWUP_STATUSES
    ):
        raise TodayServiceError(
            "action_not_available",
            409,
            "Follow-up is no longer actionable.",
        )

    existing = (
        db.query(WorkItemOverride)
        .filter_by(user_id=user_id, action_key=action_key)
        .first()
    )
    if existing is None:
        if version != 1:
            raise TodayServiceError(
                "stale_version",
                409,
                "Today action changed. Reload and retry.",
            )
        row = WorkItemOverride(
            user_id=user_id,
            action_key=action_key,
            snoozed_until=until_utc,
            version=2,
        )
        db.add(row)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise TodayServiceError(
                "stale_version",
                409,
                "Today action changed. Reload and retry.",
            ) from exc
        return row

    updated = (
        db.query(WorkItemOverride)
        .filter(
            WorkItemOverride.user_id == user_id,
            WorkItemOverride.action_key == action_key,
            WorkItemOverride.version == version,
        )
        .update(
            {
                "snoozed_until": until_utc,
                "version": int(version) + 1,
            },
            synchronize_session=False,
        )
    )
    if updated != 1:
        db.expire_all()
        raise TodayServiceError(
            "stale_version",
            409,
            "Today action changed. Reload and retry.",
        )
    db.flush()
    db.expire_all()
    return (
        db.query(WorkItemOverride)
        .filter_by(user_id=user_id, action_key=action_key)
        .one()
    )


def resolve_followup(
    db: Session,
    *,
    user_id: int,
    action_key: str,
    resolution: Literal["clear", "reschedule"],
    follow_up_at: datetime | None,
    operation_id: UUID,
    now: datetime | None = None,
) -> JobTrack:
    kind, source = validate_owned_action_key(
        db,
        user_id,
        action_key,
    )
    if kind != "followup":
        raise TodayServiceError(
            "invalid_action_type",
            422,
            "Only follow-up actions can use this operation.",
        )
    track = source
    if track.status in TERMINAL_FOLLOWUP_STATUSES:
        raise TodayServiceError(
            "action_not_available",
            409,
            "Follow-up is no longer actionable.",
        )
    if resolution == "clear":
        target = None
    elif resolution == "reschedule":
        if follow_up_at is None:
            raise TodayServiceError(
                "follow_up_at_required",
                422,
                "follow_up_at is required when rescheduling.",
            )
        target = _naive_utc(follow_up_at)
    else:
        raise TodayServiceError(
            "invalid_resolution",
            422,
            "Resolution must be clear or reschedule.",
        )

    apply_job_track_changes(
        db,
        user_id=user_id,
        item=track,
        source="today_queue",
        operation_id=operation_id,
        now=_aware_utc(now or utc_now()),
        follow_up_at=target,
        infer_applied_at_from_status=False,
    )
    db.flush()
    return track


def _row_query_from_saved_view(view: SavedView) -> RowQuery:
    if view.view_type != "job_links":
        raise TodayServiceError(
            "unsupported_view_type",
            422,
            "Only job-link saved views can create Today actions in this release.",
        )
    filters = view.filters or {}
    if not isinstance(filters, dict):
        raise TodayServiceError(
            "invalid_view_filters",
            422,
            "Saved view filters are invalid.",
        )
    allowed = {field.name for field in fields(RowQuery)}
    unknown = set(filters) - allowed
    if unknown:
        raise TodayServiceError(
            "invalid_view_filters",
            422,
            "Saved view filters are invalid.",
        )
    try:
        return RowQuery(**filters)
    except (TypeError, ValueError) as exc:
        raise TodayServiceError(
            "invalid_view_filters",
            422,
            "Saved view filters are invalid.",
        ) from exc


def _from_view_description(row: CsvRow) -> str:
    title = (row.title or "job").strip()
    company = (row.company_guess or "company").strip()
    return f"Review {title} at {company}"[:500].strip()


def create_from_view(
    db: Session,
    *,
    user_id: int,
    view_id: int,
    limit: int,
    request_id: UUID,
) -> dict[str, Any]:
    del request_id
    if limit < 1 or limit > MAX_FROM_VIEW_LIMIT:
        raise TodayServiceError(
            "invalid_limit",
            422,
            "from-view limit must be between 1 and 20.",
        )
    view = (
        db.query(SavedView)
        .filter_by(id=view_id, user_id=user_id)
        .first()
    )
    if view is None:
        raise TodayServiceError(
            "view_not_found",
            404,
            "Saved view was not found.",
        )

    params = _row_query_from_saved_view(view)
    rows = (
        order_row_query(
            build_row_query(db, user_id, params),
            params,
        )
        .limit(limit)
        .all()
    )
    if not rows:
        return {
            "items": [],
            "created": 0,
            "existing": 0,
            "completed": 0,
            "matched": 0,
        }

    origin_by_row = {
        row.id: f"view:{view.id}:row:{row.id}"
        for row in rows
    }
    existing_items = {
        item.origin_key: item
        for item in db.query(WorkItem)
        .filter(
            WorkItem.user_id == user_id,
            WorkItem.origin_key.in_(list(origin_by_row.values())),
        )
        .all()
    }

    result_items: list[WorkItem] = []
    created = existing = completed = 0
    for row in rows:
        origin_key = origin_by_row[row.id]
        current = existing_items.get(origin_key)
        if current is not None:
            if current.state == "pending":
                existing += 1
                result_items.append(current)
            else:
                completed += 1
            continue
        item = WorkItem(
            user_id=user_id,
            row_id=row.id,
            source_view_id=view.id,
            origin_key=origin_key,
            description=_from_view_description(row),
            priority=1,
            state="pending",
            version=1,
        )
        db.add(item)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            raise TodayServiceError(
                "origin_conflict",
                409,
                (
                    "A Today action for this saved-view row already changed. "
                    "Reload and retry."
                ),
            ) from exc
        created += 1
        result_items.append(item)

    return {
        "items": result_items,
        "created": created,
        "existing": existing,
        "completed": completed,
        "matched": len(rows),
    }
