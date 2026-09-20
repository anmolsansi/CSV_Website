import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

from app.models import (
    BackupImportMap,
    Base,
    CSV_COLUMNS,
    CsvRow,
    JobLifecycleEvent,
    MaintenanceStatus,
)


ROOT = Path(__file__).resolve().parents[1]


def test_csv_columns_exist_on_model():
    model_columns = set(CsvRow.__table__.columns.keys())
    missing = sorted(set(CSV_COLUMNS) - model_columns)
    assert missing == []


def test_models_are_bound_to_metadata():
    assert "csv_rows" in Base.metadata.tables
    assert "job_tracks" in Base.metadata.tables
    assert "saved_views" in Base.metadata.tables
    assert BackupImportMap.__tablename__ in Base.metadata.tables
    assert JobLifecycleEvent.__tablename__ in Base.metadata.tables
    assert MaintenanceStatus.__tablename__ in Base.metadata.tables


def test_csv_columns_are_covered_by_migrations():
    versions_dir = ROOT / "alembic" / "versions"
    migration_source = "\n".join(path.read_text() for path in versions_dir.glob("*.py"))
    missing = [
        column
        for column in CSV_COLUMNS
        if f'"{column}"' not in migration_source and f"'{column}'" not in migration_source
    ]
    assert missing == []


def test_alembic_has_single_head():
    cfg = Config(str(ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_heads() == ["007"]


def test_legacy_schema_patch_module_removed():
    assert not (ROOT / "app" / "schema.py").exists()


def test_maintenance_status_migration_up_and_down(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'maintenance-status.db'}")
    migration_path = ROOT / "alembic" / "versions" / "007_maintenance_status.py"
    spec = importlib.util.spec_from_file_location("jg014_migration", migration_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        module.op = Operations(context)
        module.upgrade()

    inspector = inspect(engine)
    assert "maintenance_status" in inspector.get_table_names()
    assert {
        "job_name",
        "outcome",
        "last_attempted_at",
        "last_successful_at",
        "last_failed_at",
        "result_json",
        "updated_at",
    } == {
        column["name"] for column in inspector.get_columns("maintenance_status")
    }

    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        module.op = Operations(context)
        module.downgrade()

    assert "maintenance_status" not in inspect(engine).get_table_names()
