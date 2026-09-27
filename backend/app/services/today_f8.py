from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy import and_, case, false, func, or_, true
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


def _naive_utc(value: datetime) -> datetime:
    return _aware_utc(value).replace(tzinfo=None)


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
        or payload.get("include_snoozed") != bool(include_snoozed)
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
    if last[0] not in {0, 1}:
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


def _action_id(action_key: str, prefix: str) -> int | None:
    marker = f"{prefix}:"
    if not action_key.startswith(marker):
        return None
    raw_id = action_key[len(marker) :].split(":", 1)[0]
    if not raw_id.isdigit() or int(raw_id) <= 0:
        return None
    return int(raw_id)


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


def _constant_suffix_after(
    *,
    priority: int,
    source_type: str,
    id_column,
    last_key: tuple[int, str, int, str, int],
):
    _last_null, _last_due, last_neg_priority, last_type, last_id = last_key
    neg_priority = -int(priority)
    if neg_priority > last_neg_priority:
        return true()
    if neg_priority < last_neg_priority:
        return false()
    if source_type > last_type:
        return true()
    if source_type < last_type:
        return false()
    return id_column > last_id


def _manual_suffix_after(
    *,
    id_column,
    priority_column,
    last_key: tuple[int, str, int, str, int],
):
    _last_null, _last_due, last_neg_priority, last_type, last_id = last_key
    last_priority = -last_neg_priority
    if "manual" > last_type:
        same_priority_after = true()
    elif "manual" < last_type:
        same_priority_after = false()
    else:
        same_priority_after = id_column > last_id
    return or_(
        priority_column < last_priority,
        and_(priority_column == last_priority, same_priority_after),
    )


def _after_cursor_filter(
    *,
    due_column,
    id_column,
    source_type: str,
    last_key: tuple[int, str, int, str, int] | None,
    priority: int | None = None,
    priority_column=None,
    nullable_due: bool = False,
):
    if last_key is None:
        return true()

    last_null, last_due, _last_neg_priority, _last_type, _last_id = last_key
    suffix = (
        _manual_suffix_after(
            id_column=id_column,
            priority_column=priority_column,
            last_key=last_key,
        )
        if priority_column is not None
        else _constant_suffix_after(
            priority=int(priority or 0),
            source_type=source_type,
            id_column=id_column,
            last_key=last_key,
        )
    )

    if last_null == 1:
        if not nullable_due:
            return false()
        return and_(due_column.is_(None), suffix)

    last_due_at = _naive_utc(_parse_iso_utc(last_due))
    dated_after = or_(
        due_column > last_due_at,
        and_(due_column == last_due_at, suffix),
    )
    if nullable_due:
        return or_(due_column.is_(None), dated_after)
    return dated_after


def _aggregate_counts(query) -> tuple[int, int, int, int]:
    row = query.one()
    return tuple(int(value or 0) for value in row)


def _eligible_counts(
    db: Session,
    *,
    user_id: int,
    as_of: datetime,
    day_start_naive: datetime,
    day_end_naive: datetime,
) -> dict[str, int]:
    manual = _aggregate_counts(
        db.query(
            func.count(WorkItem.id),
            func.sum(case((WorkItem.due_at < day_start_naive, 1), else_=0)),
            func.sum(
                case(
                    (
                        and_(
                            WorkItem.due_at.isnot(None),
                            WorkItem.due_at >= day_start_naive,
                            WorkItem.due_at < day_end_naive,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ),
            func.sum(case((WorkItem.due_at.is_(None), 1), else_=0)),
        ).filter(
            WorkItem.user_id == user_id,
            WorkItem.state == "pending",
            or_(WorkItem.due_at.is_(None), WorkItem.due_at < day_end_naive),
        )
    )
    followup = _aggregate_counts(
        db.query(
            func.count(JobTrack.id),
            func.sum(case((JobTrack.follow_up_at < day_start_naive, 1), else_=0)),
            func.sum(
                case(
                    (
                        and_(
                            JobTrack.follow_up_at >= day_start_naive,
                            JobTrack.follow_up_at < day_end_naive,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ),
            func.sum(case((false(), 1), else_=0)),
        ).filter(
            JobTrack.user_id == user_id,
            JobTrack.follow_up_at.isnot(None),
            JobTrack.follow_up_at < day_end_naive,
            ~JobTrack.status.in_(TERMINAL_FOLLOWUP_STATUSES),
        )
    )
    deadline = _aggregate_counts(
        db.query(
            func.count(JobAvailability.id),
            func.sum(case((JobAvailability.deadline_at < day_start_naive, 1), else_=0)),
            func.sum(
                case(
                    (
                        and_(
                            JobAvailability.deadline_at >= day_start_naive,
                            JobAvailability.deadline_at < day_end_naive,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ),
            func.sum(case((false(), 1), else_=0)),
        )
        .outerjoin(
            JobTrack,
            and_(
                JobTrack.user_id == JobAvailability.user_id,
                JobTrack.url == JobAvailability.job_url,
            ),
        )
        .filter(
            JobAvailability.user_id == user_id,
            JobAvailability.deadline_at.isnot(None),
            JobAvailability.deadline_at < day_end_naive,
            JobAvailability.state != "closed",
            or_(
                JobTrack.id.is_(None),
                ~JobTrack.status.in_(TERMINAL_FOLLOWUP_STATUSES),
            ),
        )
    )
    interview_total = int(
        db.query(func.count(Interview.id))
        .join(JobTrack, JobTrack.id == Interview.track_id)
        .filter(
            Interview.user_id == user_id,
            JobTrack.user_id == user_id,
            Interview.status == "scheduled",
            Interview.starts_at > _naive_utc(as_of),
            Interview.starts_at < day_end_naive,
        )
        .scalar()
        or 0
    )

    return {
        "total": manual[0] + followup[0] + deadline[0] + interview_total,
        "overdue": manual[1] + followup[1] + deadline[1],
        "due_today": manual[2] + followup[2] + deadline[2] + interview_total,
        "undated": manual[3],
    }


def _decrement_counts_for_due(
    counts: dict[str, int],
    due_at: datetime | None,
    *,
    day_start: datetime,
    day_end: datetime,
) -> None:
    counts["total"] -= 1
    if due_at is None:
        counts["undated"] -= 1
        return
    due = _aware_utc(due_at)
    if due < day_start:
        counts["overdue"] -= 1
    elif due < day_end:
        counts["due_today"] -= 1


def _active_snooze_overrides(
    db: Session,
    *,
    user_id: int,
    as_of: datetime,
    include_snoozed: bool,
) -> tuple[dict[str, WorkItemOverride], dict[str, WorkItemOverride]]:
    rows = (
        db.query(WorkItemOverride)
        .filter(WorkItemOverride.user_id == user_id)
        .all()
    )
    overrides = {row.action_key: row for row in rows}
    if include_snoozed:
        return overrides, {}
    hidden = {
        row.action_key: row
        for row in rows
        if row.snoozed_until is not None and _aware_utc(row.snoozed_until) > as_of
    }
    return overrides, hidden


def _subtract_hidden_counts(
    db: Session,
    *,
    user_id: int,
    hidden: dict[str, WorkItemOverride],
    counts: dict[str, int],
    as_of: datetime,
    day_start: datetime,
    day_end: datetime,
    day_end_naive: datetime,
) -> None:
    if not hidden:
        return

    manual_ids = {
        item_id
        for key in hidden
        if (item_id := _action_id(key, "manual")) is not None
    }
    followup_ids = {
        item_id
        for key in hidden
        if (item_id := _action_id(key, "followup")) is not None
    }
    deadline_ids = {
        item_id
        for key in hidden
        if (item_id := _action_id(key, "deadline")) is not None
    }
    interview_ids = {
        item_id
        for key in hidden
        if (item_id := _action_id(key, "interview")) is not None
    }

    if manual_ids:
        rows = (
            db.query(WorkItem)
            .filter(
                WorkItem.user_id == user_id,
                WorkItem.id.in_(manual_ids),
                WorkItem.state == "pending",
                or_(WorkItem.due_at.is_(None), WorkItem.due_at < day_end_naive),
            )
            .all()
        )
        for item in rows:
            if manual_action_key(item.id) in hidden:
                _decrement_counts_for_due(
                    counts,
                    item.due_at,
                    day_start=day_start,
                    day_end=day_end,
                )

    if followup_ids:
        rows = (
            db.query(JobTrack)
            .filter(
                JobTrack.user_id == user_id,
                JobTrack.id.in_(followup_ids),
                JobTrack.follow_up_at.isnot(None),
                JobTrack.follow_up_at < day_end_naive,
                ~JobTrack.status.in_(TERMINAL_FOLLOWUP_STATUSES),
            )
            .all()
        )
        for track in rows:
            if followup_action_key(track.id, track.follow_up_at) in hidden:
                _decrement_counts_for_due(
                    counts,
                    track.follow_up_at,
                    day_start=day_start,
                    day_end=day_end,
                )

    if deadline_ids:
        rows = (
            db.query(JobAvailability, JobTrack)
            .outerjoin(
                JobTrack,
                and_(
                    JobTrack.user_id == JobAvailability.user_id,
                    JobTrack.url == JobAvailability.job_url,
                ),
            )
            .filter(
                JobAvailability.user_id == user_id,
                JobAvailability.id.in_(deadline_ids),
                JobAvailability.deadline_at.isnot(None),
                JobAvailability.deadline_at < day_end_naive,
                JobAvailability.state != "closed",
                or_(
                    JobTrack.id.is_(None),
                    ~JobTrack.status.in_(TERMINAL_FOLLOWUP_STATUSES),
                ),
            )
            .all()
        )
        for availability, _track in rows:
            if deadline_action_key(availability.id, availability.deadline_at) in hidden:
                _decrement_counts_for_due(
                    counts,
                    availability.deadline_at,
                    day_start=day_start,
                    day_end=day_end,
                )

    if interview_ids:
        rows = (
            db.query(Interview)
            .join(JobTrack, JobTrack.id == Interview.track_id)
            .filter(
                Interview.user_id == user_id,
                JobTrack.user_id == user_id,
                Interview.id.in_(interview_ids),
                Interview.status == "scheduled",
                Interview.starts_at > _naive_utc(as_of),
                Interview.starts_at < day_end_naive,
            )
            .all()
        )
        for interview in rows:
            if interview_action_key(interview.id, interview.starts_at) in hidden:
                _decrement_counts_for_due(
                    counts,
                    interview.starts_at,
                    day_start=day_start,
                    day_end=day_end,
                )


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
    """Build one ordered mixed-source Today page with a shared cursor boundary.

    `as_of` and query context are frozen in the signed cursor, but mutable rows
    are not snapshot-stored. Pagination is therefore stable for unchanged data
    and best-effort across mutations; refresh is the recovery path after change.
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

    overrides, hidden_overrides = _active_snooze_overrides(
        db,
        user_id=user_id,
        as_of=as_of,
        include_snoozed=include_snoozed,
    )
    # At most every active hidden override can occupy a position before the
    # requested visible window. Adding that bounded allowance guarantees that
    # each source can still contribute limit+1 visible candidates without
    # loading its full account history.
    candidate_limit = limit + 1 + len(hidden_overrides)

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
            _after_cursor_filter(
                due_column=WorkItem.due_at,
                id_column=WorkItem.id,
                source_type="manual",
                last_key=last_key,
                priority_column=WorkItem.priority,
                nullable_due=True,
            ),
        )
        .order_by(
            case((WorkItem.due_at.is_(None), 1), else_=0).asc(),
            WorkItem.due_at.asc(),
            WorkItem.priority.desc(),
            WorkItem.id.asc(),
        )
        .limit(candidate_limit)
        .all()
    )
    followups = (
        db.query(JobTrack)
        .filter(
            JobTrack.user_id == user_id,
            JobTrack.follow_up_at.isnot(None),
            JobTrack.follow_up_at < day_end_naive,
            ~JobTrack.status.in_(TERMINAL_FOLLOWUP_STATUSES),
            _after_cursor_filter(
                due_column=JobTrack.follow_up_at,
                id_column=JobTrack.id,
                source_type="followup",
                last_key=last_key,
                priority=1,
            ),
        )
        .order_by(JobTrack.follow_up_at.asc(), JobTrack.id.asc())
        .limit(candidate_limit)
        .all()
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
            or_(
                JobTrack.id.is_(None),
                ~JobTrack.status.in_(TERMINAL_FOLLOWUP_STATUSES),
            ),
            _after_cursor_filter(
                due_column=JobAvailability.deadline_at,
                id_column=JobAvailability.id,
                source_type="deadline",
                last_key=last_key,
                priority=2,
            ),
        )
        .order_by(JobAvailability.deadline_at.asc(), JobAvailability.id.asc())
        .limit(candidate_limit)
        .all()
    )
    interviews = (
        db.query(Interview, JobTrack)
        .join(JobTrack, JobTrack.id == Interview.track_id)
        .filter(
            Interview.user_id == user_id,
            JobTrack.user_id == user_id,
            Interview.status == "scheduled",
            Interview.starts_at > _naive_utc(as_of),
            Interview.starts_at < day_end_naive,
            _after_cursor_filter(
                due_column=Interview.starts_at,
                id_column=Interview.id,
                source_type="interview",
                last_key=last_key,
                priority=3,
            ),
        )
        .order_by(Interview.starts_at.asc(), Interview.id.asc())
        .limit(candidate_limit)
        .all()
    )

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
        for availability, track, row in deadline_contexts
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

    counts = _eligible_counts(
        db,
        user_id=user_id,
        as_of=as_of,
        day_start_naive=day_start_naive,
        day_end_naive=day_end_naive,
    )
    if hidden_overrides:
        _subtract_hidden_counts(
            db,
            user_id=user_id,
            hidden=hidden_overrides,
            counts=counts,
            as_of=as_of,
            day_start=day_start,
            day_end=day_end,
            day_end_naive=day_end_naive,
        )

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
