import io
import json
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.backup_schemas import BackupContractError
from app.contact_models import ApplicationContact, Contact, Interview, MutationReceipt
from app.import_models import ImportMapping
from app.models import BackupImportMap, JobTrack, User
from app.services import backups, contact_backups, import_backups


@pytest.fixture
def complete_backup(db_session):
    source = User(email=f"complete-source-{uuid4()}@example.test")
    target = User(email=f"complete-target-{uuid4()}@example.test")
    db_session.add_all([source, target])
    db_session.flush()
    track = JobTrack(user_id=source.id, url=f"https://example.test/{uuid4()}", company="Recovery Co", status="applied")
    contact = Contact(user_id=source.id, name="Recruiter")
    db_session.add_all([track, contact])
    db_session.flush()
    db_session.add(Interview(user_id=source.id, track_id=track.id, contact_id=contact.id,
                             starts_at=datetime(2026, 10, 1, 10), ends_at=datetime(2026, 10, 1, 11),
                             timezone="UTC", kind="video"))
    db_session.add(ApplicationContact(user_id=source.id, track_id=track.id, contact_id=contact.id, role="recruiter"))
    db_session.add(ImportMapping(user_id=source.id, name="Mapping", header_fingerprint="a" * 64,
                                 mapping_json={"0": "url"}))
    db_session.commit()
    payload = import_backups.export_backup_v2_with_import_mappings(db_session, source.id)
    return source.id, target.id, payload


def assert_empty(db, target_id):
    with Session(db.get_bind()) as fresh:
        for model in (JobTrack, Contact, Interview, ApplicationContact, ImportMapping, MutationReceipt, BackupImportMap):
            assert fresh.query(model).filter_by(user_id=target_id).count() == 0, model.__name__


def test_invalid_extension_restore_is_atomic(db_session, complete_backup):
    _, target_id, payload = complete_backup
    payload[contact_backups.F8_BACKUP_KEY]["checksum_sha256"] = "0" * 64
    with pytest.raises(BackupContractError):
        import_backups.restore_backup_payload_with_import_mappings(db_session, target_id, json.dumps(payload).encode(), "merge_missing")
    assert_empty(db_session, target_id)


def test_late_mapping_failure_rolls_back_every_section(db_session, complete_backup):
    _, target_id, payload = complete_backup

    def fail_mapping(mapper, connection, target):
        if target.user_id == target_id:
            raise RuntimeError("injected last extension failure")

    event.listen(ImportMapping, "before_insert", fail_mapping)
    try:
        with pytest.raises(RuntimeError, match="last extension"):
            import_backups.restore_backup_payload_with_import_mappings(db_session, target_id, json.dumps(payload).encode(), "merge_missing")
    finally:
        event.remove(ImportMapping, "before_insert", fail_mapping)
    assert_empty(db_session, target_id)


def test_complete_verify_and_replay(db_session, complete_backup):
    _, target_id, payload = complete_backup
    raw = json.dumps(payload).encode()
    verify = import_backups.restore_backup_payload_with_import_mappings(db_session, target_id, raw, "verify_only")
    assert verify["verified"]
    for section in ("contacts", "interviews", "application_contacts", "import_mappings"):
        assert verify["counts"][section]["created"] == 1
    assert_empty(db_session, target_id)
    first = import_backups.restore_backup_payload_with_import_mappings(db_session, target_id, raw, "merge_missing")
    second = import_backups.restore_backup_payload_with_import_mappings(db_session, target_id, raw, "merge_missing")
    for section in ("job_tracks", "contacts", "interviews", "application_contacts", "import_mappings"):
        assert first["counts"][section]["created"] == 1
        assert second["counts"][section]["created"] == 0


@pytest.mark.parametrize("mode", ["verify_only", "merge_missing"])
@pytest.mark.parametrize("defect", ["foreign_owner", "duplicate_ref", "timestamp", "bad_role", "bad_reference"])
def test_invalid_contact_records_rejected_before_restore(db_session, complete_backup, mode, defect):
    _, target_id, payload = complete_backup
    extension = payload[contact_backups.F8_BACKUP_KEY]
    contacts = extension["sections"]["contacts"]
    if defect == "foreign_owner":
        contacts[0]["user_id"] = target_id
    elif defect == "duplicate_ref":
        contacts.append(dict(contacts[0]))
    elif defect == "timestamp":
        contacts[0]["created_at"] = "not-a-timestamp"
    elif defect == "bad_role":
        extension["sections"]["interviews"][0]["kind"] = "unknown"
    else:
        extension["sections"]["interviews"][0]["track_ref"] = str(uuid4())
    extension["checksum_sha256"] = contact_backups._checksum({
        key: value for key, value in extension.items() if key != "checksum_sha256"
    })
    with pytest.raises(BackupContractError):
        import_backups.restore_backup_payload_with_import_mappings(db_session, target_id, json.dumps(payload).encode(), mode)
    assert_empty(db_session, target_id)


def test_contact_replay_conflict_fails_preflight(db_session, complete_backup):
    _, target_id, payload = complete_backup
    import_backups.restore_backup_payload_with_import_mappings(db_session, target_id, json.dumps(payload).encode(), "merge_missing")
    extension = payload[contact_backups.F8_BACKUP_KEY]
    extension["sections"]["contacts"][0]["notes"] = "changed after original restore"
    extension["checksum_sha256"] = contact_backups._checksum({
        key: value for key, value in extension.items() if key != "checksum_sha256"
    })
    with pytest.raises(BackupContractError, match="different content"):
        import_backups.restore_backup_payload_with_import_mappings(db_session, target_id, json.dumps(payload).encode(), "verify_only")


@pytest.mark.postgresql
def test_concurrent_complete_restore_serializes_extensions(db_session, complete_backup):
    if db_session.get_bind().dialect.name != "postgresql":
        pytest.skip("Concurrent account-row locking requires PostgreSQL")
    _, target_id, payload = complete_backup
    raw = json.dumps(payload).encode()
    bind = db_session.get_bind()

    def restore():
        with Session(bind) as session:
            return import_backups.restore_backup_payload_with_import_mappings(session, target_id, raw, "merge_missing")

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: restore(), range(2)))
    for section in ("job_tracks", "contacts", "application_contacts", "interviews", "import_mappings"):
        assert sum(result["counts"][section]["created"] for result in results) == 1
    with Session(bind) as session:
        for model in (JobTrack, Contact, Interview, ApplicationContact, ImportMapping):
            assert session.query(model).filter_by(user_id=target_id).count() == 1


def test_complete_record_limit_includes_extensions(db_session, complete_backup, monkeypatch):
    source_id, target_id, payload = complete_backup
    base_count = sum(len(records) for records in payload["sections"].values())
    monkeypatch.setattr(import_backups, "MAX_TOTAL_RECORDS", base_count)
    with pytest.raises(BackupContractError, match="record limit"):
        import_backups.restore_backup_payload_with_import_mappings(db_session, target_id, json.dumps(payload).encode(), "merge_missing")
    assert_empty(db_session, target_id)
    with pytest.raises(BackupContractError, match="record limit"):
        import_backups.export_backup_v2_with_import_mappings(db_session, source_id)


def test_bundle_contains_and_restores_extensions(db_session, complete_backup, tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_DIR", str(tmp_path / "documents"))
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")
    (tmp_path / "documents").mkdir()
    source_id, target_id, _ = complete_backup
    raw = backups.export_backup_bundle(db_session, source_id)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        payload = json.loads(archive.read("backup.json"))
    assert contact_backups.F8_BACKUP_KEY in payload
    assert import_backups.F9_BACKUP_KEY in payload
    verify = backups.restore_backup_bundle(db_session, target_id, raw, "verify_only")
    assert verify["verified"]
    assert_empty(db_session, target_id)
    result = backups.restore_backup_bundle(db_session, target_id, raw, "merge_missing")
    assert result["counts"]["contacts"]["created"] == 1
    assert result["counts"]["interviews"]["created"] == 1
    assert result["counts"]["import_mappings"]["created"] == 1
