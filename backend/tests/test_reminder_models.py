from datetime import datetime, time, timezone
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import JobTrack, ReminderDelivery, ReminderPreference, User
from app.reminder_schemas import (
    ReminderContractError,
    ReminderPreferenceData,
    apply_delivery_transition,
    is_quiet_local_time,
    reminder_occurrence_key,
    validate_preference_for_timezone,
)


def _user_and_track(db_session, suffix: str):
    user = User(email=f"jg037-{suffix}-{uuid4()}@example.test")
    db_session.add(user)
    db_session.flush()
    track = JobTrack(
        user_id=user.id,
        url=f"https://example.test/jobs/jg037-{suffix}-{uuid4()}",
        company="Reminder Test",
        title="Engineer",
        status="follow_up",
        follow_up_at=datetime(2026, 9, 25, 15, 0, 0),
    )
    db_session.add(track)
    db_session.flush()
    return user, track


def test_default_opt_out(db_session):
    existing = User(email=f"jg037-existing-{uuid4()}@example.test")
    fresh = User(email=f"jg037-fresh-{uuid4()}@example.test")
    db_session.add_all([existing, fresh])
    db_session.flush()

    assert db_session.query(ReminderPreference).filter_by(user_id=existing.id).first() is None
    assert db_session.query(ReminderPreference).filter_by(user_id=fresh.id).first() is None

    pref = ReminderPreference(user_id=fresh.id)
    db_session.add(pref)
    db_session.flush()
    db_session.refresh(pref)
    assert pref.enabled is False
    assert pref.channel == "in_app"
    assert pref.local_time == "09:00"
    assert pref.quiet_start == "21:00"
    assert pref.quiet_end == "08:00"

    defaults = ReminderPreferenceData()
    assert defaults.enabled is False
    assert validate_preference_for_timezone(defaults, "America/Chicago") is defaults
    with pytest.raises(ReminderContractError) as exc:
        validate_preference_for_timezone(defaults, "Not/A_Real_Zone")
    assert exc.value.code == "invalid_timezone"

    assert is_quiet_local_time(
        time(23, 30), quiet_start="21:00", quiet_end="08:00"
    ) is True
    assert is_quiet_local_time(
        time(12, 0), quiet_start="21:00", quiet_end="08:00"
    ) is False
    assert is_quiet_local_time(
        time(21, 0), quiet_start="21:00", quiet_end="21:00"
    ) is False


def test_duplicate_occurrence_unique_constraint(db_session):
    user, track = _user_and_track(db_session, "unique")
    due = datetime(2026, 9, 25, 15, 0, 0, tzinfo=timezone.utc)
    occurrence = reminder_occurrence_key(
        track_id=track.id,
        due_at=due,
        notification_local_date=datetime(2026, 9, 25).date(),
    )
    first = ReminderDelivery(
        user_id=user.id,
        track_id=track.id,
        occurrence_key=occurrence,
        channel="in_app",
        status="pending",
        scheduled_at=due,
    )
    duplicate = ReminderDelivery(
        user_id=user.id,
        track_id=track.id,
        occurrence_key=occurrence,
        channel="in_app",
        status="pending",
        scheduled_at=due,
    )
    db_session.add(first)
    db_session.commit()

    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_illegal_state_transition_rejected(db_session):
    user, track = _user_and_track(db_session, "transitions")
    due = datetime(2026, 9, 25, 15, 0, 0, tzinfo=timezone.utc)
    delivery = ReminderDelivery(
        user_id=user.id,
        track_id=track.id,
        occurrence_key=reminder_occurrence_key(
            track_id=track.id,
            due_at=due,
            notification_local_date=datetime(2026, 9, 25).date(),
        ),
        channel="email",
        status="pending",
        scheduled_at=due,
        version=1,
    )
    db_session.add(delivery)
    db_session.commit()

    apply_delivery_transition(delivery, "sending")
    assert delivery.status == "sending"
    assert delivery.version == 2

    accepted_at = datetime(2026, 9, 25, 15, 0, 5, tzinfo=timezone.utc)
    apply_delivery_transition(delivery, "sent", sent_at=accepted_at)
    assert delivery.status == "sent"
    assert delivery.sent_at == accepted_at
    assert delivery.version == 3
    db_session.commit()

    with pytest.raises(ReminderContractError) as illegal:
        apply_delivery_transition(delivery, "failed")
    assert illegal.value.code in {"illegal_delivery_transition", "sent_at_immutable"}
    assert delivery.status == "sent"
    assert delivery.sent_at == accepted_at

    with pytest.raises(ReminderContractError) as immutable:
        apply_delivery_transition(
            delivery,
            "sent",
            sent_at=datetime(2026, 9, 25, 15, 0, 6, tzinfo=timezone.utc),
        )
    assert immutable.value.code == "sent_at_immutable"
    assert delivery.sent_at == accepted_at
