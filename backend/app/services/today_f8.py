from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from ..contact_models import Interview
from ..models import JobTrack, WorkItemOverride
from ..today_schemas import canonical_utc_timestamp
from .lifecycle import local_day_utc_bounds
from .today import (
    TodayServiceError,
    _decode_cursor,
    _encode_cursor,
    _item_sort_key,
    build_today_queue as build_base_today_queue,
    snooze_action as snooze_base_action,
)


MAX_SNOOZE_DAYS = 365


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


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


def _interview_item(interview: Interview, track: JobTrack, override: WorkItemOverride | None) -> dict[str, Any]:
    action_key = interview_action_key(interview.id, interview.starts_at)
    label = interview.round_label or interview.kind.title()
    return {
        "action_key": action_key,
        "type": "interview",
        "id": interview.id,
        "description": f"Prepare for {label} interview with {track.company or 'company'}" + (f" — {track.title}" if track.title else ""),
        "due_at": canonical_utc_timestamp(interview.starts_at),
        "priority": 3,
        "version": int(interview.version),
        "snooze_version": int(override.version) if override else 1,
        "snoozed_until": canonical_utc_timestamp(override.snoozed_until) if override else None,
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
    result = build_base_today_queue(
        db,
        user_id=user_id,
        timezone_name=timezone_name,
        secret_key=secret_key,
        cursor=cursor,
        limit=limit,
        include_snoozed=include_snoozed,
        now=now,
    )

    # The base queue owns cursor validation and freezes `as_of` on continuation
    # pages. Reuse that exact instant for interview eligibility so all sources
    # share the same account-local day boundary across pagination.
    as_of = _aware_utc(
        datetime.fromisoformat(str(result["as_of"]).replace("Z", "+00:00"))
    )
    _, day_end_naive = local_day_utc_bounds(timezone_name, reference=as_of)
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
        .order_by(Interview.starts_at.asc(), Interview.id.asc())
        .all()
    )
    if not interviews:
        return result

    keys = [
        interview_action_key(interview.id, interview.starts_at)
        for interview, _track in interviews
    ]
    overrides = {
        row.action_key: row
        for row in db.query(WorkItemOverride)
        .filter(
            WorkItemOverride.user_id == user_id,
            WorkItemOverride.action_key.in_(keys),
        )
        .all()
    }
    added: list[dict[str, Any]] = []
    for interview, track in interviews:
        item = _interview_item(
            interview,
            track,
            overrides.get(interview_action_key(interview.id, interview.starts_at)),
        )
        if not include_snoozed and item["snoozed_until"]:
            snoozed_until = datetime.fromisoformat(
                item["snoozed_until"].replace("Z", "+00:00")
            )
            if snoozed_until > as_of:
                continue
        added.append(item)

    if not added:
        return result

    # Counts describe the complete eligible population, not only this page.
    result["counts"] = dict(result.get("counts") or {})
    result["counts"]["total"] = int(result["counts"].get("total", 0)) + len(added)
    result["counts"]["due_today"] = int(result["counts"].get("due_today", 0)) + len(added)

    last_key = None
    if cursor:
        _cursor_as_of, last_key = _decode_cursor(secret_key, cursor)
        added = [item for item in added if _item_sort_key(item) > last_key]

    # The base service already returns at most `limit` candidates after the
    # cursor and tells us whether more base candidates exist. Merge those with
    # interview candidates, then page once using the shared ordering tuple. A
    # base item displaced by an interview is recovered on the next request
    # because the next cursor is based on the final mixed-source emitted item.
    base_has_more = bool(result.get("next_cursor"))
    merged = list(result["items"]) + added
    merged.sort(key=_item_sort_key)
    page = merged[:limit]
    has_more = base_has_more or len(merged) > limit

    result["items"] = page
    result["next_cursor"] = (
        _encode_cursor(secret_key, as_of=as_of, item=page[-1])
        if has_more and page
        else None
    )
    return result


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

    interview_id, encoded_start = parsed
    interview = db.query(Interview).filter(Interview.id == interview_id, Interview.user_id == user_id).first()
    if interview is None or interview.status != "scheduled" or interview_action_key(interview.id, interview.starts_at) != action_key:
        raise TodayServiceError("action_not_available", 409, "Interview preparation is no longer actionable.")

    reference = _aware_utc(now or datetime.now(timezone.utc))
    until_utc = _aware_utc(until)
    if until_utc <= reference or until_utc > reference + timedelta(days=MAX_SNOOZE_DAYS):
        raise TodayServiceError("invalid_snooze_until", 422, "Snooze time must be in the future and no more than 365 days away.")

    existing = db.query(WorkItemOverride).filter_by(user_id=user_id, action_key=action_key).first()
    if existing is None:
        if version != 1:
            raise TodayServiceError("stale_version", 409, "Today action changed. Reload and retry.")
        row = WorkItemOverride(user_id=user_id, action_key=action_key, snoozed_until=until_utc, version=2)
        db.add(row)
        db.flush()
        return row
    if existing.version != version:
        raise TodayServiceError("stale_version", 409, "Today action changed. Reload and retry.")
    existing.snoozed_until = until_utc
    existing.version += 1
    db.flush()
    return existing
