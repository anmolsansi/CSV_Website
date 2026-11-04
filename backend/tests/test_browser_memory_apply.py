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


def test_ext_17_replay_preserves_advanced_applied_status_and_original_time(db_session):
    owner = _owner(db_session)
    prior = JobTrack(
        user_id=owner.id,
        url="https://jobs.example.test/17/rejected?role=123&utm_campaign=old",
        company="Curated Employer", title="Curated Role", notes="Keep review notes",
        status="rejected", applied_at=datetime(2026, 1, 2, 9, 30),
    )
    apply_persisted_job_identity(prior)
    db_session.add(prior)
    db_session.commit()

    retry = _apply(
        db_session, owner.id,
        "https://jobs.example.test/17/rejected?role=123&gclid=new",
        now=datetime(2026, 10, 5, 10),
    )
    assert retry.as_response() == {
        "protocol_version": 1, "account_id": owner.id,
        "application_id": prior.id, "created": False, "already_applied": True,
        "applied_at": "2026-01-02T09:30:00Z",
    }
    db_session.commit()
    db_session.refresh(prior)
    assert (prior.status, prior.notes, prior.company, prior.title) == (
        "rejected", "Keep review notes", "Curated Employer", "Curated Role",
    )
    assert db_session.query(JobLifecycleEvent).filter_by(
        user_id=owner.id, job_track_id=prior.id, kind="first_applied",
    ).count() == 0


def test_ext_17_possible_company_match_never_merges_distinct_role(db_session):
    owner = _owner(db_session)
    earlier = JobTrack(
        user_id=owner.id, url="https://jobs.example.test/17/role-A",
        company="Acme Corp", title="Backend Engineer", status="archived",
        applied_at=datetime(2026, 1, 2, 11),
    )
    apply_persisted_job_identity(earlier)
    db_session.add(earlier)
    db_session.commit()
    newer = _apply(
        db_session, owner.id, "https://jobs.example.test/17/role-B",
        now=datetime(2026, 10, 6, 11),
    )
    assert newer.created is True and newer.already_applied is False
    assert newer.application_id != earlier.id
    db_session.commit()
    db_session.refresh(earlier)
    assert earlier.status == "archived"
    assert earlier.applied_at == datetime(2026, 1, 2, 11)
    assert db_session.query(JobTrack).filter_by(user_id=owner.id).count() == 2
    assert db_session.query(JobLifecycleEvent).filter_by(
        user_id=owner.id, job_track_id=newer.application_id, kind="first_applied",
    ).count() == 1


def test_ext_18_lost_response_replay_keeps_frozen_result_and_one_event(db_session):
    owner = _owner(db_session)
    db_session.commit()
    key = str(uuid4())
    url = "https://jobs.example.test/18/retry?role=4"
    kwargs = dict(
        user_id=owner.id, url=url, company="Acme Corp",
        title="Backend Engineer", confirmed=True, request_key=key,
    )
    first = browser_memory.apply_browser_application_once(
        db_session, now=datetime(2026, 10, 1, 8), **kwargs,
    )
    db_session.commit()
    replay = browser_memory.apply_browser_application_once(
        db_session, now=datetime(2026, 10, 2, 9), **kwargs,
    )
    db_session.commit()
    assert replay == first
    assert first["created"] is True and first["already_applied"] is False
    assert first["applied_at"] == "2026-10-01T08:00:00Z"
    assert db_session.query(BrowserApplyReceipt).filter_by(user_id=owner.id).count() == 1
    assert db_session.query(JobTrack).filter_by(user_id=owner.id).count() == 1
    assert db_session.query(JobLifecycleEvent).filter_by(
        user_id=owner.id, kind="first_applied",
    ).count() == 1


def test_ext_18_changed_payload_conflicts_but_key_is_owner_scoped(db_session):
    owner, other = _owner(db_session), _owner(db_session)
    db_session.commit()
    key = str(uuid4())
    original = dict(
        url="https://jobs.example.test/18/a", company="Acme Corp",
        title="Backend Engineer", confirmed=True, request_key=key,
    )
    saved = browser_memory.apply_browser_application_once(
        db_session, user_id=owner.id, **original,
    )
    db_session.commit()
    for change in ({"url": "https://jobs.example.test/18/b"}, {"title": "Designer"}):
        with pytest.raises(browser_memory.BrowserVisitConflict) as caught:
            browser_memory.apply_browser_application_once(
                db_session, user_id=owner.id, **{**original, **change},
            )
        assert caught.value.code == "idempotency_conflict"
        db_session.rollback()
    foreign = browser_memory.apply_browser_application_once(
        db_session, user_id=other.id, **original,
    )
    db_session.commit()
    assert foreign["account_id"] == other.id
    assert foreign["application_id"] != saved["application_id"]
    assert db_session.query(BrowserApplyReceipt).filter_by(request_key=key).count() == 2


def test_ext_18_deleted_target_and_rollback_have_no_false_receipt(db_session, monkeypatch):
    owner = _owner(db_session)
    db_session.commit()
    url = "https://jobs.example.test/18/failure"
    key = str(uuid4())
    original = browser_memory.apply_job_track_changes

    def late_failure(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("late failure after event")

    monkeypatch.setattr(browser_memory, "apply_job_track_changes", late_failure)
    with pytest.raises(RuntimeError, match="late failure"):
        browser_memory.apply_browser_application_once(
            db_session, user_id=owner.id, url=url, company="Acme Corp",
            title="Backend Engineer", confirmed=True, request_key=key,
        )
    db_session.rollback()
    assert db_session.query(BrowserApplyReceipt).filter_by(user_id=owner.id).count() == 0
    assert db_session.query(JobLifecycleEvent).filter_by(user_id=owner.id).count() == 0
    monkeypatch.setattr(browser_memory, "apply_job_track_changes", original)
    saved = browser_memory.apply_browser_application_once(
        db_session, user_id=owner.id, url=url, company="Acme Corp",
        title="Backend Engineer", confirmed=True, request_key=key,
    )
    db_session.commit()
    db_session.query(JobTrack).filter_by(id=saved["application_id"], user_id=owner.id).delete()
    db_session.commit()
    with pytest.raises(browser_memory.BrowserVisitConflict) as caught:
        browser_memory.apply_browser_application_once(
            db_session, user_id=owner.id, url=url, company="Acme Corp",
            title="Backend Engineer", confirmed=True, request_key=key,
        )
    assert caught.value.code == "application_deleted"
    db_session.rollback()


def test_ext_18_receipt_expiry_and_capacity_preserve_application(db_session, monkeypatch):
    owner = _owner(db_session)
    db_session.commit()
    request = dict(
        user_id=owner.id, url="https://jobs.example.test/18/cap",
        company="Acme Corp", title="Backend Engineer", confirmed=True,
    )
    key = str(uuid4())
    first = browser_memory.apply_browser_application_once(
        db_session, request_key=key, now=datetime(2026, 1, 1, 10), **request,
    )
    db_session.commit()
    monkeypatch.setattr(browser_memory, "MAX_BROWSER_APPLY_RECEIPTS_PER_OWNER", 1)
    other_key = str(uuid4())
    with pytest.raises(browser_memory.BrowserVisitConflict) as caught:
        browser_memory.apply_browser_application_once(
            db_session, request_key=other_key, now=datetime(2026, 1, 2, 10), **request,
        )
    assert caught.value.code == "receipt_limit_reached"
    db_session.rollback()
    after_expiry = browser_memory.apply_browser_application_once(
        db_session, request_key=other_key, now=datetime(2026, 3, 1, 10), **request,
    )
    db_session.commit()
    assert after_expiry["application_id"] == first["application_id"]
    assert after_expiry["already_applied"] is True
    assert db_session.query(BrowserApplyReceipt).filter_by(user_id=owner.id).count() == 1
    assert db_session.query(JobTrack).filter_by(user_id=owner.id).count() == 1
