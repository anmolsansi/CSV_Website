from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import JobTrack, ReminderDelivery, ReminderPreference, User
from app.reminder_schemas import (
    ReminderContractError,
    ReminderPreferenceData,
    is_quiet_local_time,
    validate_delivery_transition,
    validate_hhmm,
    validate_preference_for_timezone,
    validate_timezone_name,
)


def _user(db_session, prefix: str = "reminder") -> User:
    user = User(email=f"{prefix}-{uuid4()}@example.test")
    db_session.add(user)
    db_session.flush()
    return user


def _track(db_session, user: User) -> JobTrack:
    track = JobTrack(
        user_id=user.id,
        url=f"https://reminders.example/jobs/{uuid4()}",
        status="follow_up",
    )
    db_session.add(track)
    db_session.flush()
    return track


def _delivery(
    db_session,
    user: User,
    track: JobTrack,
    *,
    occurrence_key: str,
    channel: str = "in_app",
    status: str = "pending",
    sent_at=None,
) -> ReminderDelivery:
    item = ReminderDelivery(
        user_id=user.id,
        track_id=track.id,
        occurrence_key=occurrence_key,
        channel=channel,
        status=status,
        scheduled_at=datetime(2026, 9, 23, 9, 0, tzinfo=timezone.utc),
        sent_at=sent_at,
    )
    db_session.add(item)
    db_session.flush()
    return item


def test_duplicate_occurrence_unique_constraint(db_session):
    user = _user(db_session, "dedupe")
    track = _track(db_session, user)
    occurrence_key = f"track:{track.id}:due:2026-09-23T09:00:00Z:date:2026-09-23"

    first = _delivery(
        db_session,
        user,
        track,
        occurrence_key=occurrence_key,
        channel="email",
    )
    assert first.id is not None

    db_session.add(
        ReminderDelivery(
            user_id=user.id,
            track_id=track.id,
            occurrence_key=occurrence_key,
            channel="email",
            status="pending",
            scheduled_at=datetime(2026, 9, 23, 9, 5, tzinfo=timezone.utc),
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_illegal_state_transition_rejected():
    accepted_at = datetime(2026, 9, 23, 9, 0, tzinfo=timezone.utc)

    assert validate_delivery_transition(
        "pending",
        "sending",
        current_sent_at=None,
        target_sent_at=None,
    ) == "sending"
    assert validate_delivery_transition(
        "sending",
        "sent",
        current_sent_at=None,
        target_sent_at=accepted_at,
    ) == "sent"

    with pytest.raises(ReminderContractError) as terminal:
        validate_delivery_transition(
            "sent",
            "pending",
            current_sent_at=accepted_at,
            target_sent_at=accepted_at,
        )
    assert terminal.value.code == "illegal_delivery_transition"

    with pytest.raises(ReminderContractError) as immutable:
        validate_delivery_transition(
            "sent",
            "sent",
            current_sent_at=accepted_at,
            target_sent_at=accepted_at.replace(minute=1),
        )
    assert immutable.value.code == "sent_at_immutable"

    with pytest.raises(ReminderContractError) as unknown_retry:
        validate_delivery_transition(
            "unknown",
            "pending",
            current_sent_at=None,
            target_sent_at=None,
        )
    assert unknown_retry.value.code == "unknown_retry_requires_explicit_action"

    assert validate_delivery_transition(
        "unknown",
        "pending",
        current_sent_at=None,
        target_sent_at=None,
        allow_unknown_retry=True,
    ) == "pending"


def test_default_opt_out(db_session):
    existing_user = _user(db_session, "existing-optout")
    new_user = _user(db_session, "new-optout")

    assert (
        db_session.query(ReminderPreference)
        .filter_by(user_id=existing_user.id)
        .first()
        is None
    )
    assert (
        db_session.query(ReminderPreference)
        .filter_by(user_id=new_user.id)
        .first()
        is None
    )

    preference = ReminderPreference(user_id=new_user.id)
    db_session.add(preference)
    db_session.flush()
    assert preference.enabled is False
    assert preference.channel == "in_app"
    assert preference.local_time == "09:00"
    assert preference.quiet_start == "21:00"
    assert preference.quiet_end == "08:00"

    contract_default = ReminderPreferenceData()
    assert contract_default.enabled is False
    assert validate_preference_for_timezone(
        contract_default,
        timezone_name="UTC",
    ) is contract_default


def test_local_time_timezone_and_quiet_hours_validation():
    assert validate_hhmm("09:00", field="local_time") == "09:00"
    assert validate_timezone_name("America/New_York") == "America/New_York"

    with pytest.raises(ReminderContractError):
        validate_hhmm("9:00", field="local_time")
    with pytest.raises(ReminderContractError):
        validate_hhmm("24:00", field="quiet_start")
    with pytest.raises(ReminderContractError):
        validate_timezone_name("UTC+5:30")

    assert is_quiet_local_time(
        "22:30",
        quiet_start="21:00",
        quiet_end="08:00",
    ) is True
    assert is_quiet_local_time(
        "07:59",
        quiet_start="21:00",
        quiet_end="08:00",
    ) is True
    assert is_quiet_local_time(
        "12:00",
        quiet_start="21:00",
        quiet_end="08:00",
    ) is False
    assert is_quiet_local_time(
        "21:00",
        quiet_start="21:00",
        quiet_end="21:00",
    ) is False


def test_sent_at_database_state_constraint(db_session):
    user = _user(db_session, "sent-at")
    track = _track(db_session, user)
    db_session.add(
        ReminderDelivery(
            user_id=user.id,
            track_id=track.id,
            occurrence_key=f"track:{track.id}:bad-sent",
            channel="email",
            status="sent",
            scheduled_at=datetime(2026, 9, 23, 9, 0, tzinfo=timezone.utc),
            sent_at=None,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()
