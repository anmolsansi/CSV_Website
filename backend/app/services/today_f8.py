from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload

from ..availability_schemas import deadline_action_key
from ..contact_models import Interview
from ..models import CsvRow, JobAvailability, JobTrack, WorkItem, WorkItemOverride
from ..today_schemas import (
    canonical_utc_timestamp,
    followup_action_key,
    manual_action_key,
)
from .lifecycle import local_day_utc_bounds
from .today import (
    MAX_TODAY_LIMIT,
    TERMINAL_FOLLOWUP_STATUSES,
    TodayServiceError,
    _counts,
    _item_sort_key,
    _serialize_deadline,
    _serialize_followup,
    _visible_after_snooze,
    serialize_work_item,
    snooze_action as snooze_base_action,
)


MAX_SNOOZE_DAYS = 365
MIXED_TODAY_CURSOR_SALT = "jobgrid-today-mixed-cursor-v2"
MIXED_TODAY_CURSOR_VERSION = 2


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_iso_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise TodayServiceError(
            "invalid_cursor",
            422,
            "Today changed. Refresh and retry.",
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TodayServiceError(
            "invalid_cursor",
            422,
            "Today changed. Refresh and retry.",
        )
    return parsed.astimezone(timezone.utc)


def _mixed_cursor_serializer(secret_key: str) -> URLSafeSerializer:
    return URLSafeSerializer(secret_key, salt=MIXED_TODAY_CURSOR_SALT)


def _encode_mixed_cursor(
    secret_key: str,
    *,
    as_of: datetime,
    item: dict[str, Any],
    user_id: int,
    timezone_name: str,
    include_snoozed: bool,
) -> str:
    payload = {
        "v": MIXED_TODAY_CURSOR_VERSION,
        "as_of": canonical_utc_timestamp(as_of),
        "last": list(_item_sort_key(item)),
        "user_id": int(user_id),
        "timezone": timezone_name,
        "include_snoozed": bool(include_snoozed),
    }
    return _mixed_cursor_serializer(secret_key).dumps(payload)


def _decode_mixed_cursor(
    secret_key: str,
    cursor: str,
    *,
    user_id: int,
    timezone_name: str,
    include_snoozed: bool,
) -> tuple[datetime, tuple[int, str, int, str, int]]:
    try:
        payload = _mixed_cursor_serializer(secret_key).loads(cursor)
    except BadSignature as exc:
        raise TodayServiceError(
            "invalid_cursor",
            422,
            "Today changed. Refresh and retry.",
        ) from exc

    if not isinstance(payload, dict) or payload.get("v") != MIXED_TODAY_CURSOR_VERSION:
        raise TodayServiceError(
            "invalid_cursor",
            422,
            "Today changed. Refresh and retry.",
        )
    if (
        payload.get("user_id") != int(user_id)
        or payload.get("timezone") != timezone_name
        or payload.get("include_snoozed") is not bool(include_snoozed)
    ):
        raise TodayServiceError(
            "cursor_context_changed",
            409,
            "Today filters changed. Refresh and retry.",
        )

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
        raise TodayServiceError(
            "invalid_cursor",
            422,
            "Today changed. Refresh and retry.",
        )
    return _parse_iso_utc(payload.get("as_of")), tuple(last)


def interview_action_key(interview_id: int, starts_at: datetime) -> str:
    instant = _aware_utc(starts_at).isoformat().replace("+00:00", "Z")
    return f"interview:{interview_id}:{instant}"


def _parse_interview_action_key(action_key: str) -> tuple[int, str] | None:
    if not action_key.startswith("interview:"):
        return None
    parts = action_key.split(":", 2)
    if len(parts) != 3 or not parts[1].isdigit() or not parts[2]:
        return None
    return int(parts[1]), parts[2]


def _interview_item(
    interview: Interview,
    track: JobTrack,
    override: WorkItemOverride | None,
) -> dict[str, Any]:
    action_key = interview_action_key(interview.id, interview.starts_at)
    label = interview.round_label or interview.kind.title()
    return {
        "action_key": action_key,
        "type": "interview",
        "id": interview.id,
        "description": (
            f"Prepare for {label} interview with {track.company or 'company'}"
            + (f" — {track.title}" if track.title else "")
        ),
        "due_at": canonical_utc_timestamp(interview.starts_at),
        "priority": 3,
        "version": int(interview.version),
        "snooze_version": int(override.version) if override else 1,
        "snoozed_until": (
            canonical_utc_timestamp(override.snoozed_until) if override else None
        ),
        "track_id": track.id,
        "row_id": track.csv_row_id,
        "source_view_id": None,
        "origin_label": "Interview preparation",
        "company": track.company,
        "role": track.title,
        "interview_timezone": interview.timezone,
        "round_label": interview.round_label,
    }


def build_today_queue_with_interviews(
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
    """Build one ordered Today population, then paginate it exactly once.

    The previous F8 wrapper paginated manual/follow-up/deadline items first and
    merged interviews afterward. That could strand displaced base items or omit
    the cursor for interview-only queues. This implementation applies one
    ordering tuple, one frozen as_of value, one snooze policy, and one cursor
    boundary across every source before the page is emitted.

    Pagination is best-effort across mutations. `as_of` and query context are
    frozen by the signed cursor, but mutable rows are not snapshot-stored. A
    refresh is the recovery path when the queue changes between page requests.
    """
    if limit < 1 or limit > MAX_TODAY_LIMIT:
        raise TodayServiceError(
            "invalid_limit",
            422,
            "Today limit must be between 1 and 100.",
        )

    if cursor:
        as_of, last_key = _decode_mixed_cursor(
            secret_key,
            cursor,
            user_id=user_id,
            timezone_name=timezone_name,
            include_snoozed=include_snoozed,
        )
    else:
        as_of = _aware_utc(now or datetime.now(timezone.utc))
        last_key = None

    day_start_naive, day_end_naive = local_day_utc_bounds(
        timezone_name,
        reference=as_of,
    )
    day_start = day_start_naive.replace(tzinfo=timezone.utc)
    day_end = day_end_naive.replace(tzinfo=timezone.utc)

    manual_items = (
        db.query(WorkItem)
        .options(
            joinedload(WorkItem.track),
            joinedload(WorkItem.row),
            joinedload(WorkItem.source_view),
        )
        .filter(
            WorkItem.user_id == user_id,
            WorkItem.state == "pending",
            or_(WorkItem.due_at.is_(None), WorkItem.due_at < day_end),
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

    first_row_per_url = (
        db.query(
            CsvRow.user_id.label("user_id"),
            CsvRow.url.label("url"),
            func.min(CsvRow.id).label("row_id"),
        )
        .filter(CsvRow.user_id == user_id)
        .group_by(CsvRow.user_id, CsvRow.url)
        .subquery()
    )
    deadline_contexts = (
        db.query(JobAvailability, JobTrack, CsvRow)
        .outerjoin(
            JobTrack,
            and_(
                JobTrack.user_id == JobAvailability.user_id,
                JobTrack.url == JobAvailability.job_url,
            ),
        )
        .outerjoin(
            first_row_per_url,
            and_(
                first_row_per_url.c.user_id == JobAvailability.user_id,
                first_row_per_url.c.url == JobAvailability.job_url,
            ),
        )
        .outerjoin(CsvRow, CsvRow.id == first_row_per_url.c.row_id)
        .filter(
            JobAvailability.user_id == user_id,
            JobAvailability.deadline_at.isnot(None),
            JobAvailability.deadline_at < day_end_naive,
            JobAvailability.state != "closed",
        )
        .all()
    )
    deadlines = [
        (availability, track, row)
        for availability, track, row in deadline_contexts
        if track is None or track.status not in TERMINAL_FOLLOWUP_STATUSES
    ]
    interviews = (
        db.query(Interview, JobTrack)
        .join(JobTrack, JobTrack.id == Interview.track_id)
        .filter(
            Interview.user_id == user_id,
            JobTrack.user_id == user_id,
            Interview.status == "scheduled",
            Interview.starts_at > as_of.replace(tzinfo=None),
            Interview.starts_at < day_end_naive,
        )
        .all()
    )

    keys = [manual_action_key(item.id) for item in manual_items]
    keys.extend(
        followup_action_key(track.id, track.follow_up_at)
        for track in followups
    )
    keys.extend(
        deadline_action_key(availability.id, availability.deadline_at)
        for availability, _track, _row in deadlines
    )
    keys.extend(
        interview_action_key(interview.id, interview.starts_at)
        for interview, _track in interviews
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
    items.extend(
        _serialize_deadline(
            availability,
            track,
            row,
            overrides.get(deadline_action_key(availability.id, availability.deadline_at)),
        )
        for availability, track, row in deadlines
    )
    items.extend(
        _interview_item(
            interview,
            track,
            overrides.get(interview_action_key(interview.id, interview.starts_at)),
        )
        for interview, track in interviews
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

    page_plus_one = items[: limit + 1]
    page = page_plus_one[:limit]
    next_cursor = None
    if len(page_plus_one) > limit and page:
        next_cursor = _encode_mixed_cursor(
            secret_key,
            as_of=as_of,
            item=page[-1],
            user_id=user_id,
            timezone_name=timezone_name,
            include_snoozed=include_snoozed,
        )

    return {
        "items": page,
        "next_cursor": next_cursor,
        "as_of": canonical_utc_timestamp(as_of),
        "timezone": timezone_name,
        "counts": counts,
    }


def snooze_action_with_interviews(
    db: Session,
    *,
    user_id: int,
    action_key: str,
    until: datetime,
    version: int,
    now: datetime | None = None,
) -> WorkItemOverride:
    parsed = _parse_interview_action_key(action_key)
    if parsed is None:
        return snooze_base_action(
            db,
            user_id=user_id,
            action_key=action_key,
            until=until,
            version=version,
            now=now,
        )

    interview_id, _encoded_start = parsed
    interview = (
        db.query(Interview)
        .filter(Interview.id == interview_id, Interview.user_id == user_id)
        .first()
    )
    if (
        interview is None
        or interview.status != "scheduled"
        or interview_action_key(interview.id, interview.starts_at) != action_key
    ):
        raise TodayServiceError(
            "action_not_available",
            409,
            "Interview preparation is no longer actionable.",
        )

    reference = _aware_utc(now or datetime.now(timezone.utc))
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
        db.flush()
        return row
    if existing.version != version:
        raise TodayServiceError(
            "stale_version",
            409,
            "Today action changed. Reload and retry.",
        )
    existing.snoozed_until = until_utc
    existing.version += 1
    db.flush()
    return existing
