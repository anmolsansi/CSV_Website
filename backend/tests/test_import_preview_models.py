import json
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.import_models import ImportMapping, ImportPreview
from app.import_schemas import ImportCommitRequest, header_fingerprint
from app.models import User
from app.services.import_backups import export_backup_v2_with_import_mappings
from app.services.imports import (
    cleanup_import_previews,
    create_import_preview,
    get_owned_import_preview,
    parse_import_source,
)
from app.import_schemas import ImportContractError


def _user(db, prefix):
    user = User(email=f"{prefix}-{uuid4()}@example.test", timezone="UTC")
    db.add(user)
    db.flush()
    return user


def test_preview_expiry_and_owner_constraints(db_session):
    owner = _user(db_session, "import-owner")
    foreign = _user(db_session, "import-foreign")
    expired = ImportPreview(
        user_id=owner.id,
        source_filename="expired.csv",
        source_sha256="a" * 64,
        headers_json=["url"],
        header_fingerprint="b" * 64,
        mapping_json={"0": "url"},
        normalized_rows_json=[],
        rejected_rows_json=None,
        summary_json={"counts": {}},
        destination_fingerprint="c" * 64,
        created_at=datetime.utcnow() - timedelta(hours=25),
        expires_at=datetime.utcnow() - timedelta(hours=1),
        status="ready",
        version=1,
    )
    foreign_preview = ImportPreview(
        user_id=foreign.id,
        source_filename="foreign.csv",
        source_sha256="d" * 64,
        headers_json=["url"],
        header_fingerprint="e" * 64,
        mapping_json={"0": "url"},
        normalized_rows_json=[],
        rejected_rows_json=None,
        summary_json={"counts": {}},
        destination_fingerprint="f" * 64,
        expires_at=datetime.utcnow() + timedelta(hours=1),
        status="ready",
        version=1,
    )
    db_session.add_all([expired, foreign_preview])
    db_session.commit()

    with pytest.raises(ImportContractError) as error:
        get_owned_import_preview(db_session, user_id=owner.id, preview_id=foreign_preview.id)
    assert error.value.status_code == 404

    result = cleanup_import_previews(db_session, now=datetime.utcnow(), limit=20)
    db_session.commit()
    assert result == {"deleted": 1, "scrubbed": 0}
    assert db_session.query(ImportPreview).filter_by(id=expired.id).first() is None
    assert db_session.query(ImportPreview).filter_by(id=foreign_preview.id).one().user_id == foreign.id


def test_duplicate_headers_preserved_by_index(db_session):
    headers, rows = parse_import_source(
        b"url,title,title\nhttps://example.test/jobs/1,first,second\n",
        filename="duplicate.csv",
        content_type="text/csv",
    )
    assert headers == ["url", "title", "title"]
    assert rows == [(2, ["https://example.test/jobs/1", "first", "second"])]
    assert header_fingerprint(headers) != header_fingerprint(["url", "title"])

    owner = _user(db_session, "duplicate-header")
    preview = create_import_preview(
        db_session,
        user_id=owner.id,
        raw=b"url,title,title\nhttps://example.test/jobs/1,first,second\n",
        filename="duplicate.csv",
        content_type="text/csv",
        mapping_value={"0": "url", "2": "title"},
    )
    assert preview.headers_json == ["url", "title", "title"]
    assert preview.mapping_json == {"0": "url", "2": "title"}
    assert preview.normalized_rows_json[0]["values"]["title"] == "second"


def test_forbidden_update_fields_rejected():
    with pytest.raises(ValidationError):
        ImportCommitRequest(
            version=1,
            idempotency_key=str(uuid4()),
            mode="update_selected",
            update_fields=["clicked"],
            invalid_policy="reject",
        )
    with pytest.raises(ValidationError):
        ImportCommitRequest(
            version=1,
            idempotency_key=str(uuid4()),
            mode="update_selected",
            update_fields=["url"],
            invalid_policy="reject",
        )


def test_committed_payload_raw_rows_removed(db_session):
    from app.services.imports import commit_import_preview

    owner = _user(db_session, "raw-removal")
    preview = create_import_preview(
        db_session,
        user_id=owner.id,
        raw=b"url,title\nhttps://example.test/jobs/raw-removal,Engineer\n",
        filename="jobs.csv",
        content_type="text/csv",
        mapping_value={"0": "url", "1": "title"},
    )
    db_session.commit()
    payload = ImportCommitRequest(
        version=preview.version,
        idempotency_key=str(uuid4()),
        mode="insert_only",
        invalid_policy="reject",
    )
    result, replayed = commit_import_preview(
        db_session,
        user_id=owner.id,
        preview_id=preview.id,
        payload=payload,
    )
    db_session.commit()
    assert replayed is False
    assert result["counts"] == {"created": 1, "updated": 0, "skipped": 0, "invalid": 0}

    db_session.expire_all()
    stored = db_session.query(ImportPreview).filter_by(id=preview.id).one()
    assert stored.status == "committed"
    assert stored.normalized_rows_json is None
    assert stored.result_json == result
    assert stored.commit_key == payload.idempotency_key


def test_backup_includes_mapping_not_uploaded_preview(db_session):
    owner = _user(db_session, "mapping-backup")
    mapping = ImportMapping(
        user_id=owner.id,
        name="Standard export",
        header_fingerprint="a" * 64,
        mapping_json={"0": "url", "1": "title"},
        version=2,
    )
    preview = ImportPreview(
        user_id=owner.id,
        source_filename="private-upload.csv",
        source_sha256="b" * 64,
        headers_json=["url", "title"],
        header_fingerprint="c" * 64,
        mapping_json={"0": "url", "1": "title"},
        normalized_rows_json=[{"private": "uploaded row must not be backed up"}],
        rejected_rows_json=[{"private": "rejected raw must not be backed up"}],
        summary_json={"counts": {"create": 1}},
        destination_fingerprint="d" * 64,
        expires_at=datetime.utcnow() + timedelta(hours=24),
        status="ready",
        version=1,
    )
    db_session.add_all([mapping, preview])
    db_session.commit()

    payload = export_backup_v2_with_import_mappings(db_session, owner.id)
    extension = payload["f9_import_mappings"]
    assert extension["mappings"] == [
        {
            "name": "Standard export",
            "header_fingerprint": "a" * 64,
            "mapping_json": {"0": "url", "1": "title"},
            "version": 2,
        }
    ]
    serialized = json.dumps(payload)
    assert "private-upload.csv" not in serialized
    assert "uploaded row must not be backed up" not in serialized
    assert "rejected raw must not be backed up" not in serialized
