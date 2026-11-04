"""EXT-16: explicit browser application service, no CSV capture or synthetic open."""
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy.orm import sessionmaker

from app.browser_memory_schemas import BrowserMemoryValidationError
from app.models import (
    BrowserApplyReceipt, CsvRow, JobLifecycleEvent, JobTrack, JobVisit,
    SearchSession, UrlHistory, User,
)
from app.services import browser_memory
from app.services.job_identity import apply_persisted_job_identity


def _owner(session):
    owner = User(email=f"ext16-{uuid4().hex}@example.test")
    session.add(owner)
    session.flush()
    return owner


def _apply(session, user_id, url, **kwargs):
    return browser_memory.record_browser_application(
        session, user_id=user_id, url=url, company="Acme Corp",
        title="Backend Engineer", confirmed=True, **kwargs,
    )


def test_ext_16_new_explicit_apply_records_one_application_not_a_visit(db_session):
    owner = _owner(db_session)
    db_session.commit()
    url = "https://jobs.example.test/roles/16-new?req=abc"
    result = _apply(
        db_session, owner.id, url, now=datetime(2026, 10, 1, 9, 0, 0),
    )
    assert result.as_response() == {
        "protocol_version": 1, "account_id": owner.id,
        "application_id": result.application_id, "created": True,
        "already_applied": False, "applied_at": "2026-10-01T09:00:00Z",
    }
    db_session.commit()
    track = db_session.query(JobTrack).filter_by(
        user_id=owner.id, id=result.application_id,
    ).one()
    assert (track.company, track.title, track.status) == (
        "Acme Corp", "Backend Engineer", "applied",
    )
    assert track.csv_row_id is None
    assert track.opened_at is None and track.last_opened_at is None
    assert track.open_count == 0
    assert track.applied_at == datetime(2026, 10, 1, 9, 0, 0)
    events = db_session.query(JobLifecycleEvent).filter_by(
        user_id=owner.id, job_track_id=track.id,
    ).all()
    assert len(events) == 1
    assert (events[0].kind, events[0].source) == ("first_applied", "browser_memory")
    for model in (CsvRow, JobVisit, UrlHistory, SearchSession, BrowserApplyReceipt):
        assert db_session.query(model).filter(model.user_id == owner.id).count() == 0


def test_ext_16_existing_exact_unapplied_track_keeps_curated_fields(db_session):
    owner = _owner(db_session)
    url = "https://jobs.example.test/roles/16-existing"
    track = JobTrack(
        user_id=owner.id, url=url, company="Original Company",
        title="Original Job Title", notes="Keep this private note",
        status="opened", opened_at=datetime(2026, 7, 4, 9, 0, 0),
        last_opened_at=datetime(2026, 7, 4, 9, 0, 0), open_count=3,
    )
    apply_persisted_job_identity(track)
    db_session.add(track)
    db_session.commit()
    result = _apply(
        db_session, owner.id, url, now=datetime(2026, 10, 1, 12, 0, 0),
    )
    assert result.application_id == track.id
    assert result.created is False and result.already_applied is False
    db_session.commit()
    db_session.refresh(track)
    assert track.status == "applied"
    assert track.applied_at == datetime(2026, 10, 1, 12, 0, 0)
    assert (track.company, track.title, track.notes) == (
        "Original Company", "Original Job Title", "Keep this private note",
    )
    assert track.open_count == 3
    assert track.opened_at == datetime(2026, 7, 4, 9, 0, 0)
    assert {event.kind for event in db_session.query(JobLifecycleEvent).filter_by(
        user_id=owner.id, job_track_id=track.id,
    ).all()} == {"first_applied", "status_changed"}


def test_ext_16_invalid_confirmation_and_rollback_leave_no_partial_state(
    db_session, monkeypatch,
):
    owner = _owner(db_session)
    db_session.commit()
    url = "https://jobs.example.test/roles/16-rollback"
    for value in (False, "true", None, 1):
        with pytest.raises(BrowserMemoryValidationError):
            browser_memory.record_browser_application(
                db_session, user_id=owner.id, url=url,
                company="Acme", title="Engineer", confirmed=value,
            )
    original = browser_memory.apply_job_track_changes

    def fail_after_lifecycle(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("injected transaction failure")

    monkeypatch.setattr(browser_memory, "apply_job_track_changes", fail_after_lifecycle)
    with pytest.raises(RuntimeError, match="injected"):
        _apply(db_session, owner.id, url)
    db_session.rollback()

    Fresh = sessionmaker(bind=db_session.get_bind())
    with Fresh() as fresh:
        assert fresh.query(JobTrack).filter_by(user_id=owner.id, url=url).count() == 0
        assert fresh.query(JobLifecycleEvent).filter_by(
            user_id=owner.id, job_url=url,
        ).count() == 0
        assert fresh.query(CsvRow).filter_by(user_id=owner.id).count() == 0
        assert fresh.query(JobVisit).filter_by(user_id=owner.id).count() == 0


def test_ext_16_canonical_applied_is_reused_without_status_reset(db_session):
    owner, foreign = _owner(db_session), _owner(db_session)
    old_url = "https://jobs.example.test/roles/16-same?req=1&utm_source=old"
    old = JobTrack(
        user_id=owner.id, url=old_url, company="Acme Corp",
        title="Backend Engineer", status="interview",
        notes="Already had an interview",
        applied_at=datetime(2026, 5, 3, 13, 0, 0),
    )
    apply_persisted_job_identity(old)
    other = JobTrack(
        user_id=foreign.id, url="https://jobs.example.test/roles/16-foreign",
        company="Acme Corp", title="Backend Engineer", status="applied",
        applied_at=datetime(2026, 4, 1, 12, 0, 0),
    )
    apply_persisted_job_identity(other)
    db_session.add_all([old, other])
    db_session.commit()
    variant = "https://jobs.example.test/roles/16-same?req=1&gclid=abc"
    result = _apply(db_session, owner.id, variant)
    assert result.as_response() == {
        "protocol_version": 1, "account_id": owner.id,
        "application_id": old.id, "created": False,
        "already_applied": True, "applied_at": "2026-05-03T13:00:00Z",
    }
    db_session.commit()
    db_session.refresh(old)
    assert old.status == "interview" and old.notes == "Already had an interview"
    assert db_session.query(JobTrack).filter_by(user_id=owner.id).count() == 1
    assert db_session.query(JobLifecycleEvent).filter_by(user_id=owner.id).count() == 0
