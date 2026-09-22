from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models import JobTrack, ReminderDelivery, ReminderPreference, User
from app.reminder_schemas import reminder_occurrence_key
from app.services.reminders import (
    DeliveryOutcome,
    claim_due_deliveries,
    email_delivery_availability,
    plan_due_occurrence,
    process_reminder_batch,
    recover_expired_claims,
    resolve_local_wall_time,
    sync_track_reminder,
    sync_user_reminders,
)


class SequenceTransport:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def send(self, *, user, track, delivery):
        self.calls += 1
        if self.outcomes:
            return self.outcomes.pop(0)
        return DeliveryOutcome("accepted")


def _seed(
    db,
    *,
    timezone_name="UTC",
    channel="in_app",
    local_time="09:00",
    quiet_start="21:00",
    quiet_end="08:00",
    follow_up_at=None,
):
    user = User(
        email=f"reminder-{uuid4()}@example.test",
        timezone=timezone_name,
    )
    db.add(user)
    db.flush()
    pref = ReminderPreference(
        user_id=user.id,
        enabled=True,
        channel=channel,
        local_time=local_time,
        quiet_start=quiet_start,
        quiet_end=quiet_end,
    )
    track = JobTrack(
        user_id=user.id,
        url=f"https://example.test/jobs/{uuid4()}",
        company="Acme",
        title="Engineer",
        status="follow_up",
        follow_up_at=follow_up_at or datetime(2026, 9, 22, 8, 0, 0),
    )
    db.add_all([pref, track])
    db.commit()
    db.refresh(user)
    db.refresh(track)
    return user, pref, track


def test_dst_gap_and_overlap_one_daily_occurrence(db_session):
    user, pref, track = _seed(
        db_session,
        timezone_name="America/New_York",
        local_time="02:30",
        follow_up_at=datetime(2026, 3, 8, 15, 0, 0),
    )
    planned = plan_due_occurrence(
        track=track,
        preference=pref,
        timezone_name=user.timezone,
        now_utc=datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc),
    )
    assert planned is not None
    assert planned.notification_local_date == date(2026, 3, 8)
    assert planned.scheduled_at == datetime(2026, 3, 8, 7, 0, tzinfo=timezone.utc)

    sync_track_reminder(
        db_session,
        user_id=user.id,
        track_id=track.id,
        now_utc=datetime(2026, 3, 8, 12, 0, tzinfo=timezone.utc),
    )
    sync_track_reminder(
        db_session,
        user_id=user.id,
        track_id=track.id,
        now_utc=datetime(2026, 3, 8, 12, 1, tzinfo=timezone.utc),
    )
    db_session.commit()
    assert db_session.query(ReminderDelivery).filter_by(user_id=user.id).count() == 1

    assert resolve_local_wall_time(
        date(2026, 11, 1),
        "01:30",
        "America/New_York",
    ) == datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc)


def test_quiet_hours_defer_to_next_allowed_local_time(db_session):
    user, pref, track = _seed(
        db_session,
        timezone_name="Asia/Kolkata",
        local_time="22:30",
        quiet_start="21:00",
        quiet_end="08:00",
        follow_up_at=datetime(2026, 9, 22, 12, 0, 0),
    )
    planned = plan_due_occurrence(
        track=track,
        preference=pref,
        timezone_name=user.timezone,
        now_utc=datetime(2026, 9, 22, 1, 0, tzinfo=timezone.utc),
    )
    assert planned is not None
    assert planned.scheduled_at == datetime(2026, 9, 23, 2, 30, tzinfo=timezone.utc)


def test_rescheduled_followup_cancels_old_delivery(db_session):
    user, _pref, track = _seed(
        db_session,
        follow_up_at=datetime(2026, 9, 22, 8, 0, 0),
    )
    first = sync_track_reminder(
        db_session,
        user_id=user.id,
        track_id=track.id,
        now_utc=datetime(2026, 9, 22, 7, 0, tzinfo=timezone.utc),
    )
    assert first is not None
    old_key = first.occurrence_key

    track.follow_up_at = datetime(2026, 9, 23, 8, 0, 0)
    second = sync_track_reminder(
        db_session,
        user_id=user.id,
        track_id=track.id,
        now_utc=datetime(2026, 9, 22, 7, 1, tzinfo=timezone.utc),
    )
    db_session.commit()

    assert second is not None
    assert second.occurrence_key != old_key
    old = db_session.query(ReminderDelivery).filter_by(
        user_id=user.id,
        occurrence_key=old_key,
    ).one()
    assert old.status == "cancelled"
    assert old.last_error_code == "source_changed"


def test_known_transient_failure_bounded_retry(db_session):
    user, _pref, track = _seed(
        db_session,
        follow_up_at=datetime(2026, 9, 20, 8, 0, 0),
    )
    transport = SequenceTransport(
        DeliveryOutcome("transient", "smtp_transient"),
        DeliveryOutcome("transient", "smtp_transient"),
        DeliveryOutcome("transient", "smtp_transient"),
    )

    # Use an in-app row to plan, then switch only the delivery channel for a
    # deterministic transport test without enabling external SMTP.
    delivery = sync_track_reminder(
        db_session,
        user_id=user.id,
        track_id=track.id,
        now_utc=datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc),
    )
    assert delivery is not None
    delivery.channel = "email"
    delivery.occurrence_key = reminder_occurrence_key(
        track_id=track.id,
        due_at=track.follow_up_at.replace(tzinfo=timezone.utc),
        notification_local_date=date(2026, 9, 20),
    )
    db_session.query(ReminderPreference).filter_by(user_id=user.id).update(
        {"channel": "email"}
    )
    db_session.commit()

    original_gate = settings.REMINDER_EMAIL_DELIVERY_ENABLED
    original_host = settings.SMTP_HOST
    original_from = settings.EMAIL_FROM
    settings.REMINDER_EMAIL_DELIVERY_ENABLED = True
    settings.SMTP_HOST = "smtp.example.test"
    settings.EMAIL_FROM = "noreply@example.test"
    try:
        # The account intentionally has no OAuthIdentity, so inject an accepted
        # availability by monkeypatching at service level in the API tests. Here
        # exercise the state machine directly.
        from app.services import reminders as reminder_service
        old_availability = reminder_service.email_delivery_availability
        reminder_service.email_delivery_availability = lambda db, user: (True, None)
        try:
            first_now = datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc)
            result = process_reminder_batch(db_session, now_utc=first_now, transport=transport)
            assert result["failed"] == 1
            db_session.refresh(delivery)
            assert delivery.attempt_count == 1
            assert delivery.next_attempt_at == first_now + timedelta(minutes=1)

            second_now = first_now + timedelta(minutes=1)
            process_reminder_batch(db_session, now_utc=second_now, transport=transport)
            db_session.refresh(delivery)
            assert delivery.attempt_count == 2
            assert delivery.next_attempt_at == second_now + timedelta(minutes=5)

            third_now = second_now + timedelta(minutes=5)
            process_reminder_batch(db_session, now_utc=third_now, transport=transport)
            db_session.refresh(delivery)
            assert delivery.attempt_count == 3
            assert delivery.status == "failed"
            assert delivery.next_attempt_at is None

            later = third_now + timedelta(hours=1)
            result = process_reminder_batch(db_session, now_utc=later, transport=transport)
            assert result["claimed"] == 1
            # A terminal known failure has no retry time, but failed is normally
            # claimable. Max attempts therefore must suppress it explicitly.
        finally:
            reminder_service.email_delivery_availability = old_availability
    finally:
        settings.REMINDER_EMAIL_DELIVERY_ENABLED = original_gate
        settings.SMTP_HOST = original_host
        settings.EMAIL_FROM = original_from


def test_crash_after_acceptance_becomes_unknown(db_session):
    user, _pref, track = _seed(db_session)
    delivery = ReminderDelivery(
        user_id=user.id,
        track_id=track.id,
        occurrence_key=reminder_occurrence_key(
            track_id=track.id,
            due_at=track.follow_up_at.replace(tzinfo=timezone.utc),
            notification_local_date=date(2026, 9, 22),
        ),
        channel="in_app",
        status="sending",
        scheduled_at=datetime(2026, 9, 22, 9, 0, tzinfo=timezone.utc),
        lease_until=datetime(2026, 9, 22, 9, 5, tzinfo=timezone.utc),
        attempt_count=1,
        version=2,
    )
    db_session.add(delivery)
    db_session.commit()

    recovered = recover_expired_claims(
        db_session,
        now_utc=datetime(2026, 9, 22, 9, 6, tzinfo=timezone.utc),
    )
    db_session.commit()
    db_session.refresh(delivery)
    assert recovered == 1
    assert delivery.status == "unknown"
    assert delivery.next_attempt_at is None
    assert delivery.last_error_code == "lease_expired_unknown"


def test_restart_does_not_duplicate_accepted_delivery(db_session):
    user, _pref, track = _seed(
        db_session,
        follow_up_at=datetime(2026, 9, 20, 8, 0, 0),
    )
    delivery = sync_track_reminder(
        db_session,
        user_id=user.id,
        track_id=track.id,
        now_utc=datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc),
    )
    db_session.commit()
    assert delivery is not None
    delivery.status = "sent"
    delivery.sent_at = datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc)
    delivery.version += 1
    db_session.commit()

    result = process_reminder_batch(
        db_session,
        now_utc=datetime(2026, 9, 22, 10, 5, tzinfo=timezone.utc),
        transport=SequenceTransport(DeliveryOutcome("accepted")),
    )
    db_session.refresh(delivery)
    assert result["claimed"] == 0
    assert delivery.status == "sent"
    assert delivery.sent_at == datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc)


def test_timezone_change_replans_unsent(db_session):
    user, _pref, track = _seed(
        db_session,
        timezone_name="UTC",
        follow_up_at=datetime(2026, 9, 22, 20, 0, 0),
    )
    first = sync_track_reminder(
        db_session,
        user_id=user.id,
        track_id=track.id,
        now_utc=datetime(2026, 9, 22, 1, 0, tzinfo=timezone.utc),
    )
    db_session.commit()
    assert first is not None
    first_schedule = first.scheduled_at

    user.timezone = "Asia/Kolkata"
    sync_user_reminders(
        db_session,
        user_id=user.id,
        now_utc=datetime(2026, 9, 22, 1, 1, tzinfo=timezone.utc),
    )
    db_session.commit()
    db_session.refresh(first)
    assert first.status == "cancelled"
    active = db_session.query(ReminderDelivery).filter_by(
        user_id=user.id,
        status="pending",
    ).one()
    assert active.scheduled_at != first_schedule


def test_controlled_inbox_receipt_or_explicit_blocked_gate(db_session):
    user, _pref, _track = _seed(db_session, channel="email")
    available, reason = email_delivery_availability(db_session, user=user)
    if settings.REMINDER_EMAIL_DELIVERY_ENABLED:
        pytest.skip("Controlled staging send requires explicit external credentials and authorization.")
    assert available is False
    assert reason == "email_delivery_disabled"


@pytest.mark.postgresql
def test_two_workers_one_claim(engine):
    if engine.dialect.name != "postgresql":
        pytest.skip("SKIP LOCKED concurrency proof requires PostgreSQL.")

    Session = sessionmaker(bind=engine)
    seed = Session()
    user, _pref, track = _seed(
        seed,
        follow_up_at=datetime(2026, 9, 20, 8, 0, 0),
    )
    delivery = sync_track_reminder(
        seed,
        user_id=user.id,
        track_id=track.id,
        now_utc=datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc),
    )
    seed.commit()
    assert delivery is not None
    delivery_id = delivery.id
    seed.close()

    one = Session()
    two = Session()
    try:
        first = claim_due_deliveries(
            one,
            now_utc=datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc),
            lease_seconds=300,
            limit=50,
        )
        second = claim_due_deliveries(
            two,
            now_utc=datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc),
            lease_seconds=300,
            limit=50,
        )
        assert first == [delivery_id]
        assert second == []
    finally:
        one.rollback()
        two.rollback()
        one.close()
        two.close()
