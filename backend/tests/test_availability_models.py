from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.availability_schemas import (
    JOB_CHECK_REQUEST_RETENTION_DAYS,
    apply_checker_evidence,
    check_request_retention_cutoff,
    deadline_action_key,
    deadline_today_eligible,
    parse_deadline_input,
)
from app.backup_schemas import validate_backup_v2
from app.models import CsvRow, JobAvailability, JobCheckRequest, User
from app.services.availability import apply_checker_result, prune_job_check_requests
from app.services.backups import export_backup_v2, restore_backup_v2


def _user(db_session, prefix: str, timezone_name: str = "UTC") -> User:
    user = User(
        email=f"{prefix}-{uuid4()}@example.test",
        timezone=timezone_name,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_user_closed_not_overwritten_by_reachable(db_session):
    user = _user(db_session, "closed-precedence")
    availability = JobAvailability(
        user_id=user.id,
        job_url=f"https://closed.example/jobs/{uuid4()}",
        state="closed",
        confirmed_closed_at=datetime(2026, 9, 22, 11, 0),
        check_reason="user_confirmed_closed",
        version=4,
    )
    db_session.add(availability)
    db_session.commit()

    evidence = apply_checker_result(
        availability,
        checked_at=datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc),
        http_status=200,
    )
    db_session.commit()
    assert availability.state == "closed"
    assert availability.confirmed_closed_at == datetime(2026, 9, 22, 11, 0)
    assert availability.version == 4
    assert evidence.state == "closed"
    assert evidence.check_reason == "user_confirmed_closed"

    evidence = apply_checker_evidence("closed", http_status=200)
    assert evidence.state == "closed"
    assert evidence.check_reason == "user_confirmed_closed"

    blocked = apply_checker_evidence("closed", failure_reason="timeout")
    assert blocked.state == "closed"
    assert blocked.check_reason == "user_confirmed_closed"

    assert apply_checker_evidence("unknown", http_status=200).state == "available"
    assert apply_checker_evidence("available", http_status=404).state == "unavailable"
    assert apply_checker_evidence("available", http_status=410).state == "unavailable"
    assert apply_checker_evidence("available", http_status=403).state == "unknown"
    assert apply_checker_evidence("available", http_status=429).state == "unknown"
    assert apply_checker_evidence("available", failure_reason="timeout").state == "unknown"


def test_date_only_conversion_visible_and_dst_safe():
    spring = parse_deadline_input("2026-03-08", "America/New_York")
    assert spring.date_only is True
    assert spring.deadline_at == datetime(2026, 3, 9, 3, 59, 59, 999999)
    assert "23:59:59.999999 America/New_York" in spring.interpretation

    fall = parse_deadline_input("2026-11-01", "America/New_York")
    assert fall.date_only is True
    assert fall.deadline_at == datetime(2026, 11, 2, 4, 59, 59, 999999)
    assert "23:59:59.999999 America/New_York" in fall.interpretation

    timestamp = parse_deadline_input("2026-09-22T18:30:00+05:30", "Asia/Kolkata")
    assert timestamp.date_only is False
    assert timestamp.deadline_at == datetime(2026, 9, 22, 13, 0, 0)


def test_deadline_today_eligibility_matches_local_day_and_terminal_states():
    reference = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)

    overdue = datetime(2026, 9, 21, 20, 0)
    today = datetime(2026, 9, 22, 20, 0)
    tomorrow = datetime(2026, 9, 23, 20, 0)

    assert deadline_today_eligible(
        deadline_at=overdue,
        availability_state="unknown",
        application_status=None,
        timezone_name="UTC",
        reference=reference,
    )
    assert deadline_today_eligible(
        deadline_at=today,
        availability_state="available",
        application_status="interview",
        timezone_name="UTC",
        reference=reference,
    )
    assert not deadline_today_eligible(
        deadline_at=tomorrow,
        availability_state="available",
        application_status=None,
        timezone_name="UTC",
        reference=reference,
    )
    assert not deadline_today_eligible(
        deadline_at=today,
        availability_state="closed",
        application_status=None,
        timezone_name="UTC",
        reference=reference,
    )
    for terminal in ("rejected", "offer", "not_applying"):
        assert not deadline_today_eligible(
            deadline_at=today,
            availability_state="unknown",
            application_status=terminal,
            timezone_name="UTC",
            reference=reference,
        )


def test_source_delete_preserves_availability(db_session):
    user = _user(db_session, "availability-delete")
    url = f"https://availability.example/jobs/{uuid4()}"
    row = CsvRow(user_id=user.id, upload_batch_id=str(uuid4()), url=url)
    availability = JobAvailability(
        user_id=user.id,
        job_url=url,
        deadline_at=datetime(2026, 10, 1, 23, 59, 59),
        deadline_source="user",
        state="unknown",
        version=1,
    )
    db_session.add_all([row, availability])
    db_session.commit()
    availability_id = availability.id

    db_session.delete(row)
    db_session.commit()
    db_session.expire_all()

    preserved = db_session.get(JobAvailability, availability_id)
    assert preserved is not None
    assert preserved.job_url == url
    assert preserved.deadline_source == "user"


def test_backup_keeps_deadline_source(db_session):
    source = _user(db_session, "availability-source", "America/New_York")
    destination = _user(db_session, "availability-destination", "UTC")
    url = f"https://backup-availability.example/jobs/{uuid4()}"
    availability = JobAvailability(
        user_id=source.id,
        job_url=url,
        deadline_at=datetime(2026, 11, 2, 4, 59, 59, 999999),
        deadline_source="import",
        state="unavailable",
        last_checked_at=datetime(2026, 9, 22, 12, 0),
        check_reason="http_404",
        version=3,
    )
    transient = JobCheckRequest(
        user_id=source.id,
        availability=availability,
        requested_at=datetime(2026, 9, 22, 12, 1),
        status="failed",
        completed_at=datetime(2026, 9, 22, 12, 1, 2),
        error_code="http_404",
    )
    db_session.add_all([availability, transient])
    db_session.commit()

    payload = export_backup_v2(db_session, source.id)
    assert payload["schema_revision"] == "2.11.0"
    assert len(payload["sections"]["job_availability"]) == 1
    exported = payload["sections"]["job_availability"][0]
    assert exported["job_url"] == url
    assert exported["deadline_source"] == "import"
    assert exported["state"] == "unavailable"
    assert "job_check_requests" not in payload["sections"]

    document = validate_backup_v2(payload)
    result = restore_backup_v2(
        db_session,
        destination.id,
        document,
        mode="merge_missing",
    )
    assert result["counts"]["job_availability"]["created"] == 1

    db_session.expire_all()
    restored = db_session.query(JobAvailability).filter_by(
        user_id=destination.id,
        job_url=url,
    ).one()
    assert restored.deadline_source == "import"
    assert restored.deadline_at == availability.deadline_at
    assert restored.state == "unavailable"
    assert restored.check_reason == "http_404"
    assert db_session.query(JobCheckRequest).filter_by(user_id=destination.id).count() == 0


def test_check_request_metadata_retention_cutoff_is_seven_days(db_session):
    reference = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
    cutoff = check_request_retention_cutoff(reference)
    assert JOB_CHECK_REQUEST_RETENTION_DAYS == 7
    assert cutoff == datetime(2026, 9, 15, 12, 0)

    user = _user(db_session, "request-retention")
    availability = JobAvailability(
        user_id=user.id,
        job_url=f"https://retention.example/jobs/{uuid4()}",
        state="unknown",
    )
    db_session.add(availability)
    db_session.flush()
    old_request = JobCheckRequest(
        user_id=user.id,
        availability_id=availability.id,
        requested_at=cutoff - timedelta(microseconds=1),
        status="done",
        completed_at=cutoff - timedelta(microseconds=1),
    )
    boundary_request = JobCheckRequest(
        user_id=user.id,
        availability_id=availability.id,
        requested_at=cutoff,
        status="done",
        completed_at=cutoff,
    )
    db_session.add_all([old_request, boundary_request])
    db_session.commit()

    assert prune_job_check_requests(db_session, reference=reference) == 1
    db_session.commit()
    assert db_session.query(JobCheckRequest).filter_by(user_id=user.id).count() == 1

    key = deadline_action_key(availability.id, datetime(2026, 9, 22, 18, 30, tzinfo=timezone.utc))
    assert key == f"deadline:{availability.id}:2026-09-22T18:30:00Z"
