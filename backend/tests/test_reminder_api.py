from datetime import date, datetime, timezone
from uuid import uuid4

from app.config import settings
from app.models import AuditEvent, JobTrack, OAuthIdentity, ReminderDelivery, ReminderPreference, User
from app.reminder_schemas import reminder_occurrence_key


def _user(db_session):
    return db_session.query(User).filter_by(email="test@jobgrid.dev").one()


def _track(db_session, user, *, due=None):
    track = JobTrack(
        user_id=user.id,
        url=f"https://reminder-api.example/{uuid4()}",
        company="Acme",
        title="Engineer",
        status="follow_up",
        follow_up_at=due or datetime(2026, 9, 22, 8, 0, 0),
    )
    db_session.add(track)
    db_session.commit()
    db_session.refresh(track)
    return track


def _delivery(db_session, user, track, *, status="pending", channel="in_app", version=1):
    sent_at = datetime(2026, 9, 22, 9, 0, tzinfo=timezone.utc) if status == "sent" else None
    item = ReminderDelivery(
        user_id=user.id,
        track_id=track.id,
        occurrence_key=reminder_occurrence_key(
            track_id=track.id,
            due_at=track.follow_up_at.replace(tzinfo=timezone.utc),
            notification_local_date=date(2026, 9, 22),
        ),
        channel=channel,
        status=status,
        scheduled_at=datetime(2026, 9, 22, 9, 0, tzinfo=timezone.utc),
        attempt_count=1 if status != "pending" else 0,
        sent_at=sent_at,
        version=version,
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item


def test_preferences_default_and_version_guard(auth_client):
    auth_client.post("/test/reset")
    response = auth_client.get("/crm/reminders/preferences")
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is False
    assert data["channel"] == "in_app"
    assert data["local_time"] == "09:00"
    assert len(data["version"]) == 32

    stale = auth_client.patch(
        "/crm/reminders/preferences",
        json={
            "version": "0" * 32,
            "enabled": True,
            "channel": "in_app",
            "local_time": "09:00",
            "quiet_start": "21:00",
            "quiet_end": "08:00",
        },
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "preference_conflict"


def test_opt_out_cancels_unsent_only(auth_client, db_session):
    auth_client.post("/test/reset")
    user = _user(db_session)
    pref = ReminderPreference(
        user_id=user.id,
        enabled=True,
        channel="in_app",
        local_time="09:00",
        quiet_start="21:00",
        quiet_end="08:00",
    )
    db_session.add(pref)
    db_session.commit()
    track = _track(db_session, user)
    pending = _delivery(db_session, user, track, status="pending")
    sent = _delivery(
        db_session,
        user,
        track,
        status="sent",
        version=2,
    )
    # Unique occurrence/channel requires a distinct due-derived occurrence.
    sent.occurrence_key = sent.occurrence_key.replace("date:2026-09-22", "date:2026-09-23")
    db_session.commit()

    current = auth_client.get("/crm/reminders/preferences").json()
    response = auth_client.patch(
        "/crm/reminders/preferences",
        json={
            "version": current["version"],
            "enabled": False,
            "channel": "in_app",
            "local_time": "09:00",
            "quiet_start": "21:00",
            "quiet_end": "08:00",
        },
    )
    assert response.status_code == 200
    db_session.expire_all()
    assert db_session.get(ReminderDelivery, pending.id).status == "cancelled"
    assert db_session.get(ReminderDelivery, sent.id).status == "sent"
    assert db_session.get(ReminderDelivery, sent.id).sent_at is not None


def test_unverified_destination_cannot_enable_email(auth_client, db_session):
    auth_client.post("/test/reset")
    original = (
        settings.REMINDER_EMAIL_DELIVERY_ENABLED,
        settings.SMTP_HOST,
        settings.EMAIL_FROM,
    )
    settings.REMINDER_EMAIL_DELIVERY_ENABLED = True
    settings.SMTP_HOST = "smtp.example.test"
    settings.EMAIL_FROM = "noreply@example.test"
    try:
        current = auth_client.get("/crm/reminders/preferences").json()
        response = auth_client.patch(
            "/crm/reminders/preferences",
            json={
                "version": current["version"],
                "enabled": True,
                "channel": "email",
                "local_time": "09:00",
                "quiet_start": "21:00",
                "quiet_end": "08:00",
            },
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "email_unavailable"
        assert response.json()["detail"]["reason"] == "verified_destination_unavailable"

        user = _user(db_session)
        db_session.add(
            OAuthIdentity(
                user_id=user.id,
                provider="google",
                provider_id=f"provider-{uuid4()}",
            )
        )
        db_session.commit()
        refreshed = auth_client.get("/crm/reminders/preferences").json()
        response = auth_client.patch(
            "/crm/reminders/preferences",
            json={
                "version": refreshed["version"],
                "enabled": True,
                "channel": "email",
                "local_time": "09:00",
                "quiet_start": "21:00",
                "quiet_end": "08:00",
            },
        )
        assert response.status_code == 200
        assert response.json()["channel"] == "email"
    finally:
        (
            settings.REMINDER_EMAIL_DELIVERY_ENABLED,
            settings.SMTP_HOST,
            settings.EMAIL_FROM,
        ) = original


def test_unknown_retry_requires_explicit_action(auth_client, db_session):
    auth_client.post("/test/reset")
    user = _user(db_session)
    track = _track(db_session, user)
    delivery = _delivery(
        db_session,
        user,
        track,
        status="unknown",
        version=4,
    )

    warning = auth_client.post(
        f"/crm/reminders/{delivery.id}/retry",
        headers={"X-Operation-ID": str(uuid4())},
        json={"version": 4, "confirm_possible_duplicate": False},
    )
    assert warning.status_code == 422
    assert warning.json()["detail"]["code"] == "duplicate_warning_required"

    operation_id = str(uuid4())
    retried = auth_client.post(
        f"/crm/reminders/{delivery.id}/retry",
        headers={"X-Operation-ID": operation_id},
        json={"version": 4, "confirm_possible_duplicate": True},
    )
    assert retried.status_code == 200
    assert retried.json()["status"] == "pending"
    assert retried.json()["possible_duplicate"] is False

    db_session.expire_all()
    event = db_session.query(AuditEvent).filter_by(
        user_id=user.id,
        event_type="reminder_unknown_retry",
        entity_type="reminder_delivery",
        entity_id=delivery.id,
    ).one()
    assert event.metadata_json["operation_id"] == operation_id
    assert "recipient" not in event.metadata_json
    assert "body" not in event.metadata_json


def test_foreign_delivery_hidden(auth_client, db_session):
    auth_client.post("/test/reset")
    owner = _user(db_session)
    foreign = User(email=f"foreign-{uuid4()}@example.test")
    db_session.add(foreign)
    db_session.commit()
    foreign_track = _track(db_session, foreign)
    delivery = _delivery(db_session, foreign, foreign_track, status="unknown", version=2)

    response = auth_client.post(
        f"/crm/reminders/{delivery.id}/retry",
        headers={"X-Operation-ID": str(uuid4())},
        json={"version": 2, "confirm_possible_duplicate": True},
    )
    assert response.status_code == 404

    listing = auth_client.get("/crm/reminders").json()
    assert delivery.id not in {item["id"] for item in listing["items"]}
    assert owner.id != foreign.id


def test_in_app_unread_is_persisted_and_marked_read(auth_client, db_session):
    auth_client.post("/test/reset")
    user = _user(db_session)
    track = _track(db_session, user)
    delivery = _delivery(db_session, user, track, status="sent", version=3)

    listing = auth_client.get("/crm/reminders").json()
    item = next(row for row in listing["items"] if row["id"] == delivery.id)
    assert item["unread"] is True
    assert item["read_at"] is None

    response = auth_client.post(
        f"/crm/reminders/{delivery.id}/read",
        json={"version": item["version"]},
    )
    assert response.status_code == 200
    assert response.json()["unread"] is False
    assert response.json()["read_at"] is not None


def test_reminder_history_cursor_and_safe_fields(auth_client, db_session):
    auth_client.post("/test/reset")
    user = _user(db_session)
    track = _track(db_session, user)
    for index in range(3):
        delivery = _delivery(db_session, user, track, status="pending", version=1)
        delivery.occurrence_key = delivery.occurrence_key.replace(
            "date:2026-09-22",
            f"date:2026-09-{22 + index:02d}",
        )
        db_session.commit()

    first = auth_client.get("/crm/reminders?limit=2")
    assert first.status_code == 200
    body = first.json()
    assert len(body["items"]) == 2
    assert body["next_cursor"]
    encoded = str(body)
    assert user.email not in encoded
    assert "html" not in encoded.lower()

    second = auth_client.get(
        "/crm/reminders",
        params={"limit": 2, "cursor": body["next_cursor"]},
    )
    assert second.status_code == 200
    assert len(second.json()["items"]) == 1


def test_reminder_routes_require_auth(client):
    assert client.get("/crm/reminders/preferences").status_code == 401
    assert client.get("/crm/reminders").status_code == 401
