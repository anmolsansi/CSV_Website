from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.models import Base, CSV_COLUMNS, CsvRow


ROOT = Path(__file__).resolve().parents[1]


def test_csv_columns_exist_on_model():
    model_columns = set(CsvRow.__table__.columns.keys())
    missing = sorted(set(CSV_COLUMNS) - model_columns)
    assert missing == []


def test_models_are_bound_to_metadata():
    assert "csv_rows" in Base.metadata.tables
    assert "job_tracks" in Base.metadata.tables
    assert "saved_views" in Base.metadata.tables


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
    assert script.get_heads() == ["002"]


def test_legacy_schema_patch_module_removed():
    assert not (ROOT / "app" / "schema.py").exists()
