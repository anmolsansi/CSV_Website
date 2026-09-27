"""Cross-feature acceptance regressions required by C-08."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.models import JobTrack, ReminderDelivery, ReminderPreference, User
from app.services.reminders import sync_track_reminder
from app.services.today_f8 import build_today_queue_with_interviews, snooze_action_with_interviews
from app.time_utils import normalize_utc_instant
from app.today_schemas import followup_action_key

SECRET = "c08-cross-feature-secret"
NOW = datetime(2026, 9, 23, 8, 0, tzinfo=timezone.utc)


def test_today_snooze_hides_action_without_rescheduling_reminder(db_session):
    """A Today snooze is presentation state, not reminder-delivery state."""
    user = User(email=f"c08-snooze-{uuid4()}@example.test", timezone="UTC")
    db_session.add(user)
    db_session.flush()
    preference = ReminderPreference(
        user_id=user.id,
        enabled=True,
        channel="in_app",
        local_time="09:00",
        quiet_start="00:00",
        quiet_end="00:00",
    )
    track = JobTrack(
        user_id=user.id,
        url=f"https://example.test/jobs/{uuid4()}",
        company="C08 Co",
        title="Platform Engineer",
        status="follow_up",
        follow_up_at=datetime(2026, 9, 23, 12, 0, 0),
    )
    db_session.add_all([preference, track])
    db_session.commit()

    delivery = sync_track_reminder(
        db_session,
        user_id=user.id,
        track_id=track.id,
        now_utc=NOW,
    )
    assert delivery is not None
    db_session.commit()
    db_session.refresh(delivery)

    original_key = delivery.occurrence_key
    original_status = delivery.status
    original_version = delivery.version
    original_schedule = normalize_utc_instant(delivery.scheduled_at)
    original_follow_up = normalize_utc_instant(track.follow_up_at)

    action_key = followup_action_key(track.id, track.follow_up_at)
    snoozed = snooze_action_with_interviews(
        db_session,
        user_id=user.id,
        action_key=action_key,
        until=NOW + timedelta(hours=6),
        version=1,
        now=NOW,
    )
    db_session.commit()
    db_session.refresh(track)
    db_session.refresh(delivery)

    assert snoozed.action_key == action_key
    assert normalize_utc_instant(track.follow_up_at) == original_follow_up
    assert delivery.occurrence_key == original_key
    assert delivery.status == original_status == "pending"
    assert delivery.version == original_version
    assert normalize_utc_instant(delivery.scheduled_at) == original_schedule
    assert db_session.query(ReminderDelivery).filter_by(user_id=user.id).count() == 1

    hidden = build_today_queue_with_interviews(
        db_session,
        user_id=user.id,
        timezone_name=user.timezone,
        secret_key=SECRET,
        include_snoozed=False,
        now=NOW,
    )
    assert action_key not in {item["action_key"] for item in hidden["items"]}

    visible = build_today_queue_with_interviews(
        db_session,
        user_id=user.id,
        timezone_name=user.timezone,
        secret_key=SECRET,
        include_snoozed=True,
        now=NOW,
    )
    restored_item = next(item for item in visible["items"] if item["action_key"] == action_key)
    assert restored_item["snoozed_until"] is not None
    assert normalize_utc_instant(delivery.scheduled_at) == original_schedule
