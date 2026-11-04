"""EXT-06: owner-scoped visits, receipts and reversible disposable migration."""
import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.backup_schemas import MODEL_FIELD_INVENTORY
from app.database import create_jobgrid_engine
from app.models import BrowserApplyReceipt, JobVisit, User


def _user(session):
    user = User(email=f"ext06-{uuid4().hex}@example.test")
    session.add(user)
    session.flush()
    return user


def _visit(user_id, url="https://example.test/jobs/1", digest="a" * 64):
    return JobVisit(
        user_id=user_id, canonical_url=url, canonical_url_hash=digest
    )


def _receipt(user_id, key):
    return BrowserApplyReceipt(
        user_id=user_id,
        request_key=key,
        payload_hash="b" * 64,
        response_json={"status": "applied", "version": 1},
    )


def test_owner_scoped_uniqueness_preserves_two_accounts(db_session):
    owner, other = _user(db_session), _user(db_session)
    key = str(uuid4())
    db_session.add_all([_visit(owner.id), _receipt(owner.id, key)])
    db_session.commit()

    # DB constraints, not application-level races, reject duplicate writes.
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(_visit(owner.id))
            db_session.flush()
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.add(_receipt(owner.id, key))
            db_session.flush()

    db_session.add_all([_visit(other.id), _receipt(other.id, key)])
    db_session.commit()
    assert db_session.query(JobVisit).count() >= 2
    assert db_session.query(BrowserApplyReceipt).count() >= 2


def test_owner_delete_cascades_and_does_not_touch_other_owner(db_session):
    owner, other = _user(db_session), _user(db_session)
    db_session.add_all([
        _visit(owner.id), _receipt(owner.id, str(uuid4())),
        _visit(other.id), _receipt(other.id, str(uuid4())),
    ])
    db_session.commit()
    owner_id, other_id = owner.id, other.id

    # Raw DELETE proves the database FK cascade works without ORM help.
    db_session.execute(text("DELETE FROM users WHERE id = :id"), {"id": owner_id})
    db_session.commit()
    db_session.expire_all()
    assert db_session.query(JobVisit).filter_by(user_id=owner_id).count() == 0
    assert db_session.query(BrowserApplyReceipt).filter_by(user_id=owner_id).count() == 0
    assert db_session.query(JobVisit).filter_by(user_id=other_id).count() == 1
    assert db_session.query(BrowserApplyReceipt).filter_by(user_id=other_id).count() == 1


def test_new_tables_are_account_owned_and_inventory_is_complete():
    for cls, expected in (
        (JobVisit, {"id", "user_id", "canonical_url", "canonical_url_hash", "first_visited_at"}),
        (BrowserApplyReceipt, {
            "id", "user_id", "request_key", "payload_hash", "response_json", "created_at",
        }),
    ):
        assert set(cls.__table__.columns.keys()) == expected
        assert set(MODEL_FIELD_INVENTORY[cls.__name__]) == expected
        fks = list(cls.__table__.foreign_key_constraints)
        assert len(fks) == 1
        assert list(fks[0].elements)[0].ondelete == "CASCADE"
        assert cls.__table__.c.user_id.nullable is False

    assert MODEL_FIELD_INVENTORY["JobVisit"]["canonical_url"].disposition == "exported"
    assert MODEL_FIELD_INVENTORY["BrowserApplyReceipt"]["response_json"].disposition == "excluded"


def test_revision_019_upgrade_and_disposable_downgrade_preserve_legacy_data(tmp_path):
    engine = create_jobgrid_engine(f"sqlite:///{tmp_path / 'ext06.sqlite3'}")
    # Minimal populated old-schema fixture isolates this one additive revision.
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT NOT NULL)"))
        connection.execute(text(
            "CREATE TABLE legacy_job (id INTEGER PRIMARY KEY, created_at TEXT NOT NULL)"
        ))
        connection.execute(text("INSERT INTO users (id, email) VALUES (41, 'legacy@example.test')"))
        connection.execute(text(
            "INSERT INTO legacy_job (id, created_at) VALUES (12, '2026-01-01T12:30:00Z')"
        ))

    migration_path = (
        Path(__file__).resolve().parents[1] / "alembic" / "versions"
        / "019_browser_visits.py"
    )
    spec = importlib.util.spec_from_file_location("ext06_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    try:
        with engine.begin() as connection:
            migration.op = Operations(MigrationContext.configure(connection))
            migration.upgrade()
        inspector = inspect(engine)
        assert {"job_visits", "browser_apply_receipts"} <= set(inspector.get_table_names())
        assert {"uq_job_visits_user_hash"} == {
            c["name"] for c in inspector.get_unique_constraints("job_visits")
        }
        assert {"uq_browser_apply_receipts_user_key"} == {
            c["name"] for c in inspector.get_unique_constraints("browser_apply_receipts")
        }
        assert "ix_job_visits_user_first_visited" in {
            idx["name"] for idx in inspector.get_indexes("job_visits")
        }
        assert "ix_browser_apply_receipts_user_created" in {
            idx["name"] for idx in inspector.get_indexes("browser_apply_receipts")
        }
        with engine.connect() as connection:
            assert connection.execute(text(
                "SELECT created_at FROM legacy_job WHERE id = 12"
            )).scalar_one() == "2026-01-01T12:30:00Z"
            assert connection.execute(text("SELECT COUNT(*) FROM legacy_job")).scalar_one() == 1

        # Safe only because the two new tables contain no real user data.
        with engine.begin() as connection:
            migration.op = Operations(MigrationContext.configure(connection))
            migration.downgrade()
        assert "job_visits" not in inspect(engine).get_table_names()
        with engine.connect() as connection:
            assert connection.execute(text("SELECT COUNT(*) FROM legacy_job")).scalar_one() == 1
    finally:
        engine.dispose()
