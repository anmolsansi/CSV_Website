import copy
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.backup_schemas import MAX_BACKUP_JSON_BYTES, compute_sections_checksum, validate_backup_v2
from app.models import (
    ApplyPilotBatch,
    AuditEvent,
    BackupImportMap,
    ColumnPreference,
    CsvRow,
    JobTrack,
    SavedView,
    SearchSession,
    UrlHistory,
    User,
    UserGoal,
)
from app.services.backups import restore_backup_v2


def _login(client, email: str):
    response = client.post("/auth/dev-login", json={"email": email})
    assert response.status_code == 200
    return response.json()


def _seed_complete_source(db, email: str, suffix: str):
    user = db.query(User).filter_by(email=email).first()
    if user is None:
        user = User(email=email)
        db.add(user)
        db.flush()

    search_session = SearchSession(
        user_id=user.id,
        name=f"Restore search {suffix}",
        started_at=datetime(2026, 9, 16, 8, 0, 0),
        ended_at=datetime(2026, 9, 16, 11, 0, 0),
        notes="source session notes",
    )
    db.add(search_session)
    db.flush()

    row1 = CsvRow(
        user_id=user.id,
        upload_batch_id=f"batch-{suffix}",
        url=f"https://restore-{suffix}.example/jobs/1",
        company_guess=f"RestoreCo {suffix}",
        title="Backend Engineer",
        clicked=True,
        clicked_at=datetime(2026, 9, 16, 8, 30, 0),
        created_at=datetime(2026, 9, 16, 7, 30, 0),
        ats_group="greenhouse",
        jd_text="A" * 600,
    )
    row2 = CsvRow(
        user_id=user.id,
        upload_batch_id=f"batch-{suffix}",
        url=f"https://restore-{suffix}.example/jobs/2",
        company_guess=f"RestoreCo {suffix}",
        title="Applied Engineer",
        created_at=datetime(2026, 9, 16, 7, 45, 0),
        is_duplicate=True,
    )
    db.add_all([row1, row2])
    db.flush()
    row2.duplicate_of_id = row1.id

    history = UrlHistory(
        user_id=user.id,
        url=f"https://restore-{suffix}.example/history",
        first_seen_at=datetime(2026, 9, 15, 9, 0, 0),
    )
    track = JobTrack(
        user_id=user.id,
        csv_row_id=row2.id,
        url=row2.url,
        company=f"RestoreCo {suffix}",
        title="Applied Engineer",
        status="applied",
        opened_at=datetime(2026, 9, 16, 8, 15, 0),
        applied_at=datetime(2026, 9, 16, 10, 0, 0),
        follow_up_at=datetime(2026, 9, 20, 10, 0, 0),
        notes="source application notes",
        session_id=f"source-session-{suffix}",
        open_count=3,
        last_opened_at=datetime(2026, 9, 16, 9, 30, 0),
        created_at=datetime(2026, 9, 16, 8, 15, 0),
        updated_at=datetime(2026, 9, 16, 10, 5, 0),
    )
    view = SavedView(
        user_id=user.id,
        name=f"Restore view {suffix}",
        view_type="applications",
        filters={"status": "applied"},
        is_pinned=True,
        created_at=datetime(2026, 9, 16, 9, 0, 0),
    )
    preference = ColumnPreference(
        user_id=user.id,
        hidden_columns=["error"],
        column_order=["title", "company_guess"],
    )
    goal = UserGoal(
        user_id=user.id,
        open_per_day=25,
        apply_per_day=8,
        followup_per_day=4,
        applypilot_per_day=2,
    )
    batch = ApplyPilotBatch(
        user_id=user.id,
        session_id=search_session.id,
        name=f"Pilot {suffix}",
        payload_json=[{"url": row2.url}],
        status="downloaded",
        job_count=1,
        created_at=datetime(2026, 9, 16, 10, 10, 0),
        updated_at=datetime(2026, 9, 16, 10, 15, 0),
    )
    db.add_all([history, track, view, preference, goal, batch])
    db.flush()

    audit = AuditEvent(
        user_id=user.id,
        session_id=search_session.id,
        event_type="followup_set",
        entity_type="job_track",
        entity_id=track.id,
        metadata_json={"source": "restore-test"},
        created_at=datetime(2026, 9, 16, 10, 20, 0),
    )
    db.add(audit)
    db.commit()
    return user


def _export_fixture(client, db, suffix: str):
    source_email = f"jg003-source-{suffix}@jobgrid.dev"
    _login(client, source_email)
    _seed_complete_source(db, source_email, suffix)
    response = client.get("/crm/backup/export?version=2")
    assert response.status_code == 200
    payload = response.json()
    validate_backup_v2(payload)
    return payload


def _import(client, payload, *, mode="merge_missing"):
    return client.post(
        f"/crm/backup/import?mode={mode}",
        files={"file": ("backup.json", json.dumps(payload).encode("utf-8"), "application/json")},
    )


def _user(db, email: str):
    db.expire_all()
    return db.query(User).filter_by(email=email).one()


def test_restore_applied_company_notes_and_dates(auth_client, db_session):
    payload = _export_fixture(auth_client, db_session, "roundtrip")
    destination_email = "jg003-dest-roundtrip@jobgrid.dev"
    _login(auth_client, destination_email)

    response = _import(auth_client, payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["verified"] is True
    assert result["mode"] == "merge_missing"
    assert result["backup_id"] == payload["backup_id"]
    for section, expected in payload["counts"].items():
        assert result["counts"][section]["created"] == expected
        assert result["counts"][section]["skipped"] == 0
        assert result["counts"][section]["conflicts"] == 0

    apps = auth_client.get("/crm/applications", params={"q": "RestoreCo roundtrip"})
    assert apps.status_code == 200
    app_rows = apps.json()["rows"]
    assert len(app_rows) == 1
    restored = app_rows[0]
    assert restored["company"] == "RestoreCo roundtrip"
    assert restored["status"] == "applied"
    assert restored["notes"] == "source application notes"
    assert restored["applied_at"].startswith("2026-09-16T10:00:00")
    assert restored["follow_up_at"].startswith("2026-09-20T10:00:00")

    destination = _user(db_session, destination_email)
    row2 = db_session.query(CsvRow).filter_by(
        user_id=destination.id,
        url="https://restore-roundtrip.example/jobs/2",
    ).one()
    row1 = db_session.query(CsvRow).filter_by(
        user_id=destination.id,
        url="https://restore-roundtrip.example/jobs/1",
    ).one()
    assert row2.duplicate_of_id == row1.id
    assert db_session.query(UrlHistory).filter_by(user_id=destination.id).count() == 1
    assert db_session.query(SearchSession).filter_by(user_id=destination.id).count() == 1
    assert db_session.query(SavedView).filter_by(user_id=destination.id).count() == 1
    assert db_session.query(ApplyPilotBatch).filter_by(user_id=destination.id).count() == 1
    assert db_session.query(AuditEvent).filter_by(user_id=destination.id).count() == 1
    assert db_session.query(ColumnPreference).filter_by(user_id=destination.id).one().hidden_columns == ["error"]
    assert db_session.query(UserGoal).filter_by(user_id=destination.id).one().apply_per_day == 8


def test_verify_only_and_bounded_read(auth_client, db_session):
    payload = _export_fixture(auth_client, db_session, "verify")
    destination_email = "jg003-dest-verify@jobgrid.dev"
    _login(auth_client, destination_email)

    response = _import(auth_client, payload, mode="verify_only")
    assert response.status_code == 200
    result = response.json()
    assert result["verified"] is True
    assert all(
        result["counts"][section]["created"] == payload["counts"][section]
        for section in payload["counts"]
    )

    destination = _user(db_session, destination_email)
    assert db_session.query(CsvRow).filter_by(user_id=destination.id).count() == 0
    assert db_session.query(BackupImportMap).filter_by(user_id=destination.id).count() == 0

    oversized = b"{" + (b"x" * MAX_BACKUP_JSON_BYTES)
    too_large = auth_client.post(
        "/crm/backup/import",
        files={"file": ("large.json", oversized, "application/json")},
    )
    assert too_large.status_code == 413
    assert too_large.json()["detail"]["code"] == "backup_too_large"


def test_retry_and_concurrent_retry(auth_client, db_session, engine):
    payload = _export_fixture(auth_client, db_session, "retry")
    destination_email = "jg003-dest-retry@jobgrid.dev"
    _login(auth_client, destination_email)

    first = _import(auth_client, payload)
    second = _import(auth_client, payload)
    assert first.status_code == 200
    assert second.status_code == 200
    assert sum(v["created"] for v in second.json()["counts"].values()) == 0
    assert sum(v["skipped"] for v in second.json()["counts"].values()) == sum(payload["counts"].values())

    destination = _user(db_session, destination_email)
    assert db_session.query(JobTrack).filter_by(user_id=destination.id).count() == payload["counts"]["job_tracks"]
    assert db_session.query(BackupImportMap).filter_by(user_id=destination.id).count() == sum(payload["counts"].values())

    concurrent_user = User(email="jg003-dest-concurrent@jobgrid.dev")
    db_session.add(concurrent_user)
    db_session.commit()
    db_session.refresh(concurrent_user)
    concurrent_user_id = concurrent_user.id
    document = validate_backup_v2(payload)
    SessionLocal = sessionmaker(bind=engine)

    def run_restore():
        session = SessionLocal()
        try:
            return restore_backup_v2(session, concurrent_user_id, document, "merge_missing")
        finally:
            session.close()

    if engine.dialect.name == "postgresql":
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: run_restore(), range(2)))
    else:
        results = [run_restore(), run_restore()]

    assert sum(sum(v["created"] for v in r["counts"].values()) for r in results) == sum(payload["counts"].values())
    db_session.expire_all()
    assert db_session.query(CsvRow).filter_by(user_id=concurrent_user_id).count() == payload["counts"]["csv_rows"]
    assert db_session.query(JobTrack).filter_by(user_id=concurrent_user_id).count() == payload["counts"]["job_tracks"]
    assert db_session.query(BackupImportMap).filter_by(user_id=concurrent_user_id).count() == sum(payload["counts"].values())


def test_failure_on_last_section_rolls_back_all(auth_client, db_session):
    payload = _export_fixture(auth_client, db_session, "rollback")
    destination_email = "jg003-dest-rollback@jobgrid.dev"
    _login(auth_client, destination_email)

    def fail_audit_insert(_mapper, _connection, target):
        if target.event_type == "followup_set":
            raise IntegrityError("injected final-section constraint failure", {}, RuntimeError("injected"))

    event.listen(AuditEvent, "before_insert", fail_audit_insert)
    try:
        response = _import(auth_client, payload)
    finally:
        event.remove(AuditEvent, "before_insert", fail_audit_insert)

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "restore_failed"
    destination = _user(db_session, destination_email)
    for model in (CsvRow, UrlHistory, JobTrack, SavedView, SearchSession, AuditEvent, ApplyPilotBatch):
        assert db_session.query(model).filter_by(user_id=destination.id).count() == 0
    assert db_session.query(ColumnPreference).filter_by(user_id=destination.id).count() == 0
    assert db_session.query(UserGoal).filter_by(user_id=destination.id).count() == 0
    assert db_session.query(BackupImportMap).filter_by(user_id=destination.id).count() == 0


def test_merge_preserves_newer_destination(auth_client, db_session):
    payload = _export_fixture(auth_client, db_session, "merge")
    destination_email = "jg003-dest-merge@jobgrid.dev"
    _login(auth_client, destination_email)
    destination = _user(db_session, destination_email)

    destination_row = CsvRow(
        user_id=destination.id,
        upload_batch_id="destination-batch",
        url="https://restore-merge.example/jobs/2",
        company_guess="Destination Company",
        title="Destination title",
    )
    db_session.add(destination_row)
    db_session.flush()
    destination_track = JobTrack(
        user_id=destination.id,
        csv_row_id=destination_row.id,
        url=destination_row.url,
        company="Destination Company",
        title="Destination title",
        status="interview",
        notes="destination newer note",
        open_count=9,
        created_at=datetime(2026, 9, 16, 12, 0, 0),
        updated_at=datetime(2026, 9, 16, 12, 30, 0),
    )
    db_session.add(destination_track)
    db_session.commit()

    response = _import(auth_client, payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["counts"]["job_tracks"]["conflicts"] == 1
    assert any(
        warning["code"] == "destination_record_preserved" and warning.get("section") == "job_tracks"
        for warning in result["warnings"]
    )

    db_session.expire_all()
    preserved = db_session.query(JobTrack).filter_by(user_id=destination.id, url=destination_row.url).one()
    assert preserved.company == "Destination Company"
    assert preserved.title == "Destination title"
    assert preserved.status == "interview"
    assert preserved.notes == "destination newer note"
    assert preserved.open_count == 9


def test_wrong_account_and_reference_injection(auth_client, db_session):
    payload = _export_fixture(auth_client, db_session, "isolation")

    foreign = User(email="jg003-foreign@jobgrid.dev")
    db_session.add(foreign)
    db_session.flush()
    foreign_row = CsvRow(
        user_id=foreign.id,
        upload_batch_id="foreign",
        url="https://foreign.example/jobs/1",
        title="Foreign secret title",
    )
    db_session.add(foreign_row)
    db_session.commit()
    foreign_user_id = foreign.id
    foreign_row_id = foreign_row.id

    malicious = copy.deepcopy(payload)
    malicious["sections"]["job_tracks"][0]["csv_row_ref"] = str(foreign_row_id)
    malicious["checksum_sha256"] = compute_sections_checksum(malicious["sections"])

    destination_email = "jg003-dest-isolation@jobgrid.dev"
    _login(auth_client, destination_email)
    response = _import(auth_client, malicious)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "conflicting_reference_graph"

    destination = _user(db_session, destination_email)
    assert db_session.query(CsvRow).filter_by(user_id=destination.id).count() == 0
    assert db_session.query(JobTrack).filter_by(user_id=destination.id).count() == 0
    assert db_session.query(BackupImportMap).filter_by(user_id=destination.id).count() == 0
    assert db_session.query(CsvRow).filter_by(id=foreign_row_id, user_id=foreign_user_id).one().title == "Foreign secret title"


def test_v1_import_warns_about_incomplete_history(auth_client, db_session):
    destination_email = "jg003-dest-v1@jobgrid.dev"
    _login(auth_client, destination_email)
    payload = {
        "version": "1.0",
        "exported_at": "2026-09-16T12:00:00",
        "csv_rows": [
            {
                "url": "https://legacy.example/jobs/1",
                "company_guess": "Legacy Co",
                "title": "Legacy Engineer",
                "created_at": "2026-09-15T08:00:00",
            }
        ],
        "job_tracks": [
            {
                "url": "https://legacy.example/jobs/1",
                "company": "Legacy Co",
                "title": "Legacy Engineer",
                "status": "applied",
                "applied_at": "2026-09-15T10:00:00",
                "follow_up_at": None,
                "notes": "legacy note",
                "created_at": "2026-09-15T09:00:00",
            }
        ],
        "saved_views": [],
        "sessions": [],
        "audit_events": [],
        "applypilot_batches": [],
    }
    response = _import(auth_client, payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert any(warning["code"] == "incomplete_legacy_backup" for warning in result["warnings"])
    assert result["counts"]["job_tracks"]["created"] == 1

    destination = _user(db_session, destination_email)
    track = db_session.query(JobTrack).filter_by(user_id=destination.id, url="https://legacy.example/jobs/1").one()
    assert track.status == "applied"
    assert track.applied_at == datetime(2026, 9, 15, 10, 0, 0)
    assert track.notes == "legacy note"
