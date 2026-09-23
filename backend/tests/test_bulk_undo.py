from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.models import CsvRow, JobTrack, User
from app.services.bulk_actions import (
    archive_rows,
    permanent_delete_preview,
    permanent_delete_rows,
    restore_archived_rows,
    undo_action,
)
from app.undo_models import BulkAction
from app.undo_schemas import UndoContractError


def _user(db, prefix):
    user = User(email=f"{prefix}-{uuid4()}@example.test", timezone="UTC")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _row(db, user, suffix, **values):
    row = CsvRow(
        user_id=user.id,
        upload_batch_id=f"jg062-{suffix}",
        url=f"https://example.test/jg062/{suffix}-{uuid4()}",
        title=values.pop("title", "Engineer"),
        **values,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _archive(db, user, rows, *, now=None):
    result = archive_rows(
        db,
        user_id=user.id,
        row_ids=[row.id for row in rows],
        request_key=str(uuid4()),
        expected_versions={row.id: row.version for row in rows},
        now=now,
    )
    db.commit()
    db.expire_all()
    return result


def test_bulk_failure_rolls_back_changes_and_journal(db_session, monkeypatch):
    user = _user(db_session, "jg062-rollback")
    row = _row(db_session, user, "rollback")

    from app.services import bulk_actions as service

    def explode(*args, **kwargs):
        raise RuntimeError("journal unavailable")

    monkeypatch.setattr(service, "create_bulk_action_journal", explode)
    with pytest.raises(RuntimeError):
        archive_rows(
            db_session,
            user_id=user.id,
            row_ids=[row.id],
            request_key=str(uuid4()),
            expected_versions={row.id: row.version},
        )
    db_session.rollback()
    db_session.expire_all()

    stored = db_session.get(CsvRow, row.id)
    assert stored.archived is False
    assert stored.version == 1
    assert db_session.query(BulkAction).filter_by(user_id=user.id).count() == 0


def test_one_conflict_default_zero_restore(db_session):
    user = _user(db_session, "jg062-conflict")
    rows = [_row(db_session, user, f"conflict-{index}") for index in range(3)]
    result = _archive(db_session, user, rows)

    changed = db_session.get(CsvRow, rows[1].id)
    changed.title = "Edited in another tab"
    db_session.commit()

    with pytest.raises(UndoContractError) as conflict:
        undo_action(
            db_session,
            user_id=user.id,
            action_id=result["operation_id"],
            mode="all_or_nothing",
        )
    assert conflict.value.status_code == 409
    assert conflict.value.context["restored"] == 0
    assert conflict.value.context["conflicts"] == 1
    db_session.commit()
    db_session.expire_all()

    assert all(db_session.get(CsvRow, row.id).archived is True for row in rows)


def test_partial_mode_restores_only_unchanged(db_session):
    user = _user(db_session, "jg062-partial")
    rows = [_row(db_session, user, f"partial-{index}") for index in range(3)]
    result = _archive(db_session, user, rows)

    changed = db_session.get(CsvRow, rows[1].id)
    changed.title = "Newer edit"
    db_session.commit()

    partial = undo_action(
        db_session,
        user_id=user.id,
        action_id=result["operation_id"],
        mode="restore_unchanged",
    )
    db_session.commit()
    db_session.expire_all()

    assert partial["status"] == "partially_undone"
    assert partial["restored"] == 2
    assert partial["conflicts"] == 1
    assert db_session.get(CsvRow, rows[0].id).archived is False
    assert db_session.get(CsvRow, rows[1].id).archived is True
    assert db_session.get(CsvRow, rows[2].id).archived is False


def test_retry_undo_no_second_mutation(db_session):
    user = _user(db_session, "jg062-retry")
    row = _row(db_session, user, "retry")
    result = _archive(db_session, user, [row])

    first = undo_action(
        db_session,
        user_id=user.id,
        action_id=result["operation_id"],
    )
    db_session.commit()
    db_session.expire_all()
    restored = db_session.get(CsvRow, row.id)
    version_after_first = restored.version

    second = undo_action(
        db_session,
        user_id=user.id,
        action_id=result["operation_id"],
    )
    db_session.commit()
    db_session.expire_all()

    assert first["restored"] == 1
    assert second["replayed"] is True
    assert db_session.get(CsvRow, row.id).version == version_after_first


def test_expired410_foreign404(db_session):
    owner = _user(db_session, "jg062-owner")
    foreign = _user(db_session, "jg062-foreign")
    row = _row(db_session, owner, "expiry")
    old_now = datetime.now(timezone.utc) - timedelta(minutes=11)
    result = _archive(db_session, owner, [row], now=old_now)

    with pytest.raises(UndoContractError) as expired:
        undo_action(
            db_session,
            user_id=owner.id,
            action_id=result["operation_id"],
            now=datetime.now(timezone.utc),
        )
    assert expired.value.status_code == 410

    with pytest.raises(UndoContractError) as missing:
        undo_action(
            db_session,
            user_id=foreign.id,
            action_id=result["operation_id"],
        )
    assert missing.value.status_code == 404


def test_archive_api_returns_additive_operation_metadata(auth_client, db_session):
    user = db_session.query(User).filter_by(email="test@jobgrid.dev").first()
    if user is None:
        user = User(email="test@jobgrid.dev", timezone="UTC")
        db_session.add(user)
        db_session.commit()
    row = _row(db_session, user, "api")

    response = auth_client.request(
        "DELETE",
        "/rows",
        json={
            "row_ids": [row.id],
            "mode": "archive",
            "request_key": str(uuid4()),
            "expected_versions": {str(row.id): row.version},
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["archived"] == 1
    assert payload["deleted"] == 0
    assert payload["operation_id"]
    assert payload["undo_expires_at"]


def test_restore_archive_keeps_application_state(db_session):
    user = _user(db_session, "jg063-restore")
    row = _row(db_session, user, "restore", clicked=True, clicked_at=datetime.utcnow())
    track = JobTrack(
        user_id=user.id,
        csv_row_id=row.id,
        url=row.url,
        company="Example",
        title="Engineer",
        status="applied",
        applied_at=datetime.utcnow(),
        open_count=1,
    )
    db_session.add(track)
    db_session.commit()
    original_applied_at = track.applied_at
    result = _archive(db_session, user, [row])
    archived = db_session.get(CsvRow, row.id)

    restored = restore_archived_rows(
        db_session,
        user_id=user.id,
        row_ids=[row.id],
        expected_versions={row.id: archived.version},
    )
    db_session.commit()
    db_session.expire_all()

    assert restored == {"restored": 1, "conflicts": 0, "missing": 0}
    stored_row = db_session.get(CsvRow, row.id)
    stored_track = db_session.get(JobTrack, track.id)
    assert stored_row.archived is False
    assert stored_row.clicked is True
    assert stored_track.status == "applied"
    assert stored_track.applied_at == original_applied_at
    assert result["operation_id"]


def test_purge_source_preserves_complete_application_graph(db_session):
    user = _user(db_session, "jg064-purge")
    row = _row(db_session, user, "purge")
    track = JobTrack(
        user_id=user.id,
        csv_row_id=row.id,
        url=row.url,
        company="Durable Co",
        title="Engineer",
        status="interview",
        notes="durable application history",
    )
    db_session.add(track)
    db_session.commit()
    _archive(db_session, user, [row])
    archived = db_session.get(CsvRow, row.id)

    preview = permanent_delete_preview(
        db_session,
        user_id=user.id,
        row_ids=[row.id],
        expected_versions={row.id: archived.version},
    )
    deleted = permanent_delete_rows(
        db_session,
        user_id=user.id,
        row_ids=[row.id],
        expected_versions={row.id: archived.version},
        confirmation_token=preview["confirmation_token"],
    )
    db_session.commit()
    db_session.expire_all()

    assert deleted["deleted"] == 1
    assert db_session.get(CsvRow, row.id) is None
    durable_track = db_session.get(JobTrack, track.id)
    assert durable_track is not None
    assert durable_track.csv_row_id is None
    assert durable_track.status == "interview"
    assert durable_track.notes == "durable application history"


def test_unknown_archive_timestamp_never_purged_automatically(db_session):
    user = _user(db_session, "jg064-unknown")
    row = _row(db_session, user, "unknown")
    row.archived = True
    row.archived_at = None
    db_session.commit()

    stored = db_session.get(CsvRow, row.id)
    assert stored.archived is True
    assert stored.archived_at is None
    # F10 deliberately ships no automatic purge worker. Only an explicit,
    # confirmation-token guarded selected-row delete path exists.
    assert permanent_delete_preview(
        db_session,
        user_id=user.id,
        row_ids=[row.id],
    )["automatic_purge_enabled"] is False


def test_undo_cannot_overwrite_newer_import_style_edit(db_session):
    user = _user(db_session, "jg064-newer")
    row = _row(db_session, user, "newer", title="Before")
    result = _archive(db_session, user, [row])

    current = db_session.get(CsvRow, row.id)
    current.title = "Imported newer title"
    db_session.commit()

    with pytest.raises(UndoContractError) as conflict:
        undo_action(
            db_session,
            user_id=user.id,
            action_id=result["operation_id"],
            mode="all_or_nothing",
        )
    assert conflict.value.status_code == 409
    db_session.rollback()
    db_session.expire_all()
    assert db_session.get(CsvRow, row.id).title == "Imported newer title"
    assert db_session.get(CsvRow, row.id).archived is True
