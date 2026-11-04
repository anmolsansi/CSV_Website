import io
import json
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
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


# EXT-23/24: visit history is portable, but rate/receipt/session state is not.
def _add_visit(db, owner, url, first=datetime(2026, 11, 3, 11, 30)):
    from app.models import JobVisit
    from app.services.job_identity import canonicalize_job_url

    canonical = canonicalize_job_url(url)
    visit = JobVisit(
        user_id=owner,
        canonical_url=canonical.canonical_url,
        canonical_url_hash=canonical.canonical_url_hash,
        first_visited_at=first,
    )
    db.add(visit)
    db.commit()
    return visit


def _visit_backup(db, owner):
    from app.services.browser_memory_backup import export_backup_v2_with_browser_visits
    return export_backup_v2_with_browser_visits(db, owner)


def _visit_restore(db, owner, payload, mode):
    from app.services.browser_memory_backup import restore_backup_payload_with_browser_visits
    return restore_backup_payload_with_browser_visits(
        db, owner, json.dumps(payload).encode(), mode,
    )


def _read_visits(db, owner):
    from app.models import JobVisit
    with Session(db.get_bind()) as fresh:
        return [
            (
                visit.canonical_url,
                visit.first_visited_at.replace(tzinfo=None)
                if visit.first_visited_at.tzinfo is None
                else visit.first_visited_at.astimezone(timezone.utc).replace(tzinfo=None),
            )
            for visit in fresh.query(JobVisit).filter(JobVisit.user_id == owner).all()
        ]


def test_ext_23_json_and_zip_have_equal_owner_visit_facts(db_session, complete_backup, tmp_path, monkeypatch):
    from app.config import settings
    from app.browser_memory_backup_schemas import VISIT_BACKUP_KEY, validate_visit_extension
    from app.models import BrowserApplyReceipt, RequestWindowCounter

    source, target, _ = complete_backup
    visit = _add_visit(db_session, source, "https://jobs.example.test/23/a?req=7")
    _add_visit(db_session, target, "https://jobs.example.test/23/foreign?req=9")
    db_session.add(BrowserApplyReceipt(
        user_id=source, request_key=str(uuid4()), payload_hash="a" * 64,
        response_json={"secret": "must-not-export"}, created_at=datetime(2026, 11, 4, 10),
    ))
    db_session.add(RequestWindowCounter(
        user_id=source, scope="browser_memory_check",
        window_start=datetime(2026, 11, 4, 10), count=3,
    ))
    db_session.commit()
    direct = _visit_backup(db_session, source)
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_DIR", str(tmp_path / "documents"))
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")
    (tmp_path / "documents").mkdir()
    raw = backups.export_backup_bundle(db_session, source)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        zipped = json.loads(archive.read("backup.json"))
    for payload in (direct, zipped):
        assert len(validate_visit_extension(payload[VISIT_BACKUP_KEY])) == 1
        record = payload[VISIT_BACKUP_KEY]["visits"][0]
        assert record["canonical_url"] == visit.canonical_url
        assert record["canonical_url_hash"] == visit.canonical_url_hash
        assert "user_id" not in record and "id" not in record
        assert "f8_private" in payload and "f9_import_mappings" in payload
        serialized = json.dumps(payload)
        assert "must-not-export" not in serialized
        assert "browser_apply_receipts" not in serialized
        assert "request_window_counters" not in serialized
        assert "foreign?req=9" not in serialized
    # Unique backup IDs produce different backup-local UUIDs/checksums,
    # but the signed visit facts are equivalent within each snapshot.
    assert [
        (r["canonical_url"], r["canonical_url_hash"], r["first_visited_at"])
        for r in direct[VISIT_BACKUP_KEY]["visits"]
    ] == [
        (r["canonical_url"], r["canonical_url_hash"], r["first_visited_at"])
        for r in zipped[VISIT_BACKUP_KEY]["visits"]
    ]


def test_ext_24_visit_restore_replays_earliest(db_session, complete_backup):
    from app.models import JobVisit, BrowserApplyReceipt
    from app.browser_memory_backup_schemas import VISIT_BACKUP_KEY
    source, target, _ = complete_backup
    url = "https://jobs.example.test/24/a?req=42"
    _add_visit(db_session, source, url, datetime(2026, 11, 2, 7, 0))
    payload = _visit_backup(db_session, source)
    assert len(payload[VISIT_BACKUP_KEY]["visits"]) == 1
    preview = _visit_restore(db_session, target, payload, "verify_only")
    assert preview["verified"]
    assert preview["counts"]["job_visits"] == {"created": 1, "existing": 0}
    assert _read_visits(db_session, target) == []
    first = _visit_restore(db_session, target, payload, "merge_missing")
    assert first["counts"]["job_visits"]["created"] == 1
    assert _read_visits(db_session, target) == [(url, datetime(2026, 11, 2, 7, 0))]
    # Existing later timestamp does not overwrite earlier portable evidence.
    with Session(db_session.get_bind()) as fresh:
        item = fresh.query(JobVisit).filter_by(user_id=target).one()
        item.first_visited_at = datetime(2026, 11, 4, 10)
        fresh.commit()
    replay = _visit_restore(db_session, target, payload, "merge_missing")
    assert replay["counts"]["job_visits"] == {"created": 0, "existing": 1}
    assert _read_visits(db_session, target) == [(url, datetime(2026, 11, 2, 7, 0))]
    with Session(db_session.get_bind()) as fresh:
        assert fresh.query(BrowserApplyReceipt).filter_by(user_id=target).count() == 0
        assert fresh.query(JobVisit).filter_by(user_id=source).count() == 1


def test_ext_24_invalid_late_extension_rejects_entire_restore(db_session, complete_backup):
    from app.browser_memory_backup_schemas import VISIT_BACKUP_KEY
    source, target, _ = complete_backup
    _add_visit(db_session, source, "https://jobs.example.test/24/corrupt")
    payload = _visit_backup(db_session, source)
    payload[VISIT_BACKUP_KEY]["checksum_sha256"] = "0" * 64
    with pytest.raises(BackupContractError):
        _visit_restore(db_session, target, payload, "merge_missing")
    assert_empty(db_session, target)
    assert _read_visits(db_session, target) == []


def test_ext_24_union_over_quota_rejects_without_core_writes(db_session, complete_backup, monkeypatch):
    from app.services import browser_memory_backup
    source, target, _ = complete_backup
    _add_visit(db_session, source, "https://jobs.example.test/24/new")
    _add_visit(db_session, target, "https://jobs.example.test/24/old")
    payload = _visit_backup(db_session, source)
    monkeypatch.setattr(browser_memory_backup, "MAX_PORTABLE_VISITS", 1)
    with pytest.raises(BackupContractError, match="10,000-record limit"):
        _visit_restore(db_session, target, payload, "merge_missing")
    assert len(_read_visits(db_session, target)) == 1
    assert_empty(db_session, target)


def test_ext_24_late_visit_insert_failure_rolls_back_core(db_session, complete_backup):
    from app.models import JobVisit
    source, target, _ = complete_backup
    _add_visit(db_session, source, "https://jobs.example.test/24/fault")
    payload = _visit_backup(db_session, source)
    def fail_visit(mapper, connection, item):
        if item.user_id == target:
            raise RuntimeError("injected visit failure")
    event.listen(JobVisit, "before_insert", fail_visit)
    try:
        with pytest.raises(RuntimeError, match="injected visit failure"):
            _visit_restore(db_session, target, payload, "merge_missing")
    finally:
        event.remove(JobVisit, "before_insert", fail_visit)
    assert_empty(db_session, target)
    assert _read_visits(db_session, target) == []


def test_ext_24_legacy_backup_has_no_inferred_visits(db_session, complete_backup):
    source, target, payload = complete_backup
    assert "job_visits_v1" not in payload
    result = _visit_restore(db_session, target, payload, "merge_missing")
    assert result["verified"]
    assert _read_visits(db_session, target) == []


def test_ext_23_old_reader_rejects_unknown_visit_extension(db_session, complete_backup):
    from app.services import import_backups
    source, target, _ = complete_backup
    _add_visit(db_session, source, "https://jobs.example.test/23/legacy")
    payload = _visit_backup(db_session, source)
    with pytest.raises(BackupContractError):
        import_backups.restore_backup_payload_with_import_mappings(
            db_session, target, json.dumps(payload).encode(), "verify_only",
        )
    assert_empty(db_session, target)


def test_ext_24_zip_restore_commits_visits_with_existing_sections(db_session, complete_backup, tmp_path, monkeypatch):
    from app.config import settings
    source, target, _ = complete_backup
    _add_visit(db_session, source, "https://jobs.example.test/24/bundle")
    monkeypatch.setattr(settings, "DOCUMENT_STORAGE_DIR", str(tmp_path / "documents"))
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")
    (tmp_path / "documents").mkdir()
    raw = backups.export_backup_bundle(db_session, source)
    assert backups.restore_backup_bundle(db_session, target, raw, "verify_only")["counts"]["job_visits"]["created"] == 1
    assert _read_visits(db_session, target) == []
    result = backups.restore_backup_bundle(db_session, target, raw, "merge_missing")
    assert result["counts"]["job_visits"]["created"] == 1
    assert len(_read_visits(db_session, target)) == 1
    replay = backups.restore_backup_bundle(db_session, target, raw, "merge_missing")
    assert replay["counts"]["job_visits"]["created"] == 0
