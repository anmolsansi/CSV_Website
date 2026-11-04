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



# EXT-07: this is pure validation, no network access or write endpoint.
from pydantic import ValidationError
from app.browser_memory_schemas import (
    BrowserApplyIn,
    BrowserCheckIn,
    BrowserMemoryValidationError,
    BrowserVisitIn,
    parse_browser_memory_payload,
    validate_apply_idempotency_key,
)


def test_ext_07_public_url_acceptance_and_private_url_rejection(monkeypatch):
    def no_dns(*args, **kwargs):
        raise AssertionError("URL validation must never resolve or fetch input")
    monkeypatch.setattr("socket.getaddrinfo", no_dns)

    assert BrowserCheckIn(url="https://jobs.example.test/roles/3").url.endswith("/3")
    for rejected in (
        "chrome://settings", "file:///etc/passwd", "javascript:alert(1)",
        "https://name:password@jobs.example.test/3",
        "http://localhost:8000/jobs/3",
        "http://127.0.0.1/jobs/3", "https://10.1.2.3/jobs/3",
        "https://192.168.1.20/jobs/3", "https://[::1]/jobs/3",
        "https://jobs.local/jobs/3", "http://0.0.0.0/jobs/3",
        "https://jobs.example.test/jobs/3?ToKeN=secret",
        "https://jobs.example.test/jobs/3?ACCESS_%74OKEN=secret",
    ):
        with pytest.raises(ValidationError):
            BrowserVisitIn(url=rejected)


def test_ext_07_url_and_text_boundaries_are_exact():
    prefix = "https://jobs.example.test/"
    maximum = prefix + "x" * (2048 - len(prefix))
    assert len(BrowserVisitIn(url=maximum).url) == 2048
    with pytest.raises(ValidationError):
        BrowserVisitIn(url=maximum + "x")

    assert BrowserCheckIn(url=prefix, company=None, title=None).company is None
    assert BrowserCheckIn(url=prefix, company="C" * 320, title="T" * 500)
    assert BrowserApplyIn(url=prefix, company="C" * 320, title="T" * 500, confirmed=True)
    for values in (
        {"company": "C" * 321, "title": "a", "confirmed": True},
        {"company": "a", "title": "T" * 501, "confirmed": True},
        {"company": " ", "title": "a", "confirmed": True},
        {"company": "a", "title": "\t", "confirmed": True},
        {"company": "a", "confirmed": True},
        {"title": "a", "confirmed": True},
    ):
        with pytest.raises(ValidationError):
            BrowserApplyIn(url=prefix, **values)


def test_ext_07_strict_confirmation_unknown_fields_and_uuid_contract():
    url = "https://jobs.example.test/123"
    for confirmed in (1, "true", "True", False, None, 0):
        with pytest.raises(ValidationError):
            BrowserApplyIn(url=url, company="A", title="Engineer", confirmed=confirmed)
    for payload in (
        {"url": url, "user_id": 500},
        {"url": url, "owner_id": 500},
        {"url": url, "unexpected": None},
        {"url": url, "company": 22},
    ):
        with pytest.raises(BrowserMemoryValidationError) as error:
            parse_browser_memory_payload("check", payload)
        assert error.value.status_code == 422
        assert error.value.as_detail()["code"] == "invalid_browser_memory_payload"
        assert "url" not in error.value.as_detail().get("message", "")

    key = str(uuid4())
    assert validate_apply_idempotency_key(key) == key
    for invalid in (None, 1, "not-a-uuid", "0" * 32):
        with pytest.raises(BrowserMemoryValidationError) as error:
            validate_apply_idempotency_key(invalid)
        assert error.value.as_detail()["field"] == "Idempotency-Key"



# EXT-08: service tests use the existing disposable database fixtures.
from hashlib import sha256
from app.services.browser_memory import (
    MAX_BROWSER_VISITS_PER_OWNER,
    BrowserVisitConflict,
    save_browser_visit,
)


def test_ext_08_first_visit_and_replay_preserve_timestamp_and_owner(db_session):
    first_user, second_user = _user(db_session), _user(db_session)
    db_session.commit()
    url = "https://jobs.example.test/job/first?utm_source=fixture"
    first = save_browser_visit(db_session, user_id=first_user.id, url=url)
    assert first.created is True
    assert first.as_response()["protocol_version"] == 1
    assert first.as_response()["account_id"] == first_user.id
    assert first.as_response()["first_visited_at"].endswith("Z")
    db_session.commit()

    replay = save_browser_visit(
        db_session, user_id=first_user.id, url="https://jobs.example.test/job/first"
    )
    assert replay.created is False
    assert replay.first_visited_at == first.first_visited_at
    db_session.commit()
    assert db_session.query(JobVisit).filter_by(user_id=first_user.id).count() == 1

    other = save_browser_visit(db_session, user_id=second_user.id, url=url)
    assert other.created is True
    db_session.commit()
    assert db_session.query(JobVisit).filter_by(user_id=second_user.id).count() == 1


def test_ext_08_limit_per_owner_allows_existing_retry(db_session):
    owner = _user(db_session)
    db_session.commit()
    original = "https://jobs.example.test/job/original"
    saved = save_browser_visit(db_session, user_id=owner.id, url=original)
    db_session.commit()

    # Fast synthetic bulk fixture exercises the actual 10,000-row limit.
    rows = []
    for number in range(MAX_BROWSER_VISITS_PER_OWNER - 1):
        canonical = f"https://jobs.example.test/role/{number}"
        rows.append({
            "user_id": owner.id, "canonical_url": canonical,
            "canonical_url_hash": sha256(canonical.encode("utf-8")).hexdigest(),
        })
    db_session.execute(JobVisit.__table__.insert(), rows)
    db_session.commit()
    before = db_session.query(JobVisit).filter_by(user_id=owner.id).count()
    assert before == 10000
    replay = save_browser_visit(db_session, user_id=owner.id, url=original)
    assert replay.created is False
    assert replay.first_visited_at == saved.first_visited_at

    with pytest.raises(BrowserVisitConflict) as error:
        save_browser_visit(
            db_session, user_id=owner.id, url="https://jobs.example.test/role/new"
        )
    assert error.value.status_code == 409
    assert error.value.code == "visit_limit_reached"
    assert db_session.query(JobVisit).filter_by(user_id=owner.id).count() == before


def test_ext_08_hash_collision_and_rollback_do_not_merge(db_session):
    owner = _user(db_session)
    db_session.commit()
    requested = "https://jobs.example.test/job/desired"
    digest = sha256(requested.encode("utf-8")).hexdigest()
    db_session.add(_visit(owner.id, url="https://jobs.example.test/job/other", digest=digest))
    db_session.commit()
    with pytest.raises(BrowserVisitConflict) as error:
        save_browser_visit(db_session, user_id=owner.id, url=requested)
    assert error.value.code == "identity_conflict"
    assert db_session.query(JobVisit).filter_by(user_id=owner.id).count() == 1

    rollback_url = "https://jobs.example.test/job/rollback"
    save_browser_visit(db_session, user_id=owner.id, url=rollback_url)
    db_session.rollback()
    assert db_session.query(JobVisit).filter_by(
        user_id=owner.id,
        canonical_url_hash=sha256(rollback_url.encode("utf-8")).hexdigest(),
    ).count() == 0
