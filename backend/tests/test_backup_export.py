import importlib.util
import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Column, Integer, MetaData, Table, create_engine, inspect

from app.backup_schemas import (
    BACKUP_SCHEMA_REVISION,
    BACKUP_V2_SECTIONS,
    compute_sections_checksum,
    validate_backup_v2,
)
from app.models import (
    ApplyPilotBatch,
    AuditEvent,
    ColumnPreference,
    CsvRow,
    JobTrack,
    JobLifecycleEvent,
    SavedView,
    SearchSession,
    UrlHistory,
    User,
    UserGoal,
)


def _login_and_seed(client, db, email):
    response = client.post("/auth/dev-login", json={"email": email})
    assert response.status_code == 200
    return _seed_complete_fixture(db, email=email)


def _seed_complete_fixture(db, email):
    user = db.query(User).filter_by(email=email).first()
    if user is None:
        user = User(email=email)
        db.add(user)
        db.flush()

    session = SearchSession(user_id=user.id, name="Search A", notes="notes")
    db.add(session)
    db.flush()

    row1 = CsvRow(
        user_id=user.id,
        upload_batch_id="batch-1",
        url=f"https://example.com/{user.id}/jobs/1",
        title="Engineer",
        clicked=True,
        clicked_at=datetime(2026, 9, 16, 9, 0, 0),
    )
    row2 = CsvRow(
        user_id=user.id,
        upload_batch_id="batch-1",
        url=f"https://example.com/{user.id}/jobs/2",
        title="Engineer II",
        is_duplicate=True,
    )
    db.add_all([row1, row2])
    db.flush()
    row2.duplicate_of_id = row1.id

    track = JobTrack(
        user_id=user.id,
        csv_row_id=row1.id,
        url=row1.url,
        status="applied",
        session_id=str(session.id),
        open_count=2,
        applied_at=datetime(2026, 9, 16, 10, 0, 0),
    )
    view = SavedView(
        user_id=user.id,
        name="My view",
        view_type="job_links",
        filters={"atsGroup": "greenhouse"},
        is_pinned=True,
    )
    history = UrlHistory(user_id=user.id, url=f"https://example.com/{user.id}/jobs/history")
    preference = ColumnPreference(user_id=user.id, hidden_columns=["error"], column_order=["title"])
    goal = UserGoal(user_id=user.id, open_per_day=10, apply_per_day=4, followup_per_day=2, applypilot_per_day=1)
    batch = ApplyPilotBatch(
        user_id=user.id,
        session_id=session.id,
        name="Batch A",
        payload_json=[{"url": row1.url}],
        status="downloaded",
        job_count=1,
    )
    db.add_all([track, view, history, preference, goal, batch])
    db.flush()

    lifecycle_event = JobLifecycleEvent(
        user_id=user.id,
        event_key=f"operation:{uuid4()}",
        job_url=row1.url,
        csv_row_id=row1.id,
        job_track_id=track.id,
        kind="status_changed",
        occurred_at=datetime(2026, 9, 16, 10, 0, 0),
        recorded_at=datetime(2026, 9, 16, 10, 1, 0),
        source="export_test",
        payload={"from": "opened", "to": "applied"},
    )
    db.add(lifecycle_event)

    event = AuditEvent(
        user_id=user.id,
        session_id=session.id,
        event_type="followup_set",
        entity_type="job_track",
        entity_id=track.id,
        metadata_json={"source": "test"},
    )
    db.add(event)
    db.commit()
    return user


def test_export_every_section(auth_client, db_session):
    user = _login_and_seed(auth_client, db_session, "backup-all@jobgrid.dev")

    response = auth_client.get("/crm/backup/export?version=2")
    assert response.status_code == 200
    payload = response.json()
    document = validate_backup_v2(payload)

    assert tuple(payload["sections"]) == BACKUP_V2_SECTIONS
    assert all(payload["counts"][name] > 0 for name in BACKUP_V2_SECTIONS)
    assert payload["counts"] == {
        name: len(payload["sections"][name]) for name in BACKUP_V2_SECTIONS
    }
    assert payload["checksum_sha256"] == compute_sections_checksum(payload["sections"])
    assert payload["version"] == "2.0"
    assert document.schema_revision == BACKUP_SCHEMA_REVISION
    assert "user_id" not in json.dumps(payload)

    track = payload["sections"]["job_tracks"][0]
    assert track["csv_row_ref"] is not None
    assert track["session_id"] is not None
    assert track["session_ref"] is None
    assert user.id > 0


def test_foreign_user_absent(auth_client, db_session):
    _login_and_seed(auth_client, db_session, "backup-isolation@jobgrid.dev")
    foreign = User(email="backup-foreign@jobgrid.dev")
    db_session.add(foreign)
    db_session.flush()
    db_session.add(CsvRow(
        user_id=foreign.id,
        upload_batch_id="foreign-batch",
        url="https://foreign.example/job",
        title="Foreign title",
    ))
    db_session.commit()

    payload = auth_client.get("/crm/backup/export?version=2").json()
    encoded = json.dumps(payload)
    assert "https://foreign.example/job" not in encoded
    assert "Foreign title" not in encoded


def test_export_reference_graph(auth_client, db_session):
    _login_and_seed(auth_client, db_session, "backup-refs@jobgrid.dev")
    payload = auth_client.get("/crm/backup/export?version=2").json()
    document = validate_backup_v2(payload)

    refs = {
        name: {item.backup_ref for item in getattr(document.sections, name)}
        for name in BACKUP_V2_SECTIONS
    }
    row_records = document.sections.csv_rows
    assert row_records[1].duplicate_of_ref in refs["csv_rows"]
    assert document.sections.job_tracks[0].csv_row_ref in refs["csv_rows"]
    assert document.sections.lifecycle_events[0].csv_row_ref in refs["csv_rows"]
    assert document.sections.lifecycle_events[0].job_track_ref in refs["job_tracks"]
    assert document.sections.audit_events[0].session_ref in refs["sessions"]
    assert document.sections.audit_events[0].entity_ref in refs["job_tracks"]
    assert document.sections.applypilot_batches[0].session_ref in refs["sessions"]


def test_v1_export_remains_default(auth_client, db_session):
    _login_and_seed(auth_client, db_session, "backup-v1@jobgrid.dev")
    default_payload = auth_client.get("/crm/backup/export").json()
    explicit_payload = auth_client.get("/crm/backup/export?version=1.0").json()

    assert default_payload["version"] == "1.0"
    assert explicit_payload["version"] == "1.0"
    assert "sections" not in default_payload


def test_migration_up_down_empty(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    metadata = MetaData()
    Table("users", metadata, Column("id", Integer, primary_key=True))
    metadata.create_all(engine)

    migration_path = Path(__file__).parents[1] / "alembic" / "versions" / "003_backup_import_maps.py"
    spec = importlib.util.spec_from_file_location("jg002_migration", migration_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        module.op = Operations(context)
        module.upgrade()

    inspector = inspect(engine)
    assert "backup_import_maps" in inspector.get_table_names()
    assert {"user_id", "backup_id", "section", "backup_ref", "target_id", "created_at"} <= {
        column["name"] for column in inspector.get_columns("backup_import_maps")
    }
    indexes = {index["name"]: index for index in inspector.get_indexes("backup_import_maps")}
    assert indexes["uq_backup_import_map_identity"]["unique"] == 1

    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        module.op = Operations(context)
        module.downgrade()

    assert "backup_import_maps" not in inspect(engine).get_table_names()
