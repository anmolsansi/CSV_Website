from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.orm import sessionmaker

from app.availability_schemas import deadline_action_key
from app.backup_schemas import validate_backup_v2
from app.config import settings
from app.models import (
    CsvRow,
    JobAvailability,
    JobCheckRequest,
    JobTrack,
    ReminderDelivery,
    ReminderPreference,
    User,
    WorkItem,
)
from app.services.availability import (
    AvailabilityServiceError,
    enqueue_job_check,
    finish_job_check_request,
)
from app.services.backups import export_backup_v2, restore_backup_v2
from app.services.safe_job_fetch import SafeFetchResult
from app.services.today import build_today_queue


def _test_user(db_session) -> User:
    db_session.expire_all()
    user = db_session.query(User).filter_by(email="test@jobgrid.dev").first()
    assert user is not None
    return user


def _row(db_session, user: User, *, url: str | None = None) -> CsvRow:
    item = CsvRow(
        user_id=user.id,
        upload_batch_id=str(uuid4()),
        url=url or f"https://freshness.example/jobs/{uuid4()}",
        company_guess="Fresh Co",
        title="Backend Engineer",
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item


def _user(db_session, prefix: str, timezone_name: str = "UTC") -> User:
    user = User(
        email=f"{prefix}-{uuid4()}@example.test",
        timezone=timezone_name,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_manual_row_availability_version_close_reopen_and_timezone(auth_client, db_session):
    auth_client.post("/test/reset")
    user = _test_user(db_session)
    user.timezone = "America/New_York"
    db_session.commit()
    row = _row(db_session, user)

    initial = auth_client.get(f"/crm/jobs/{row.id}/availability")
    assert initial.status_code == 200
    assert initial.json()["state"] == "unknown"
    assert initial.json()["version"] == 1
    assert initial.json()["timezone"] == "America/New_York"
    assert initial.json()["checks_enabled"] is False

    deadline = auth_client.patch(
        f"/crm/jobs/{row.id}/availability",
        json={
            "version": 1,
            "deadline_at": "2026-11-01",
        },
    )
    assert deadline.status_code == 200
    saved = deadline.json()
    assert saved["deadline_source"] == "user"
    assert saved["deadline_local_date"] == "2026-11-01"
    assert saved["deadline_at"] == "2026-11-02T04:59:59.999999Z"
    assert saved["version"] == 2

    stale = auth_client.patch(
        f"/crm/jobs/{row.id}/availability",
        json={"version": 1, "deadline_at": "2026-11-02"},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "stale_version"

    missing_confirmation = auth_client.patch(
        f"/crm/jobs/{row.id}/availability",
        json={"version": 2, "state": "closed"},
    )
    assert missing_confirmation.status_code == 422

    closed = auth_client.patch(
        f"/crm/jobs/{row.id}/availability",
        json={
            "version": 2,
            "state": "closed",
            "confirm_state_change": True,
        },
    )
    assert closed.status_code == 200
    closed_data = closed.json()
    assert closed_data["state"] == "closed"
    assert closed_data["confirmed_closed_at"] is not None
    assert closed_data["check_reason"] == "user_confirmed_closed"
    assert closed_data["version"] == 3

    reopened = auth_client.patch(
        f"/crm/jobs/{row.id}/availability",
        json={
            "version": 3,
            "state": "unknown",
            "confirm_state_change": True,
        },
    )
    assert reopened.status_code == 200
    assert reopened.json()["state"] == "unknown"
    assert reopened.json()["confirmed_closed_at"] is None
    assert reopened.json()["check_reason"] == "user_reopened"
    assert reopened.json()["version"] == 4


def test_source_less_track_availability_and_foreign_owner_hidden(auth_client, db_session):
    auth_client.post("/test/reset")
    owner = _test_user(db_session)
    track = JobTrack(
        user_id=owner.id,
        csv_row_id=None,
        url=f"https://source-less.example/jobs/{uuid4()}",
        company="Source Less",
        title="Engineer",
        status="opened",
    )
    foreign = _user(db_session, "foreign")
    foreign_row = _row(db_session, foreign)
    db_session.add(track)
    db_session.commit()
    db_session.refresh(track)

    response = auth_client.patch(
        f"/crm/tracks/{track.id}/availability",
        json={"version": 1, "deadline_at": "2026-10-01"},
    )
    assert response.status_code == 200
    assert response.json()["job_url"] == track.url
    assert response.json()["deadline_local_date"] == "2026-10-01"

    reloaded = auth_client.get(f"/crm/tracks/{track.id}/availability")
    assert reloaded.status_code == 200
    assert reloaded.json()["id"] == response.json()["id"]

    hidden = auth_client.get(f"/crm/jobs/{foreign_row.id}/availability")
    assert hidden.status_code == 404
    assert hidden.json()["detail"]["code"] == "job_not_found"


def test_disabled_check_capability_has_manual_fallback(
    auth_client,
    db_session,
    monkeypatch,
):
    auth_client.post("/test/reset")
    user = _test_user(db_session)
    row = _row(db_session, user)
    monkeypatch.setattr(settings, "JOB_URL_CHECKS_ENABLED", False)

    state = auth_client.get(f"/crm/jobs/{row.id}/availability")
    assert state.status_code == 200
    assert state.json()["checks_enabled"] is False

    check = auth_client.post(f"/crm/jobs/{row.id}/availability/check")
    assert check.status_code == 503
    assert check.json()["detail"]["code"] == "job_url_checks_disabled"

    manual = auth_client.patch(
        f"/crm/jobs/{row.id}/availability",
        json={"version": 1, "deadline_at": "2026-10-02"},
    )
    assert manual.status_code == 200
    assert manual.json()["deadline_local_date"] == "2026-10-02"


def test_concurrent_rate_limit_enforced_across_sessions(engine, db_session):
    user = _user(db_session, "rate-limit")
    availability = JobAvailability(
        user_id=user.id,
        job_url=f"https://rate.example/jobs/{uuid4()}",
        state="unknown",
        version=1,
    )
    db_session.add(availability)
    db_session.commit()
    availability_id = availability.id
    user_id = user.id

    Session = sessionmaker(bind=engine)
    first_session = Session()
    second_session = Session()
    try:
        first_availability = first_session.get(JobAvailability, availability_id)
        first = enqueue_job_check(
            first_session,
            user_id=user_id,
            availability=first_availability,
            requested_at=datetime(2026, 9, 22, 12, 0),
        )
        first_session.commit()
        assert first.status == "pending"

        second_availability = second_session.get(JobAvailability, availability_id)
        with pytest.raises(AvailabilityServiceError) as raised:
            enqueue_job_check(
                second_session,
                user_id=user_id,
                availability=second_availability,
                requested_at=datetime(2026, 9, 22, 12, 5),
            )
        assert raised.value.code == "job_check_url_rate_limited"
        assert raised.value.status_code == 429
        assert 1 <= raised.value.retry_after <= 3600
        second_session.rollback()

        # Persisted state is the source of truth, not process memory.
        assert (
            second_session.query(JobCheckRequest)
            .filter_by(user_id=user_id, availability_id=availability_id)
            .count()
            == 1
        )
    finally:
        first_session.close()
        second_session.close()


def test_daily_check_limit_is_durable(db_session):
    user = _user(db_session, "daily-limit")
    reference = datetime(2026, 9, 22, 12, 0)
    availabilities = []
    for index in range(21):
        availability = JobAvailability(
            user_id=user.id,
            job_url=f"https://daily-{index}.example/jobs/1",
            state="unknown",
            version=1,
        )
        db_session.add(availability)
        availabilities.append(availability)
    db_session.flush()

    for index in range(20):
        request = JobCheckRequest(
            user_id=user.id,
            availability_id=availabilities[index].id,
            requested_at=reference - timedelta(minutes=index),
            status="done",
            completed_at=reference - timedelta(minutes=index),
        )
        db_session.add(request)
    db_session.commit()

    with pytest.raises(AvailabilityServiceError) as raised:
        enqueue_job_check(
            db_session,
            user_id=user.id,
            availability=availabilities[20],
            requested_at=reference,
        )
    assert raised.value.code == "job_check_daily_rate_limited"
    assert raised.value.retry_after is not None
    db_session.rollback()


def test_ambiguous_network_response_never_closes_or_removes_history(db_session):
    user = _user(db_session, "ambiguous")
    url = f"https://ambiguous.example/jobs/{uuid4()}"
    track = JobTrack(
        user_id=user.id,
        url=url,
        company="Ambiguous Co",
        title="Engineer",
        status="applied",
        applied_at=datetime(2026, 9, 20, 12, 0),
    )
    availability = JobAvailability(
        user_id=user.id,
        job_url=url,
        state="available",
        version=2,
    )
    db_session.add_all([track, availability])
    db_session.flush()
    request = JobCheckRequest(
        user_id=user.id,
        availability_id=availability.id,
        requested_at=datetime(2026, 9, 22, 12, 0),
        status="running",
        lease_until=datetime(2026, 9, 22, 12, 2),
    )
    db_session.add(request)
    db_session.commit()

    finish_job_check_request(
        db_session,
        request_id=request.id,
        result=SafeFetchResult(http_status=403),
        checked_at=datetime(2026, 9, 22, 12, 1),
    )
    db_session.commit()
    db_session.expire_all()

    stored = db_session.get(JobAvailability, availability.id)
    history = db_session.get(JobTrack, track.id)
    assert stored.state == "unknown"
    assert stored.confirmed_closed_at is None
    assert stored.check_reason == "http_403"
    assert history.status == "applied"
    assert history.applied_at == datetime(2026, 9, 20, 12, 0)


def test_closed_job_deadline_excluded_but_manual_task_retained(db_session):
    user = _user(db_session, "closed-deadline")
    url = f"https://closed-deadline.example/jobs/{uuid4()}"
    row = CsvRow(
        user_id=user.id,
        upload_batch_id=str(uuid4()),
        url=url,
        company_guess="Closed Co",
        title="Engineer",
    )
    availability = JobAvailability(
        user_id=user.id,
        job_url=url,
        deadline_at=datetime(2026, 9, 22, 18, 0),
        deadline_source="user",
        state="closed",
        confirmed_closed_at=datetime(2026, 9, 21, 12, 0),
        check_reason="user_confirmed_closed",
        version=3,
    )
    db_session.add_all([row, availability])
    db_session.flush()
    manual = WorkItem(
        user_id=user.id,
        row_id=row.id,
        description="Keep manual research task",
        due_at=datetime(2026, 9, 22, 17, 0, tzinfo=timezone.utc),
        priority=1,
        state="pending",
        version=1,
    )
    db_session.add(manual)
    db_session.flush()

    queue = build_today_queue(
        db_session,
        user_id=user.id,
        timezone_name="UTC",
        secret_key="closed-deadline-secret",
        now=datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc),
    )
    keys = {item["action_key"] for item in queue["items"]}

    assert f"manual:{manual.id}" in keys
    assert deadline_action_key(availability.id, availability.deadline_at) not in keys


def test_deadline_edit_updates_today_and_unsent_reminder(auth_client, db_session):
    auth_client.post("/test/reset")
    user = _test_user(db_session)
    user.timezone = "UTC"
    preference = ReminderPreference(
        user_id=user.id,
        enabled=True,
        channel="in_app",
        local_time="09:00",
        quiet_start="21:00",
        quiet_end="08:00",
    )
    url = f"https://deadline-reminder.example/jobs/{uuid4()}"
    row = CsvRow(
        user_id=user.id,
        upload_batch_id=str(uuid4()),
        url=url,
        company_guess="Deadline Co",
        title="Engineer",
    )
    track = JobTrack(
        user_id=user.id,
        url=url,
        company="Deadline Co",
        title="Engineer",
        status="follow_up",
        follow_up_at=datetime(2026, 9, 22, 16, 0),
    )
    db_session.add_all([preference, row, track])
    db_session.commit()

    patched = auth_client.patch(
        f"/crm/jobs/{row.id}/availability",
        json={"version": 1, "deadline_at": "2026-09-22"},
    )
    assert patched.status_code == 200
    availability_id = patched.json()["id"]

    db_session.expire_all()
    queue = build_today_queue(
        db_session,
        user_id=user.id,
        timezone_name="UTC",
        secret_key="deadline-reminder-secret",
        now=datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc),
    )
    deadline_items = [
        item for item in queue["items"]
        if item["type"] == "deadline" and item["id"] == availability_id
    ]
    assert len(deadline_items) == 1
    assert deadline_items[0]["availability_state"] == "unknown"

    deliveries = (
        db_session.query(ReminderDelivery)
        .filter_by(user_id=user.id, track_id=track.id)
        .all()
    )
    assert len(deliveries) == 1
    assert deliveries[0].status == "pending"

    closed = auth_client.patch(
        f"/crm/jobs/{row.id}/availability",
        json={
            "version": patched.json()["version"],
            "state": "closed",
            "confirm_state_change": True,
        },
    )
    assert closed.status_code == 200

    db_session.expire_all()
    delivery = db_session.get(ReminderDelivery, deliveries[0].id)
    assert delivery.status == "cancelled"


def test_restore_preserves_user_confirmation(db_session):
    source = _user(db_session, "closed-backup-source")
    destination = _user(db_session, "closed-backup-destination")
    confirmed_at = datetime(2026, 9, 22, 10, 30)
    url = f"https://closed-backup.example/jobs/{uuid4()}"
    db_session.add(
        JobAvailability(
            user_id=source.id,
            job_url=url,
            deadline_at=datetime(2026, 10, 1, 23, 59, 59),
            deadline_source="user",
            state="closed",
            confirmed_closed_at=confirmed_at,
            check_reason="user_confirmed_closed",
            version=5,
        )
    )
    db_session.commit()

    payload = export_backup_v2(db_session, source.id)
    document = validate_backup_v2(payload)
    result = restore_backup_v2(
        db_session,
        destination.id,
        document,
        mode="merge_missing",
    )
    assert result["counts"]["job_availability"]["created"] == 1

    restored = (
        db_session.query(JobAvailability)
        .filter_by(user_id=destination.id, job_url=url)
        .one()
    )
    assert restored.state == "closed"
    assert restored.confirmed_closed_at == confirmed_at
    assert restored.check_reason == "user_confirmed_closed"
    assert restored.version == 5


def test_deadline_action_snooze_is_owner_scoped(auth_client, db_session):
    auth_client.post("/test/reset")
    user = _test_user(db_session)
    url = f"https://snooze-deadline.example/jobs/{uuid4()}"
    availability = JobAvailability(
        user_id=user.id,
        job_url=url,
        deadline_at=datetime.utcnow() + timedelta(hours=1),
        deadline_source="user",
        state="unknown",
        version=2,
    )
    db_session.add(availability)
    db_session.commit()
    action_key = deadline_action_key(availability.id, availability.deadline_at)

    snooze = auth_client.post(
        "/crm/today/snooze",
        json={
            "action_key": action_key,
            "until": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
            "version": 1,
        },
    )
    assert snooze.status_code == 200
    assert snooze.json()["action_key"] == action_key
    assert snooze.json()["version"] == 2
