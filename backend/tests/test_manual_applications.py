"""Phase 3 manual submission: date truth, ownership and transactional writes."""
from datetime import datetime
from uuid import uuid4

import pytest

from app.models import (
    BrowserApplyReceipt, CsvRow, JobLifecycleEvent, JobTrack, JobVisit,
    ManualApplicationReceipt, User,
)
from app.services.job_identity import apply_persisted_job_identity


def _payload(url=None, **overrides):
    values = {
        "url": url or f"https://jobs.example.test/roles/{uuid4().hex}",
        "company": "Acme",
        "title": "Senior Engineer",
        "applied_at": "2026-10-01T12:30:00+05:30",
        "confirmed": True,
    }
    values.update(overrides)
    return values


def _save(client, payload, key=None):
    return client.post(
        "/crm/applications", json=payload,
        headers={"Idempotency-Key": key or str(uuid4())},
    )


@pytest.fixture
def manual_session(client, db_session):
    email = f"al-phase3-{uuid4().hex}@example.test"
    login = client.post("/auth/dev-login", json={"email": email})
    assert login.status_code == 200
    return client, db_session.query(User).filter_by(email=email).one()


def test_manual_create_is_dated_atomic_and_not_a_visit(manual_session, db_session):
    auth_client, owner = manual_session
    url = f"https://jobs.example.test/manual/{uuid4().hex}"
    result = _save(auth_client, _payload(
        url, notes="Interview prep", follow_up_at="2026-11-30T18:00:00Z",
    ))
    assert result.status_code == 201, result.text
    saved = result.json()
    assert saved["created"] is True
    assert saved["replayed"] is False
    assert saved["status"] == "applied"
    assert saved["applied_at"] == "2026-10-01T07:00:00Z"

    db_session.expire_all()
    track = db_session.query(JobTrack).filter_by(
        user_id=owner.id, id=saved["application_id"],
    ).one()
    assert track.url == url and track.csv_row_id is None
    assert (track.company, track.title, track.notes) == (
        "Acme", "Senior Engineer", "Interview prep",
    )
    assert (track.open_count, track.opened_at, track.last_opened_at) == (0, None, None)
    assert track.applied_at == datetime(2026, 10, 1, 7)
    assert track.follow_up_at == datetime(2026, 11, 30, 18)
    assert [
        event.kind for event in db_session.query(JobLifecycleEvent).filter_by(
            user_id=owner.id, job_track_id=track.id,
        ).order_by(JobLifecycleEvent.id)
    ] == ["first_applied", "status_changed"]
    for table in (CsvRow, JobVisit, BrowserApplyReceipt):
        assert db_session.query(table).filter_by(user_id=owner.id).count() == 0
    assert db_session.query(ManualApplicationReceipt).filter_by(user_id=owner.id).count() == 1
    lifetime = auth_client.get("/crm/applications", params={"applied_only": True})
    assert lifetime.status_code == 200
    assert track.id in [row["id"] for row in lifetime.json()["rows"]]


def test_existing_exact_unapplied_track_keeps_curated_fields_and_stage(
    manual_session, db_session,
):
    auth_client, owner = manual_session
    url = f"https://jobs.example.test/open/{uuid4().hex}"
    tracked = JobTrack(
        user_id=owner.id, url=url, company="Curated employer",
        title="Curated role", notes="Important note", status="interview",
        opened_at=datetime(2026, 9, 1, 8), open_count=4,
    )
    apply_persisted_job_identity(tracked)
    db_session.add(tracked)
    db_session.commit()
    result = _save(auth_client, _payload(
        url, company="Overwrite?", title="Overwrite?", notes="Other note",
        follow_up_at="2026-12-01T00:00:00Z",
    ))
    assert result.status_code == 200, result.text
    assert result.json()["application_id"] == tracked.id
    assert result.json()["created"] is False
    db_session.refresh(tracked)
    assert (tracked.company, tracked.title, tracked.notes) == (
        "Curated employer", "Curated role", "Important note",
    )
    assert tracked.status == "interview"
    assert tracked.applied_at == datetime(2026, 10, 1, 7)
    assert tracked.opened_at == datetime(2026, 9, 1, 8)
    assert tracked.follow_up_at == datetime(2026, 12, 1, 0)
    first = db_session.query(JobLifecycleEvent).filter_by(
        user_id=owner.id, job_track_id=tracked.id, kind="first_applied",
    ).all()
    assert len(first) == 1


@pytest.mark.parametrize("override,field", [
    ({"confirmed": False}, "confirmed"),
    ({"confirmed": "true"}, "confirmed"),
    ({"applied_at": "2026-10-01"}, "applied_at"),
    ({"applied_at": "2026-10-01T12:30:00"}, "applied_at"),
    ({"applied_at": "2999-01-01T00:00:00Z"}, "applied_at"),
    ({"follow_up_at": "2026-12-01"}, "follow_up_at"),
    ({"company": "  "}, "company"),
    ({"title": ""}, "title"),
    ({"url": "file:///etc/passwd"}, "url"),
    ({"url": "http://localhost/private"}, "url"),
    ({"url": "https://jobs.example.test/path?access_token=x"}, "url"),
    ({"notes": "x" * 20001}, "notes"),
    ({"unrecognized_field": "yes"}, "unrecognized_field"),
])
def test_manual_invalid_payload_has_no_side_effect(manual_session, db_session, override, field):
    auth_client, owner = manual_session
    bad = _save(auth_client, _payload(**override))
    assert bad.status_code == 422, bad.text
    assert bad.json()["detail"]["fields"][0]["field"] == field
    assert db_session.query(ManualApplicationReceipt).filter_by(user_id=owner.id).count() == 0
    assert db_session.query(JobTrack).filter_by(user_id=owner.id).count() == 0


def test_missing_or_noncanonical_idempotency_key_is_rejected(manual_session):
    auth_client, _owner = manual_session
    payload = _payload()
    absent = auth_client.post("/crm/applications", json=payload)
    assert absent.status_code == 400, absent.text
    invalid = _save(auth_client, payload, key="not-a-uuid")
    assert invalid.status_code == 400
    assert invalid.json()["detail"]["code"] == "invalid_idempotency_key"


def test_requires_authentication(client):
    response = _save(client, _payload())
    assert response.status_code in (401, 403)


def test_failure_after_lifecycle_rolls_back_track_event_and_receipt(
    manual_session, db_session, monkeypatch,
):
    from app.services import manual_applications

    auth_client, owner = manual_session
    original = manual_applications.apply_job_track_changes

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("injected failure after lifecycle event")

    monkeypatch.setattr(manual_applications, "apply_job_track_changes", fail)
    failed = _save(auth_client, _payload())
    assert failed.status_code == 500
    db_session.expire_all()
    assert db_session.query(JobTrack).filter_by(user_id=owner.id).count() == 0
    assert db_session.query(JobLifecycleEvent).filter_by(user_id=owner.id).count() == 0
    assert db_session.query(ManualApplicationReceipt).filter_by(user_id=owner.id).count() == 0
