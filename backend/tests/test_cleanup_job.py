from datetime import datetime, timedelta
from threading import Event, Thread
from uuid import uuid4

import pytest
from sqlalchemy import text

import app.jobs as jobs_module
from app.database import engine
from app.models import CsvRow, User
from app.services.retention import (
    CleanupResult,
    RetentionJobError,
    archive_eligible_rows,
)


def _create_user(db_session, *, retention_days):
    user = User(
        email=f"jg013-{uuid4().hex}@jobgrid.dev",
        retention_days=retention_days,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _create_row(
    db_session,
    user,
    *,
    clicked_at,
    created_at=None,
):
    token = uuid4().hex
    row = CsvRow(
        user_id=user.id,
        upload_batch_id=f"jg013-{token[:24]}",
        url=f"https://example.com/{token}/job",
        created_at=created_at or datetime.utcnow(),
        clicked=clicked_at is not None,
        clicked_at=clicked_at,
        archived=False,
        archived_at=None,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row


def test_old_unvisited_is_preserved(db_session):
    now = datetime(2026, 9, 20, 12, 0, 0)
    user = _create_user(db_session, retention_days=30)
    old_unvisited = _create_row(
        db_session,
        user,
        clicked_at=None,
        created_at=now - timedelta(days=120),
    )
    eligible = _create_row(
        db_session,
        user,
        clicked_at=now - timedelta(days=31),
    )

    result = archive_eligible_rows(db_session, now=now)

    assert result.scanned == 1
    assert result.archived == 1
    assert result.failed == 0
    db_session.expire_all()
    assert db_session.get(CsvRow, old_unvisited.id).archived is False
    assert db_session.get(CsvRow, old_unvisited.id).archived_at is None
    assert db_session.get(CsvRow, eligible.id).archived is True
    assert db_session.get(CsvRow, eligible.id).archived_at == now


def test_disabled_account_policy_archives_nothing(db_session):
    now = datetime(2026, 9, 20, 12, 0, 0)
    disabled_users = [
        _create_user(db_session, retention_days=None),
        _create_user(db_session, retention_days=0),
    ]
    rows = [
        _create_row(
            db_session,
            user,
            clicked_at=now - timedelta(days=365),
        )
        for user in disabled_users
    ]

    result = archive_eligible_rows(db_session, now=now)

    assert result.as_dict() | {"duration_ms": 0} == {
        "scanned": 0,
        "archived": 0,
        "skipped": 0,
        "failed": 0,
        "duration_ms": 0,
    }
    db_session.expire_all()
    assert all(db_session.get(CsvRow, row.id).archived is False for row in rows)


def test_clock_boundary_is_inclusive_and_recent_visit_is_preserved(db_session):
    now = datetime(2026, 9, 20, 12, 0, 0)
    user = _create_user(db_session, retention_days=30)
    boundary = _create_row(
        db_session,
        user,
        clicked_at=now - timedelta(days=30),
    )
    recent = _create_row(
        db_session,
        user,
        clicked_at=now - timedelta(days=30) + timedelta(microseconds=1),
    )

    result = archive_eligible_rows(db_session, now=now)

    assert result.scanned == 1
    assert result.archived == 1
    db_session.expire_all()
    assert db_session.get(CsvRow, boundary.id).archived is True
    assert db_session.get(CsvRow, boundary.id).archived_at == now
    assert db_session.get(CsvRow, recent.id).archived is False
    assert db_session.get(CsvRow, recent.id).archived_at is None


def test_500_row_batch_limit_and_resume(db_session):
    now = datetime(2026, 9, 20, 12, 0, 0)
    user = _create_user(db_session, retention_days=30)
    rows = []
    for _ in range(501):
        token = uuid4().hex
        rows.append(
            CsvRow(
                user_id=user.id,
                upload_batch_id=f"jg013-{token[:24]}",
                url=f"https://example.com/{token}/batch",
                clicked=True,
                clicked_at=now - timedelta(days=31),
                archived=False,
            )
        )
    db_session.add_all(rows)
    db_session.commit()
    ordered_ids = [
        row_id
        for (row_id,) in (
            db_session.query(CsvRow.id)
            .filter(CsvRow.user_id == user.id)
            .order_by(CsvRow.id.asc())
            .all()
        )
    ]

    first = archive_eligible_rows(db_session, now=now)

    assert first.scanned == 500
    assert first.archived == 500
    assert first.skipped == 0
    assert first.failed == 0
    db_session.expire_all()
    assert (
        db_session.query(CsvRow)
        .filter(CsvRow.id.in_(ordered_ids[:500]), CsvRow.archived.is_(True))
        .count()
        == 500
    )
    assert db_session.get(CsvRow, ordered_ids[500]).archived is False

    second = archive_eligible_rows(db_session, now=now)

    assert second.scanned == 1
    assert second.archived == 1
    assert second.skipped == 0
    assert second.failed == 0
    db_session.expire_all()
    final_row = db_session.get(CsvRow, ordered_ids[500])
    assert final_row.archived is True
    assert final_row.archived_at == now


def test_repeated_run_does_not_double_count_or_reset_timestamp(db_session):
    now = datetime(2026, 9, 20, 12, 0, 0)
    user = _create_user(db_session, retention_days=30)
    row = _create_row(
        db_session,
        user,
        clicked_at=now - timedelta(days=31),
    )

    first = archive_eligible_rows(db_session, now=now)
    later = now + timedelta(hours=6)
    second = archive_eligible_rows(db_session, now=later)

    assert first.archived == 1
    assert second.scanned == 0
    assert second.archived == 0
    db_session.expire_all()
    archived = db_session.get(CsvRow, row.id)
    assert archived.archived is True
    assert archived.archived_at == now


def test_cleanup_failure_not_zero_success(db_session, monkeypatch):
    now = datetime(2026, 9, 20, 12, 0, 0)
    user = _create_user(db_session, retention_days=30)
    row = _create_row(
        db_session,
        user,
        clicked_at=now - timedelta(days=31),
    )
    real_commit = db_session.commit

    def fail_commit():
        raise RuntimeError("synthetic commit failure")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    with pytest.raises(RetentionJobError) as exc_info:
        archive_eligible_rows(db_session, now=now)

    result = exc_info.value.result
    assert result.scanned == 1
    assert result.archived == 0
    assert result.failed == 1
    monkeypatch.setattr(db_session, "commit", real_commit)
    db_session.expire_all()
    assert db_session.get(CsvRow, row.id).archived is False
    assert db_session.get(CsvRow, row.id).archived_at is None


class _FakeSession:
    def close(self):
        return None


def test_two_workers_do_not_double_count(monkeypatch):
    entered = Event()
    release = Event()
    calls = []
    first_results = []
    first_errors = []

    def blocking_archive(_db, **_kwargs):
        calls.append("called")
        entered.set()
        assert release.wait(timeout=5)
        return CleanupResult(scanned=1, archived=1)

    monkeypatch.setattr(jobs_module, "archive_eligible_rows", blocking_archive)

    def run_first():
        try:
            first_results.append(
                jobs_module.cleanup_clicked_rows(session_factory=_FakeSession)
            )
        except Exception as exc:  # pragma: no cover - assertion aid
            first_errors.append(exc)

    worker = Thread(target=run_first)
    worker.start()
    assert entered.wait(timeout=5)

    second = jobs_module.cleanup_clicked_rows(session_factory=_FakeSession)
    assert second["scanned"] == 0
    assert second["archived"] == 0
    assert second["skipped"] == 1
    assert second["failed"] == 0

    release.set()
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert first_errors == []
    assert first_results[0]["archived"] == 1
    assert calls == ["called"]


def test_failed_worker_releases_process_lock(monkeypatch):
    def fail_archive(_db, **_kwargs):
        raise RetentionJobError(
            "synthetic worker failure",
            CleanupResult(scanned=1, failed=1),
        )

    monkeypatch.setattr(jobs_module, "archive_eligible_rows", fail_archive)
    with pytest.raises(RetentionJobError) as exc_info:
        jobs_module.cleanup_clicked_rows(session_factory=_FakeSession)
    assert exc_info.value.result.failed == 1

    monkeypatch.setattr(
        jobs_module,
        "archive_eligible_rows",
        lambda _db, **_kwargs: CleanupResult(),
    )
    retried = jobs_module.cleanup_clicked_rows(session_factory=_FakeSession)
    assert retried["skipped"] == 0
    assert retried["failed"] == 0


def test_postgresql_advisory_lock_contention_is_skipped_and_recoverable(
    monkeypatch,
):
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL advisory lock coverage runs in PostgreSQL CI")

    monkeypatch.setattr(
        jobs_module,
        "archive_eligible_rows",
        lambda _db, **_kwargs: CleanupResult(),
    )

    with engine.connect() as connection:
        held = connection.execute(
            text("SELECT pg_try_advisory_lock(:lock_key)"),
            {"lock_key": jobs_module.POSTGRES_CLEANUP_LOCK_KEY},
        ).scalar()
        assert held is True
        try:
            contended = jobs_module.cleanup_clicked_rows(
                session_factory=_FakeSession
            )
        finally:
            released = connection.execute(
                text("SELECT pg_advisory_unlock(:lock_key)"),
                {"lock_key": jobs_module.POSTGRES_CLEANUP_LOCK_KEY},
            ).scalar()
            assert released is True

    assert contended["skipped"] == 1
    after_release = jobs_module.cleanup_clicked_rows(session_factory=_FakeSession)
    assert after_release["skipped"] == 0
    assert after_release["failed"] == 0


def test_batch_size_over_500_is_rejected_with_failure_result(db_session):
    with pytest.raises(RetentionJobError) as exc_info:
        archive_eligible_rows(db_session, batch_size=501)

    assert exc_info.value.result.failed == 1
    assert exc_info.value.result.archived == 0
