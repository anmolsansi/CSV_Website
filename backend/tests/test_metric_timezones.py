import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, create_engine, inspect

from app.models import CsvRow, JobLifecycleEvent, JobTrack, User
from app.services.lifecycle import (
    backfill_legacy_applications,
    backfill_legacy_visits,
    legacy_backfill_warning_counts,
    local_day_utc_bounds,
    rolling_week_utc_bounds,
)


def test_kolkata_midnight_boundaries_are_shifted_to_utc():
    start, end = local_day_utc_bounds(
        "Asia/Kolkata",
        reference=datetime(2026, 9, 20, 1, 0, tzinfo=timezone.utc),
    )

    assert start == datetime(2026, 9, 19, 18, 30)
    assert end == datetime(2026, 9, 20, 18, 30)
    assert end - start == timedelta(hours=24)


def test_dst_23_and_25_hour_days_have_exact_local_boundaries():
    spring_start, spring_end = local_day_utc_bounds(
        "America/New_York",
        reference=datetime(2026, 3, 8, 16, 0, tzinfo=timezone.utc),
    )
    fall_start, fall_end = local_day_utc_bounds(
        "America/New_York",
        reference=datetime(2026, 11, 1, 17, 0, tzinfo=timezone.utc),
    )

    assert spring_start == datetime(2026, 3, 8, 5, 0)
    assert spring_end == datetime(2026, 3, 9, 4, 0)
    assert spring_end - spring_start == timedelta(hours=23)

    assert fall_start == datetime(2026, 11, 1, 4, 0)
    assert fall_end == datetime(2026, 11, 2, 5, 0)
    assert fall_end - fall_start == timedelta(hours=25)


def test_rolling_week_preserves_local_wall_clock_across_dst():
    start, end = rolling_week_utc_bounds(
        "America/New_York",
        reference=datetime(2026, 3, 10, 16, 0, tzinfo=timezone.utc),
    )
    assert start == datetime(2026, 3, 3, 17, 0)
    assert end == datetime(2026, 3, 10, 16, 0)
    assert end - start == timedelta(hours=167)


def test_profile_timezone_defaults_updates_and_rejects_invalid_input(client):
    email = f"jg010-profile-{uuid4().hex}@jobgrid.dev"
    login = client.post("/auth/dev-login", json={"email": email})
    assert login.status_code == 200

    initial = client.get("/crm/profile/timezone")
    assert initial.status_code == 200
    assert initial.json() == {"timezone": "UTC"}

    updated = client.patch(
        "/crm/profile/timezone",
        json={"timezone": "Asia/Kolkata"},
    )
    assert updated.status_code == 200
    assert updated.json() == {"timezone": "Asia/Kolkata"}
    assert client.get("/crm/profile/timezone").json() == {"timezone": "Asia/Kolkata"}

    for payload in (
        {"timezone": "+05:30"},
        {"timezone": "UTC+05:30"},
        {"timezone": "Mars/Olympus"},
        {"timezone": "UTC", "user_id": 999},
        {},
    ):
        response = client.patch("/crm/profile/timezone", json=payload)
        assert response.status_code == 422

    assert client.get("/crm/profile/timezone").json() == {"timezone": "Asia/Kolkata"}


def test_backfill_twice_keeps_same_first_event_count(db_session):
    suffix = uuid4().hex
    user = User(email=f"jg010-backfill-{suffix}@jobgrid.dev")
    db_session.add(user)
    db_session.flush()

    clicked_at = datetime(2026, 9, 1, 8, 15, 0)
    applied_at = datetime(2026, 9, 2, 13, 45, 0)
    row = CsvRow(
        user_id=user.id,
        upload_batch_id=f"batch-{suffix}",
        url=f"https://example.com/{suffix}/job",
        clicked=True,
        clicked_at=clicked_at,
    )
    db_session.add(row)
    db_session.flush()
    track = JobTrack(
        user_id=user.id,
        csv_row_id=row.id,
        url=row.url,
        status="applied",
        applied_at=applied_at,
    )
    db_session.add(track)
    db_session.commit()

    first_visit = backfill_legacy_visits(db_session, user_id=user.id)
    first_apply = backfill_legacy_applications(db_session, user_id=user.id)
    db_session.commit()

    assert first_visit["created"] == 1
    assert first_apply["created"] == 1
    first_events = (
        db_session.query(JobLifecycleEvent)
        .filter(
            JobLifecycleEvent.user_id == user.id,
            JobLifecycleEvent.kind.in_(["first_visited", "first_applied"]),
        )
        .order_by(JobLifecycleEvent.kind.asc())
        .all()
    )
    assert len(first_events) == 2
    assert {event.source for event in first_events} == {"legacy_backfill"}
    assert {
        event.kind: event.occurred_at for event in first_events
    } == {
        "first_visited": clicked_at,
        "first_applied": applied_at,
    }

    second_visit = backfill_legacy_visits(db_session, user_id=user.id)
    second_apply = backfill_legacy_applications(db_session, user_id=user.id)
    db_session.commit()

    assert second_visit["created"] == 0
    assert second_visit["already_present"] == 1
    assert second_apply["created"] == 0
    assert second_apply["already_present"] == 1
    assert (
        db_session.query(JobLifecycleEvent)
        .filter(
            JobLifecycleEvent.user_id == user.id,
            JobLifecycleEvent.kind.in_(["first_visited", "first_applied"]),
        )
        .count()
        == 2
    )


def test_known_clicked_at_is_visit_evidence_even_if_legacy_flag_is_false(db_session):
    suffix = uuid4().hex
    user = User(email=f"jg010-known-click-{suffix}@jobgrid.dev")
    db_session.add(user)
    db_session.flush()
    occurred_at = datetime(2026, 9, 4, 7, 30, 0)
    db_session.add(CsvRow(
        user_id=user.id,
        upload_batch_id=f"batch-{suffix}",
        url=f"https://example.com/{suffix}/known-click",
        clicked=False,
        clicked_at=occurred_at,
    ))
    db_session.commit()

    result = backfill_legacy_visits(db_session, user_id=user.id)
    db_session.commit()

    assert result["created"] == 1
    event = db_session.query(JobLifecycleEvent).filter_by(
        user_id=user.id,
        kind="first_visited",
    ).one()
    assert event.occurred_at == occurred_at


def test_dry_run_counts_known_facts_without_writing(db_session):
    suffix = uuid4().hex
    user = User(email=f"jg010-dry-{suffix}@jobgrid.dev")
    db_session.add(user)
    db_session.flush()
    row = CsvRow(
        user_id=user.id,
        upload_batch_id=f"batch-{suffix}",
        url=f"https://example.com/{suffix}/visit",
        clicked=True,
        clicked_at=datetime(2026, 9, 3, 12, 0, 0),
    )
    db_session.add(row)
    db_session.commit()

    result = backfill_legacy_visits(
        db_session,
        user_id=user.id,
        dry_run=True,
    )
    assert result["eligible"] == 1
    assert result["created"] == 1
    assert (
        db_session.query(JobLifecycleEvent)
        .filter(JobLifecycleEvent.user_id == user.id)
        .count()
        == 0
    )


def test_missing_applied_date_warns_and_fabricates_nothing(db_session):
    suffix = uuid4().hex
    user = User(email=f"jg010-missing-{suffix}@jobgrid.dev")
    db_session.add(user)
    db_session.flush()
    track = JobTrack(
        user_id=user.id,
        url=f"https://example.com/{suffix}/applied",
        status="applied",
        applied_at=None,
    )
    db_session.add(track)
    db_session.commit()

    result = backfill_legacy_applications(db_session, user_id=user.id)
    warnings = legacy_backfill_warning_counts(db_session, user_id=user.id)
    db_session.commit()

    assert result["scanned"] == 1
    assert result["eligible"] == 0
    assert result["created"] == 0
    assert result["missing_dates"] == 1
    assert warnings["applied_without_date"] == 1
    assert (
        db_session.query(JobLifecycleEvent)
        .filter(
            JobLifecycleEvent.user_id == user.id,
            JobLifecycleEvent.kind == "first_applied",
        )
        .count()
        == 0
    )


def test_timezone_migration_up_and_down_preserves_existing_user(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'timezone-migration.db'}")
    metadata = MetaData()
    users = Table(
        "users",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("email", String(320), nullable=False),
        Column("created_at", DateTime),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            users.insert().values(
                id=1,
                email="legacy@jobgrid.dev",
                created_at=datetime(2026, 9, 1, 0, 0, 0),
            )
        )

    migration_path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "005_user_timezone.py"
    )
    spec = importlib.util.spec_from_file_location("jg010_migration", migration_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        module.op = Operations(context)
        module.upgrade()

    inspector = inspect(engine)
    timezone_column = next(
        column for column in inspector.get_columns("users")
        if column["name"] == "timezone"
    )
    assert timezone_column["nullable"] is False
    with engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT timezone FROM users WHERE id = 1"
        ).scalar_one() == "UTC"

    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        module.op = Operations(context)
        module.downgrade()

    assert "timezone" not in {
        column["name"] for column in inspect(engine).get_columns("users")
    }
