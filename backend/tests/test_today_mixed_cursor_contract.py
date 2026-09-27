from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.contact_models import Interview
from app.models import JobTrack, User, WorkItem
from app.services.today import TodayServiceError, build_today_queue
from app.services.today_f8 import build_today_queue_with_interviews


SECRET = "c04-cursor-contract-secret"
NOW = datetime(2026, 9, 23, 8, 0, tzinfo=timezone.utc)


def _user(db_session):
    user = User(email=f"c04-cursor-{uuid4()}@example.test", timezone="UTC")
    db_session.add(user)
    db_session.flush()
    return user


def test_legacy_v1_today_cursor_requires_refresh(db_session):
    user = _user(db_session)
    for index in range(2):
        db_session.add(
            WorkItem(
                user_id=user.id,
                description=f"Legacy cursor action {index}",
                due_at=NOW + timedelta(hours=index + 1),
                priority=1,
                state="pending",
                version=1,
            )
        )
    db_session.flush()

    legacy_page = build_today_queue(
        db_session,
        user_id=user.id,
        timezone_name="UTC",
        secret_key=SECRET,
        limit=1,
        now=NOW,
    )
    assert legacy_page["next_cursor"]

    with pytest.raises(TodayServiceError) as rejected:
        build_today_queue_with_interviews(
            db_session,
            user_id=user.id,
            timezone_name="UTC",
            secret_key=SECRET,
            cursor=legacy_page["next_cursor"],
            limit=1,
        )
    assert rejected.value.code == "invalid_cursor"
    assert rejected.value.status_code == 422
    assert "Refresh" in str(rejected.value)


def test_mutation_between_pages_uses_current_state_without_duplicate_loop(db_session):
    user = _user(db_session)
    track = JobTrack(
        user_id=user.id,
        url=f"https://example.test/jobs/{uuid4()}",
        company="Acme",
        title="Engineer",
    )
    db_session.add(track)
    db_session.flush()

    interviews = []
    for hour in (12, 13, 14):
        interview = Interview(
            user_id=user.id,
            track_id=track.id,
            starts_at=datetime(2026, 9, 23, hour, 0),
            ends_at=datetime(2026, 9, 23, hour + 1, 0),
            timezone="UTC",
            kind="video",
            status="scheduled",
            round_label=f"Round {hour}",
        )
        db_session.add(interview)
        interviews.append(interview)
    db_session.flush()

    first = build_today_queue_with_interviews(
        db_session,
        user_id=user.id,
        timezone_name="UTC",
        secret_key=SECRET,
        limit=2,
        now=NOW,
    )
    assert len(first["items"]) == 2
    assert first["next_cursor"]

    # The queue is intentionally not a stored snapshot. A mutation after page 1
    # is reflected by page 2, while the signed ordering boundary still prevents
    # previously emitted actions from looping back into the continuation.
    interviews[-1].status = "cancelled"
    interviews[-1].version += 1
    db_session.flush()

    second = build_today_queue_with_interviews(
        db_session,
        user_id=user.id,
        timezone_name="UTC",
        secret_key=SECRET,
        cursor=first["next_cursor"],
        limit=2,
        now=NOW + timedelta(hours=1),
    )
    assert second["as_of"] == first["as_of"]
    assert second["counts"]["total"] == 2
    assert second["items"] == []
    assert second["next_cursor"] is None
