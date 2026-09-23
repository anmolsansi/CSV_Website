from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.import_schemas import ImportCommitRequest
from app.models import CsvRow, JobTrack, User
from app.services.imports import commit_import_preview, create_import_preview
from app.services.retention import archive_eligible_rows
from app.services.undo_foundation import (
    cleanup_bulk_action_journals,
    compare_and_update,
    create_bulk_action_journal,
    serialize_bulk_action_metadata_for_backup,
    snapshot_changed_fields,
)
from app.undo_models import BulkAction, BulkActionEffect
from app.undo_schemas import MAX_BULK_SNAPSHOT_BYTES, UndoContractError


def _user(db, prefix):
    user = User(email=f"{prefix}-{uuid4()}@example.test", timezone="UTC")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _row(db, user, suffix, **values):
    row = CsvRow(
        user_id=user.id,
        upload_batch_id=f"jg061-{suffix}",
        url=f"https://example.test/jg061/{suffix}-{uuid4()}",
        title=values.pop("title", "Engineer"),
        **values,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_version_changes_on_each_mutation_path(auth_client, db_session):
    user = db_session.query(User).filter_by(email="test@jobgrid.dev").first()
    if user is None:
        user = User(email="test@jobgrid.dev", timezone="UTC")
        db_session.add(user)
        db_session.commit()

    # Ordinary CsvRow ORM mutation uses the shared before_update hook.
    row = _row(db_session, user, "orm")
    assert row.version == 1
    row.title = "Senior Engineer"
    db_session.commit()
    db_session.refresh(row)
    assert row.version == 2

    # Import exact-match update is an ORM writer and advances once.
    preview = create_import_preview(
        db_session,
        user_id=user.id,
        raw=f"url,title\n{row.url},Principal Engineer\n".encode(),
        filename="update.csv",
        content_type="text/csv",
        mapping_value={"0": "url", "1": "title"},
    )
    db_session.commit()
    payload = ImportCommitRequest(
        version=preview.version,
        idempotency_key=str(uuid4()),
        mode="update_selected",
        update_fields=["title"],
        invalid_policy="reject",
    )
    result, replayed = commit_import_preview(
        db_session,
        user_id=user.id,
        preview_id=preview.id,
        payload=payload,
    )
    db_session.commit()
    db_session.refresh(row)
    assert replayed is False
    assert result["counts"]["updated"] == 1
    assert row.version == 3

    # Dashboard archive is raw bulk SQL and increments in the same statement.
    archive_row = _row(db_session, user, "archive")
    archive_response = auth_client.delete(
        "/rows",
        json={"row_ids": [archive_row.id], "mode": "archive"},
    )
    assert archive_response.status_code == 200, archive_response.text
    db_session.expire_all()
    archive_row = db_session.get(CsvRow, archive_row.id)
    assert archive_row.archived is True
    assert archive_row.version == 2

    # Retention archive is the second raw bulk SQL path and also increments.
    retention_row = _row(
        db_session,
        user,
        "retention",
        clicked=True,
        clicked_at=datetime.utcnow() - timedelta(days=30),
    )
    user.retention_days = 7
    db_session.commit()
    cleanup = archive_eligible_rows(
        db_session,
        now=datetime.utcnow(),
        batch_size=500,
    )
    assert cleanup.archived >= 1
    db_session.expire_all()
    retention_row = db_session.get(CsvRow, retention_row.id)
    assert retention_row.archived is True
    assert retention_row.version == 2

    # Application/JobTrack ORM writers share the same optimistic hook.
    track_row = _row(db_session, user, "track")
    created = auth_client.post(f"/crm/from-row/{track_row.id}")
    assert created.status_code == 200, created.text
    track = db_session.get(JobTrack, created.json()["id"])
    assert track.version == 1
    patch = auth_client.patch(
        f"/crm/applications/{track.id}",
        json={"notes": "Versioned application note"},
    )
    assert patch.status_code == 200, patch.text
    db_session.expire_all()
    track = db_session.get(JobTrack, track.id)
    assert track.version == 2

    # The future F10 compare-and-update helper enforces expected version and
    # advances exactly once through the same ORM hook.
    updated = compare_and_update(
        db_session,
        entity_type="job_track",
        user_id=user.id,
        entity_id=track.id,
        expected_version=2,
        changes={"notes": "Updated through optimistic helper"},
    )
    assert updated.version == 3
    with pytest.raises(UndoContractError) as stale:
        compare_and_update(
            db_session,
            entity_type="job_track",
            user_id=user.id,
            entity_id=track.id,
            expected_version=2,
            changes={"notes": "stale write"},
        )
    assert stale.value.code == "version_conflict"


def test_snapshot_over_limit_rejected_before_write(db_session):
    user = _user(db_session, "jg061-limit")
    row = _row(db_session, user, "limit-row")
    before_actions = db_session.query(BulkAction).filter_by(user_id=user.id).count()

    effects = [{
        "entity_type": "csv_row",
        "entity_id": row.id,
        "before_json": {"title": "x" * (MAX_BULK_SNAPSHOT_BYTES + 100)},
        "after_version": row.version + 1,
    }]
    with pytest.raises(UndoContractError) as too_large:
        create_bulk_action_journal(
            db_session,
            user_id=user.id,
            kind="update_rows",
            request_key=str(uuid4()),
            effects=effects,
        )
    assert too_large.value.code == "bulk_snapshot_limit_exceeded"
    assert too_large.value.status_code == 413
    assert db_session.query(BulkAction).filter_by(user_id=user.id).count() == before_actions

    too_many = [
        {
            "entity_type": "csv_row",
            "entity_id": row.id,
            "before_json": {"title": "before"},
            "after_version": row.version + 1,
        }
        for _ in range(501)
    ]
    with pytest.raises(UndoContractError) as target_limit:
        create_bulk_action_journal(
            db_session,
            user_id=user.id,
            kind="update_rows",
            request_key=str(uuid4()),
            effects=too_many,
        )
    assert target_limit.value.code == "bulk_target_limit_exceeded"
    assert target_limit.value.status_code == 413
    assert db_session.query(BulkAction).filter_by(user_id=user.id).count() == before_actions


def test_duplicate_operation_key_single_journal(db_session):
    user = _user(db_session, "jg061-idempotent")
    row = _row(db_session, user, "idempotent-row")
    request_key = str(uuid4())
    effects = [{
        "entity_type": "csv_row",
        "entity_id": row.id,
        "before_json": {"title": row.title},
        "after_version": row.version + 1,
    }]

    first, replayed_first = create_bulk_action_journal(
        db_session,
        user_id=user.id,
        kind="update_rows",
        request_key=request_key,
        effects=effects,
        result={"updated": 1},
    )
    db_session.commit()
    second, replayed_second = create_bulk_action_journal(
        db_session,
        user_id=user.id,
        kind="update_rows",
        request_key=request_key,
        effects=effects,
        result={"updated": 1},
    )

    assert replayed_first is False
    assert replayed_second is True
    assert second.id == first.id
    assert db_session.query(BulkAction).filter_by(user_id=user.id, request_key=request_key).count() == 1
    assert db_session.query(BulkActionEffect).filter_by(action_id=first.id).count() == 1

    conflicting = [{**effects[0], "before_json": {"title": "different"}}]
    with pytest.raises(UndoContractError) as conflict:
        create_bulk_action_journal(
            db_session,
            user_id=user.id,
            kind="update_rows",
            request_key=request_key,
            effects=conflicting,
        )
    assert conflict.value.code == "request_key_conflict"


def test_expired_before_images_removed(db_session):
    user = _user(db_session, "jg061-expiry")
    row = _row(db_session, user, "expiry-row")
    now = datetime.now(timezone.utc)
    action, _ = create_bulk_action_journal(
        db_session,
        user_id=user.id,
        kind="archive_rows",
        request_key=str(uuid4()),
        effects=[{
            "entity_type": "csv_row",
            "entity_id": row.id,
            "before_json": {"archived": False, "archived_at": None},
            "after_version": row.version + 1,
        }],
        now=now - timedelta(minutes=11),
    )
    db_session.commit()
    assert action.effects[0].before_json == {"archived": False, "archived_at": None}

    cleaned = cleanup_bulk_action_journals(db_session, now=now, limit=500)
    db_session.commit()
    db_session.expire_all()
    stored = db_session.get(BulkAction, action.id)
    assert cleaned["expired_actions"] == 1
    assert cleaned["scrubbed_effects"] == 1
    assert stored.status == "expired"
    assert stored.effects[0].before_json is None

    backup_metadata = serialize_bulk_action_metadata_for_backup(
        db_session,
        user_id=user.id,
    )
    assert backup_metadata[0]["undo_available"] is False
    assert "before_json" not in str(backup_metadata)


def test_foreign_effect_reference_rejected(db_session):
    owner = _user(db_session, "jg061-owner")
    foreign = _user(db_session, "jg061-foreign")
    foreign_row = _row(db_session, foreign, "foreign-row")

    with pytest.raises(UndoContractError) as missing:
        create_bulk_action_journal(
            db_session,
            user_id=owner.id,
            kind="update_rows",
            request_key=str(uuid4()),
            effects=[{
                "entity_type": "csv_row",
                "entity_id": foreign_row.id,
                "before_json": {"title": foreign_row.title},
                "after_version": foreign_row.version + 1,
            }],
        )
    assert missing.value.code == "effect_target_not_found"
    assert missing.value.status_code == 404
    assert db_session.query(BulkAction).filter_by(user_id=owner.id).count() == 0


def test_snapshot_changed_fields_is_strict_and_minimal(db_session):
    user = _user(db_session, "jg061-snapshot")
    row = _row(db_session, user, "snapshot", title="Before")

    before = snapshot_changed_fields(
        "csv_row",
        row,
        {"title": "After", "company_guess": row.company_guess},
    )
    assert before == {"title": "Before"}

    with pytest.raises(UndoContractError) as forbidden:
        snapshot_changed_fields("csv_row", row, {"user_id": 999})
    assert forbidden.value.code == "forbidden_snapshot_field"
