import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.models import CsvRow, JobLifecycleEvent, JobTrack, User
from app.services.bulk_actions import (
    archive_rows,
    permanent_delete_preview,
    permanent_delete_rows,
    restore_archived_rows,
    undo_action,
)
from app.services.import_backups import (
    export_backup_v2_with_import_mappings,
    restore_backup_payload_with_import_mappings,
)
from app.undo_models import BulkAction
from app.undo_schemas import UndoContractError


def _user(db, prefix):
    user = User(email=f"{prefix}-{uuid4()}@example.test", timezone="UTC")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _auth_user(db):
    user = db.query(User).filter_by(email="test@jobgrid.dev").first()
    if user is None:
        user = User(email="test@jobgrid.dev", timezone="UTC")
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
    user = _auth_user(db_session)
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


def test_metric_correction_matches_undo(auth_client, db_session):
    user = _auth_user(db_session)
    row = _row(db_session, user, "track-undo")
    track = JobTrack(
        user_id=user.id,
        csv_row_id=row.id,
        url=row.url,
        company="Metric Co",
        title="Engineer",
        status="opened",
        applied_at=None,
        open_count=1,
    )
    db_session.add(track)
    db_session.commit()
    operation_id = str(uuid4())

    changed = auth_client.patch(
        "/crm/applications/bulk",
        headers={"X-Operation-ID": operation_id},
        json={"ids": [track.id], "patch": {"status": "applied"}},
    )
    assert changed.status_code == 200, changed.text
    changed_payload = changed.json()
    assert changed_payload["updated"] == 1
    assert changed_payload["failed"] == []
    assert changed_payload["operation_id"]
    assert changed_payload["undo_expires_at"]

    db_session.expire_all()
    applied = db_session.get(JobTrack, track.id)
    assert applied.status == "applied"
    assert applied.applied_at is not None

    undone = auth_client.post(
        f"/crm/bulk-actions/{changed_payload['operation_id']}/undo",
        json={"mode": "all_or_nothing"},
    )
    assert undone.status_code == 200, undone.text
    db_session.expire_all()
    restored = db_session.get(JobTrack, track.id)
    assert restored.status == "opened"
    assert restored.applied_at is None

    corrections = (
        db_session.query(JobLifecycleEvent)
        .filter(
            JobLifecycleEvent.user_id == user.id,
            JobLifecycleEvent.job_track_id == track.id,
            JobLifecycleEvent.source == "bulk_undo",
        )
        .all()
    )
    assert {event.kind for event in corrections} >= {"status_changed", "applied_date_corrected"}


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
    assert permanent_delete_preview(
        db_session,
        user_id=user.id,
        row_ids=[row.id],
    )["automatic_purge_enabled"] is False


def test_default_automatic_purge_disabled(db_session):
    user = _user(db_session, "jg064-default-purge")
    row = _row(db_session, user, "default-purge")
    _archive(db_session, user, [row])
    archived = db_session.get(CsvRow, row.id)

    preview = permanent_delete_preview(
        db_session,
        user_id=user.id,
        row_ids=[row.id],
        expected_versions={row.id: archived.version},
    )
    assert preview["automatic_purge_enabled"] is False
    assert db_session.get(CsvRow, row.id) is not None


def test_undo_cannot_overwrite_newer_import(db_session):
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


def test_restored_backup_matches_pre_purge_history(db_session):
    source = _user(db_session, "jg064-backup-source")
    row = _row(db_session, source, "backup", clicked=True, clicked_at=datetime.utcnow())
    track = JobTrack(
        user_id=source.id,
        csv_row_id=row.id,
        url=row.url,
        company="Recovery Co",
        title="Platform Engineer",
        status="interview",
        notes="pre-purge durable history",
        open_count=3,
    )
    db_session.add(track)
    db_session.commit()

    backup = export_backup_v2_with_import_mappings(db_session, source.id)
    _archive(db_session, source, [row])
    archived = db_session.get(CsvRow, row.id)
    preview = permanent_delete_preview(
        db_session,
        user_id=source.id,
        row_ids=[row.id],
        expected_versions={row.id: archived.version},
    )
    permanent_delete_rows(
        db_session,
        user_id=source.id,
        row_ids=[row.id],
        expected_versions={row.id: archived.version},
        confirmation_token=preview["confirmation_token"],
    )
    db_session.commit()
    assert db_session.get(CsvRow, row.id) is None

    destination = _user(db_session, "jg064-backup-destination")
    result = restore_backup_payload_with_import_mappings(
        db_session,
        destination.id,
        json.dumps(backup).encode("utf-8"),
        "merge_missing",
    )
    assert result["counts"]["csv_rows"]["created"] == 1
    assert result["counts"]["job_tracks"]["created"] == 1

    restored_row = db_session.query(CsvRow).filter_by(user_id=destination.id, url=row.url).one()
    restored_track = db_session.query(JobTrack).filter_by(user_id=destination.id, url=row.url).one()
    assert restored_track.csv_row_id == restored_row.id
    assert restored_row.clicked is True
    assert restored_track.status == "interview"
    assert restored_track.notes == "pre-purge durable history"
    assert restored_track.open_count == 3
