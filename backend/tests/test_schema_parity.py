import importlib.util
import os
import re
from pathlib import Path
from unittest.mock import patch

import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import UniqueConstraint, create_engine, inspect, text
from sqlalchemy.engine import make_url

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


_TEST_DATABASE_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")


def _alembic_config() -> Config:
    return Config(str(ROOT / "alembic.ini"))


def _run_alembic_upgrade(database_url: str) -> None:
    with patch.dict(os.environ, {"DATABASE_URL": database_url}):
        command.upgrade(_alembic_config(), "head")


def _admin_engine(database_url: str):
    parsed = make_url(database_url)
    admin_url = parsed.set(database="postgres")
    return create_engine(admin_url, isolation_level="AUTOCOMMIT")


def _validated_disposable_database_name(database_url: str) -> str:
    parsed = make_url(database_url)
    database_name = parsed.database or ""
    if (
        not _TEST_DATABASE_NAME_RE.fullmatch(database_name)
        or "test" not in database_name.lower()
        or database_name.lower() in {"postgres", "template0", "template1"}
    ):
        pytest.fail(
            "TEST_DATABASE_URL must target a simple, explicitly disposable "
            "PostgreSQL test database name"
        )
    return database_name


def _drop_postgres_database(database_url: str) -> None:
    database_name = _validated_disposable_database_name(database_url)
    admin = _admin_engine(database_url)
    try:
        with admin.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) "
                    "FROM pg_stat_activity "
                    "WHERE datname = :database_name "
                    "AND pid <> pg_backend_pid()"
                ),
                {"database_name": database_name},
            )
            connection.exec_driver_sql(
                f'DROP DATABASE IF EXISTS "{database_name}"'
            )
    finally:
        admin.dispose()


def _recreate_postgres_database(database_url: str) -> None:
    database_name = _validated_disposable_database_name(database_url)
    _drop_postgres_database(database_url)

    admin = _admin_engine(database_url)
    try:
        with admin.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
    finally:
        admin.dispose()


@pytest.fixture(scope="module")
def migrated_postgres_database(postgres_test_url):
    _recreate_postgres_database(postgres_test_url)
    try:
        _run_alembic_upgrade(postgres_test_url)
        engine = create_engine(postgres_test_url, pool_pre_ping=True)
        try:
            yield postgres_test_url, engine
        finally:
            engine.dispose()
    finally:
        _drop_postgres_database(postgres_test_url)


def _metadata_indexes(table):
    return {
        (
            tuple(column.name for column in index.columns),
            bool(index.unique),
        )
        for index in table.indexes
    }


def _actual_indexes(inspector, table_name):
    unique_columns = _actual_unique_constraints(inspector, table_name)
    signatures = set()

    for index in inspector.get_indexes(table_name):
        columns = tuple(index.get("column_names") or ())
        is_unique = bool(index.get("unique"))

        # PostgreSQL may expose the physical index that backs a UNIQUE
        # constraint without setting duplicates_constraint. The constraint is
        # compared separately below, so do not count its backing index twice.
        if is_unique and columns in unique_columns:
            continue
        signatures.add((columns, is_unique))

    return signatures


def _metadata_unique_constraints(table):
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def _actual_unique_constraints(inspector, table_name):
    return {
        tuple(constraint.get("column_names") or ())
        for constraint in inspector.get_unique_constraints(table_name)
    }


def _normalize_ondelete(value):
    return (value or "").upper()


def _metadata_foreign_keys(table):
    signatures = set()
    for constraint in table.foreign_key_constraints:
        elements = list(constraint.elements)
        signatures.add(
            (
                tuple(element.parent.name for element in elements),
                elements[0].column.table.name,
                tuple(element.column.name for element in elements),
                _normalize_ondelete(elements[0].ondelete),
            )
        )
    return signatures


def _actual_foreign_keys(inspector, table_name):
    signatures = set()
    for constraint in inspector.get_foreign_keys(table_name):
        options = constraint.get("options") or {}
        signatures.add(
            (
                tuple(constraint.get("constrained_columns") or ()),
                constraint.get("referred_table"),
                tuple(constraint.get("referred_columns") or ()),
                _normalize_ondelete(options.get("ondelete")),
            )
        )
    return signatures


def _assert_postgres_matches_metadata(engine):
    inspector = inspect(engine)
    actual_tables = set(inspector.get_table_names()) - {"alembic_version"}
    expected_tables = set(Base.metadata.tables)

    assert actual_tables == expected_tables

    for table_name in sorted(expected_tables):
        table = Base.metadata.tables[table_name]
        actual_columns = {
            column["name"]: column for column in inspector.get_columns(table_name)
        }
        expected_columns = {column.name: column for column in table.columns}

        assert set(actual_columns) == set(expected_columns), table_name
        assert {
            name: bool(column["nullable"])
            for name, column in actual_columns.items()
        } == {
            name: bool(column.nullable)
            for name, column in expected_columns.items()
        }, table_name
        assert _actual_indexes(inspector, table_name) == _metadata_indexes(table), (
            table_name
        )
        assert _actual_unique_constraints(
            inspector, table_name
        ) == _metadata_unique_constraints(table), table_name
        assert _actual_foreign_keys(
            inspector, table_name
        ) == _metadata_foreign_keys(table), table_name


def _schema_fingerprint(engine):
    inspector = inspect(engine)
    fingerprint = []

    for table_name in sorted(inspector.get_table_names()):
        fingerprint.append(
            (
                table_name,
                tuple(
                    sorted(
                        (
                            column["name"],
                            bool(column["nullable"]),
                        )
                        for column in inspector.get_columns(table_name)
                    )
                ),
                tuple(sorted(_actual_indexes(inspector, table_name))),
                tuple(sorted(_actual_unique_constraints(inspector, table_name))),
                tuple(sorted(_actual_foreign_keys(inspector, table_name))),
            )
        )

    return tuple(fingerprint)


def _current_revision(engine):
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


@pytest.mark.postgresql
def test_fresh_postgres_matches_metadata(migrated_postgres_database):
    _database_url, engine = migrated_postgres_database

    _assert_postgres_matches_metadata(engine)
    assert _current_revision(engine) == ScriptDirectory.from_config(
        _alembic_config()
    ).get_current_head()


@pytest.mark.postgresql
def test_migration_replay_is_noop(migrated_postgres_database):
    database_url, engine = migrated_postgres_database
    expected_head = ScriptDirectory.from_config(_alembic_config()).get_current_head()

    before = _schema_fingerprint(engine)
    assert _current_revision(engine) == expected_head

    _run_alembic_upgrade(database_url)

    after = _schema_fingerprint(engine)
    assert _current_revision(engine) == expected_head
    assert after == before
