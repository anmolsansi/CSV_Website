from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.contact_models import Interview
from app.models import JobTrack, User
from app.services.today_f8 import build_today_queue_with_interviews, interview_action_key, snooze_action_with_interviews


def _setup(db_session):
    user = User(email=f"f8-today-{uuid4()}@example.test", timezone="UTC")
    db_session.add(user)
    db_session.flush()
    track = JobTrack(user_id=user.id, url=f"https://example.test/jobs/{uuid4()}", company="Acme", title="Engineer")
    db_session.add(track)
    db_session.flush()
    interview = Interview(
        user_id=user.id,
        track_id=track.id,
        starts_at=datetime(2026, 9, 23, 16, 0),
        ends_at=datetime(2026, 9, 23, 17, 0),
        timezone="UTC",
        kind="video",
        status="scheduled",
        round_label="Technical",
    )
    db_session.add(interview)
    db_session.flush()
    return user, track, interview


def test_cancel_removes_today_interview_action(db_session):
    user, _track, interview = _setup(db_session)
    now = datetime(2026, 9, 23, 8, 0, tzinfo=timezone.utc)
    first = build_today_queue_with_interviews(
        db_session,
        user_id=user.id,
        timezone_name="UTC",
        secret_key="test-secret",
        now=now,
    )
    actions = [item for item in first["items"] if item["type"] == "interview"]
    assert len(actions) == 1
    assert actions[0]["action_key"] == interview_action_key(interview.id, interview.starts_at)

    interview.status = "cancelled"
    interview.version += 1
    db_session.flush()
    second = build_today_queue_with_interviews(
        db_session,
        user_id=user.id,
        timezone_name="UTC",
        secret_key="test-secret",
        now=now,
    )
    assert not [item for item in second["items"] if item["type"] == "interview"]


def test_interview_preparation_reuses_today_snooze_model(db_session):
    user, _track, interview = _setup(db_session)
    now = datetime(2026, 9, 23, 8, 0, tzinfo=timezone.utc)
    key = interview_action_key(interview.id, interview.starts_at)
    override = snooze_action_with_interviews(
        db_session,
        user_id=user.id,
        action_key=key,
        until=now + timedelta(hours=2),
        version=1,
        now=now,
    )
    assert override.action_key == key
    assert override.version == 2

    queue = build_today_queue_with_interviews(
        db_session,
        user_id=user.id,
        timezone_name="UTC",
        secret_key="test-secret",
        now=now,
    )
    assert not [item for item in queue["items"] if item["action_key"] == key]

    with_snoozed = build_today_queue_with_interviews(
        db_session,
        user_id=user.id,
        timezone_name="UTC",
        secret_key="test-secret",
        now=now,
        include_snoozed=True,
    )
    item = next(item for item in with_snoozed["items"] if item["action_key"] == key)
    assert item["snooze_version"] == 2
