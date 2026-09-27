from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.contact_models import Interview
from app.models import JobAvailability, JobTrack, User, WorkItem
from app.services.today import TodayServiceError, _item_sort_key
from app.services.today_f8 import (
    build_today_queue_with_interviews,
    interview_action_key,
    snooze_action_with_interviews,
)
from app.today_schemas import followup_action_key, manual_action_key
from app.availability_schemas import deadline_action_key


SECRET = "c04-test-secret"
NOW = datetime(2026, 9, 23, 8, 0, tzinfo=timezone.utc)


def _user(db_session, *, timezone_name="UTC"):
    user = User(
        email=f"c04-{uuid4()}@example.test",
        timezone=timezone_name,
    )
    db_session.add(user)
    db_session.flush()
    return user


def _track(db_session, user, *, follow_up_at=None):
    track = JobTrack(
        user_id=user.id,
        url=f"https://example.test/jobs/{uuid4()}",
        company="Acme",
        title="Engineer",
        follow_up_at=follow_up_at,
    )
    db_session.add(track)
    db_session.flush()
    return track


def _interview(db_session, user, track, *, starts_at, label):
    interview = Interview(
        user_id=user.id,
        track_id=track.id,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
        timezone=user.timezone,
        kind="video",
        status="scheduled",
        round_label=label,
    )
    db_session.add(interview)
    db_session.flush()
    return interview


def _all_pages(db_session, *, user, limit, include_snoozed=False):
    pages = []
    cursor = None
    seen_cursors = set()
    for _ in range(20):
        page = build_today_queue_with_interviews(
            db_session,
            user_id=user.id,
            timezone_name=user.timezone,
            secret_key=SECRET,
            cursor=cursor,
            limit=limit,
            include_snoozed=include_snoozed,
            now=NOW + timedelta(hours=len(pages)),
        )
        pages.append(page)
        cursor = page["next_cursor"]
        if cursor is None:
            return pages
        assert cursor not in seen_cursors
        seen_cursors.add(cursor)
    pytest.fail("Today cursor did not terminate")


@pytest.mark.parametrize(
    ("count", "limit", "expected_pages"),
    [(0, 2, 1), (1, 2, 1), (2, 2, 1), (3, 2, 2), (7, 2, 4)],
)
def test_interview_only_cardinality_and_cursor_termination(
    db_session,
    count,
    limit,
    expected_pages,
):
    user = _user(db_session)
    track = _track(db_session, user)
    interviews = [
        _interview(
            db_session,
            user,
            track,
            starts_at=datetime(2026, 9, 23, 10 + index, 0),
            label=f"Round {index}",
        )
        for index in range(count)
    ]

    pages = _all_pages(db_session, user=user, limit=limit)
    emitted = [item for page in pages for item in page["items"]]

    assert len(pages) == expected_pages
    assert len(emitted) == count
    assert len({item["action_key"] for item in emitted}) == count
    assert {item["id"] for item in emitted} == {item.id for item in interviews}
    assert all(page["counts"]["total"] == count for page in pages)
    assert all(page["as_of"] == pages[0]["as_of"] for page in pages)


def test_all_today_sources_share_one_order_and_cursor_boundary(db_session):
    user = _user(db_session)
    due = datetime(2026, 9, 23, 16, 0)
    track = _track(db_session, user, follow_up_at=due)

    manual = WorkItem(
        user_id=user.id,
        description="Manual tie",
        due_at=due,
        priority=3,
        state="pending",
        version=1,
    )
    undated = WorkItem(
        user_id=user.id,
        description="Undated last",
        due_at=None,
        priority=3,
        state="pending",
        version=1,
    )
    db_session.add_all([manual, undated])
    db_session.flush()

    deadline = JobAvailability(
        user_id=user.id,
        job_url=track.url,
        state="unknown",
        deadline_at=due,
        version=1,
    )
    db_session.add(deadline)
    db_session.flush()

    interview = _interview(
        db_session,
        user,
        track,
        starts_at=due,
        label="Tie interview",
    )

    pages = _all_pages(db_session, user=user, limit=2)
    emitted = [item for page in pages for item in page["items"]]
    emitted_keys = [item["action_key"] for item in emitted]

    expected_keys = [
        interview_action_key(interview.id, interview.starts_at),
        manual_action_key(manual.id),
        deadline_action_key(deadline.id, deadline.deadline_at),
        followup_action_key(track.id, track.follow_up_at),
        manual_action_key(undated.id),
    ]
    assert emitted_keys == expected_keys
    assert [_item_sort_key(item) for item in emitted] == sorted(
        _item_sort_key(item) for item in emitted
    )
    assert len(set(emitted_keys)) == len(expected_keys)
    assert pages[0]["counts"] == {
        "total": 5,
        "overdue": 0,
        "due_today": 4,
        "undated": 1,
    }
    assert all(page["counts"] == pages[0]["counts"] for page in pages)


def test_snoozed_interview_is_excluded_from_counts_and_pages(db_session):
    user = _user(db_session)
    track = _track(db_session, user)
    first = _interview(
        db_session,
        user,
        track,
        starts_at=datetime(2026, 9, 23, 12, 0),
        label="Hidden",
    )
    second = _interview(
        db_session,
        user,
        track,
        starts_at=datetime(2026, 9, 23, 13, 0),
        label="Visible",
    )
    snooze_action_with_interviews(
        db_session,
        user_id=user.id,
        action_key=interview_action_key(first.id, first.starts_at),
        until=NOW + timedelta(hours=2),
        version=1,
        now=NOW,
    )

    hidden = build_today_queue_with_interviews(
        db_session,
        user_id=user.id,
        timezone_name=user.timezone,
        secret_key=SECRET,
        limit=1,
        now=NOW,
    )
    assert hidden["counts"]["total"] == 1
    assert [item["id"] for item in hidden["items"]] == [second.id]
    assert hidden["next_cursor"] is None

    visible = build_today_queue_with_interviews(
        db_session,
        user_id=user.id,
        timezone_name=user.timezone,
        secret_key=SECRET,
        limit=1,
        include_snoozed=True,
        now=NOW,
    )
    assert visible["counts"]["total"] == 2
    assert visible["next_cursor"] is not None


def test_cursor_rejects_tampering_wrong_account_and_context_changes(db_session):
    user = _user(db_session)
    other = _user(db_session)
    track = _track(db_session, user)
    for hour in (12, 13, 14):
        _interview(
            db_session,
            user,
            track,
            starts_at=datetime(2026, 9, 23, hour, 0),
            label=f"Round {hour}",
        )

    first = build_today_queue_with_interviews(
        db_session,
        user_id=user.id,
        timezone_name="UTC",
        secret_key=SECRET,
        limit=1,
        now=NOW,
    )
    cursor = first["next_cursor"]
    assert cursor

    with pytest.raises(TodayServiceError) as tampered:
        build_today_queue_with_interviews(
            db_session,
            user_id=user.id,
            timezone_name="UTC",
            secret_key=SECRET,
            cursor=cursor + "x",
            limit=1,
        )
    assert tampered.value.code == "invalid_cursor"

    with pytest.raises(TodayServiceError) as wrong_account:
        build_today_queue_with_interviews(
            db_session,
            user_id=other.id,
            timezone_name="UTC",
            secret_key=SECRET,
            cursor=cursor,
            limit=1,
        )
    assert wrong_account.value.code == "cursor_context_changed"

    with pytest.raises(TodayServiceError) as timezone_changed:
        build_today_queue_with_interviews(
            db_session,
            user_id=user.id,
            timezone_name="Asia/Kolkata",
            secret_key=SECRET,
            cursor=cursor,
            limit=1,
        )
    assert timezone_changed.value.code == "cursor_context_changed"

    with pytest.raises(TodayServiceError) as snooze_context_changed:
        build_today_queue_with_interviews(
            db_session,
            user_id=user.id,
            timezone_name="UTC",
            secret_key=SECRET,
            cursor=cursor,
            limit=1,
            include_snoozed=True,
        )
    assert snooze_context_changed.value.code == "cursor_context_changed"


def test_account_local_day_boundary_is_frozen_across_pages(db_session):
    user = _user(db_session, timezone_name="Asia/Kolkata")
    track = _track(db_session, user)
    # 18:29 UTC is 23:59 IST on Sep 23. 18:31 UTC is Sep 24 locally.
    inside = _interview(
        db_session,
        user,
        track,
        starts_at=datetime(2026, 9, 23, 18, 29),
        label="Inside local day",
    )
    _interview(
        db_session,
        user,
        track,
        starts_at=datetime(2026, 9, 23, 18, 31),
        label="Next local day",
    )
    now = datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc)

    page = build_today_queue_with_interviews(
        db_session,
        user_id=user.id,
        timezone_name=user.timezone,
        secret_key=SECRET,
        limit=1,
        now=now,
    )
    assert page["counts"]["total"] == 1
    assert [item["id"] for item in page["items"]] == [inside.id]
    assert page["next_cursor"] is None
