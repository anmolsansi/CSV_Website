import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from pydantic import ValidationError
from sqlalchemy import Column, DateTime, ForeignKey, Integer, MetaData, Table, create_engine, select
from sqlalchemy.exc import IntegrityError

from app.models import CsvRow, JobTrack, SavedView, User, WorkItem, WorkItemOverride
from app.today_schemas import (
    TodayContractError,
    WorkItemCreate,
    WorkItemStored,
    followup_action_key,
    manual_action_key,
    validate_owned_action_key,
    validate_owned_work_item_sources,
)


ROOT = Path(__file__).resolve().parents[1]


def _user(db_session, prefix: str) -> User:
    user = User(email=f"{prefix}-{uuid4()}@example.test")
    db_session.add(user)
    db_session.flush()
    return user


def test_owned_action_key_rejects_foreign_track(db_session):
    owner = _user(db_session, "today-owner")
    foreign = _user(db_session, "today-foreign")
    due = datetime(2026, 9, 22, 9, 30, 0)
    track = JobTrack(
        user_id=foreign.id,
        url=f"https://example.test/jobs/{uuid4()}",
        status="follow_up",
        follow_up_at=due,
    )
    db_session.add(track)
    db_session.commit()

    key = followup_action_key(track.id, due)
    with pytest.raises(TodayContractError) as exc:
        validate_owned_action_key(db_session, owner.id, key)

    assert (exc.value.status_code, exc.value.code) == (404, "action_not_found")


def test_manual_action_key_requires_owned_work_item(db_session):
    owner = _user(db_session, "manual-owner")
    foreign = _user(db_session, "manual-foreign")
    item = WorkItem(
        user_id=foreign.id,
        description="Call recruiter",
        priority=1,
        state="pending",
        version=1,
    )
    db_session.add(item)
    db_session.commit()

    with pytest.raises(TodayContractError) as exc:
        validate_owned_action_key(db_session, owner.id, manual_action_key(item.id))

    assert (exc.value.status_code, exc.value.code) == (404, "action_not_found")


def test_followup_key_changes_when_followup_date_changes(db_session):
    owner = _user(db_session, "followup-owner")
    original = datetime(2026, 9, 22, 9, 30, 0)
    track = JobTrack(
        user_id=owner.id,
        url=f"https://example.test/jobs/{uuid4()}",
        status="follow_up",
        follow_up_at=original,
    )
    db_session.add(track)
    db_session.commit()

    old_key = followup_action_key(track.id, original)
    kind, resolved = validate_owned_action_key(db_session, owner.id, old_key)
    assert kind == "followup"
    assert resolved.id == track.id

    track.follow_up_at = datetime(2026, 9, 23, 9, 30, 0)
    db_session.commit()

    with pytest.raises(TodayContractError) as exc:
        validate_owned_action_key(db_session, owner.id, old_key)
    assert (exc.value.status_code, exc.value.code) == (404, "action_not_found")


def test_owned_source_validation_rejects_foreign_ids(db_session):
    owner = _user(db_session, "sources-owner")
    foreign = _user(db_session, "sources-foreign")
    row = CsvRow(
        user_id=foreign.id,
        upload_batch_id="foreign",
        url=f"https://example.test/jobs/{uuid4()}",
    )
    track = JobTrack(
        user_id=foreign.id,
        url=f"https://example.test/applications/{uuid4()}",
        status="opened",
    )
    view = SavedView(
        user_id=foreign.id,
        name=f"Foreign {uuid4()}",
        view_type="job_links",
    )
    db_session.add_all([row, track, view])
    db_session.commit()

    for kwargs in (
        {"track_id": track.id},
        {"row_id": row.id},
        {"source_view_id": view.id},
    ):
        with pytest.raises(TodayContractError) as exc:
            validate_owned_work_item_sources(db_session, owner.id, **kwargs)
        assert (exc.value.status_code, exc.value.code) == (404, "source_not_found")


def test_work_item_contract_trims_and_normalizes_utc():
    contract = WorkItemCreate(
        description="  Send portfolio  ",
        due_at=datetime(2026, 9, 22, 18, 0, tzinfo=timezone.utc),
        priority=3,
    )
    assert contract.description == "Send portfolio"
    assert contract.due_at == datetime(2026, 9, 22, 18, 0, tzinfo=timezone.utc)

    with pytest.raises(ValidationError):
        WorkItemCreate(description="   ")
    with pytest.raises(ValidationError):
        WorkItemCreate(description="x" * 501)
    with pytest.raises(ValidationError):
        WorkItemCreate(description="ok", priority=4)
    with pytest.raises(ValidationError):
        WorkItemCreate(description="ok", due_at=datetime(2026, 9, 22, 18, 0))


def test_done_timestamp_constraint(db_session):
    owner = _user(db_session, "done-constraint")
    db_session.add(
        WorkItem(
            user_id=owner.id,
            description="Record interview outcome",
            priority=1,
            state="done",
            version=1,
            completed_at=None,
        )
    )

    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()

    with pytest.raises(ValidationError):
        WorkItemStored(description="Record interview outcome", state="done")


def test_origin_key_is_unique_per_owner(db_session):
    owner = _user(db_session, "origin-owner")
    other = _user(db_session, "origin-other")
    key = "view:1:row:1"
    db_session.add_all(
        [
            WorkItem(
                user_id=owner.id,
                description="Review first match",
                origin_key=key,
                priority=1,
                state="pending",
                version=1,
            ),
            WorkItem(
                user_id=other.id,
                description="Review first match",
                origin_key=key,
                priority=1,
                state="pending",
                version=1,
            ),
        ]
    )
    db_session.commit()

    db_session.add(
        WorkItem(
            user_id=owner.id,
            description="Duplicate source action",
            origin_key=key,
            priority=1,
            state="pending",
            version=1,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_override_version_must_be_positive(db_session):
    owner = _user(db_session, "override-version")
    db_session.add(
        WorkItemOverride(
            user_id=owner.id,
            action_key="followup:1:2026-09-22T09:30:00Z",
            snoozed_until=datetime(2026, 9, 23, 9, 30, tzinfo=timezone.utc),
            version=0,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def _load_today_migration():
    path = ROOT / "alembic" / "versions" / "008_today_queue.py"
    spec = importlib.util.spec_from_file_location("jg025_today_migration", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_migration_preserves_existing_followups(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'today-migration.db'}")
    metadata = MetaData()
    users = Table(
        "users",
        metadata,
        Column("id", Integer, primary_key=True),
    )
    csv_rows = Table(
        "csv_rows",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    )
    job_tracks = Table(
        "job_tracks",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        Column("follow_up_at", DateTime(), nullable=True),
    )
    saved_views = Table(
        "saved_views",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    )
    due = datetime(2026, 9, 22, 9, 30, 0)

    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        metadata.create_all(connection)
        connection.execute(users.insert().values(id=1))
        connection.execute(csv_rows.insert().values(id=10, user_id=1))
        connection.execute(job_tracks.insert().values(id=20, user_id=1, follow_up_at=due))
        connection.execute(saved_views.insert().values(id=30, user_id=1))

        migration = _load_today_migration()
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()

        preserved = connection.execute(
            select(job_tracks.c.follow_up_at).where(job_tracks.c.id == 20)
        ).scalar_one()
        assert preserved == due

        connection.exec_driver_sql(
            """
            INSERT INTO work_items
              (id, user_id, track_id, row_id, source_view_id, origin_key,
               description, due_at, priority, state, version, created_at,
               updated_at, completed_at)
            VALUES
              (40, 1, 20, 10, 30, 'view:30:row:10',
               'Review saved-view match', NULL, 1, 'pending', 1,
               '2026-09-21 10:00:00', '2026-09-21 10:00:00', NULL)
            """
        )

        connection.execute(job_tracks.delete().where(job_tracks.c.id == 20))
        connection.execute(csv_rows.delete().where(csv_rows.c.id == 10))
        connection.execute(saved_views.delete().where(saved_views.c.id == 30))

        detached = connection.exec_driver_sql(
            "SELECT track_id, row_id, source_view_id, description FROM work_items WHERE id = 40"
        ).one()
        assert detached == (None, None, None, "Review saved-view match")

        migration.downgrade()
        assert "work_items" not in {
            row[0]
            for row in connection.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

    engine.dispose()
