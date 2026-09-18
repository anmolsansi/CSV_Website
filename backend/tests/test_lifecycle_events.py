import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models import CsvRow, JobLifecycleEvent, JobTrack, User
from app.services.lifecycle import (
    LifecycleEventError,
    count_applied,
    count_saved,
    count_visited,
    first_event_key,
    validate_event_payload,
    write_event,
)


def _user(db, prefix: str) -> User:
    user = User(email=f"{prefix}-{uuid.uuid4()}@example.test")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.mark.parametrize("kind", ["first_visited", "first_applied"])
def test_first_event_replay(db_session, kind):
    user = _user(db_session, f"jg008-{kind}")
    occurred_at = datetime(2026, 9, 18, 4, 30, 0, tzinfo=timezone.utc)
    url = f"https://events.example/{kind}"

    keys = {
        write_event(
            db_session,
            user_id=user.id,
            job_url=url,
            kind=kind,
            occurred_at=occurred_at,
            source="test",
        ).event_key
        for _ in range(20)
    }
    db_session.commit()

    events = db_session.query(JobLifecycleEvent).filter_by(
        user_id=user.id, kind=kind
    ).all()
    assert len(events) == 1
    assert keys == {first_event_key(user.id, url, kind)}
    assert events[0].occurred_at == datetime(2026, 9, 18, 4, 30, 0)


def test_first_event_insert_is_idempotent_on_sqlite():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    with Session(engine) as session:
        user = User(email="jg008-sqlite@example.test")
        session.add(user)
        session.commit()
        session.refresh(user)

        for _ in range(20):
            write_event(
                session,
                user_id=user.id,
                job_url="https://sqlite.example/job/1",
                kind="first_applied",
                occurred_at=datetime(2026, 9, 18, 5, 0, 0),
                source="sqlite_test",
            )
        session.commit()

        assert session.query(JobLifecycleEvent).filter_by(
            user_id=user.id, kind="first_applied"
        ).count() == 1


def test_event_keys_and_payload_allowlists():
    key_a = first_event_key(7, "https://example.test/jobs/1", "first_visited")
    key_b = first_event_key(7, "https://example.test/jobs/1", "first_visited")
    key_other_url = first_event_key(7, "https://example.test/jobs/2", "first_visited")
    key_other_kind = first_event_key(7, "https://example.test/jobs/1", "first_applied")
    assert key_a == key_b
    assert key_a != key_other_url
    assert key_a != key_other_kind

    assert validate_event_payload("status_changed", {"from": "applied", "to": "interview"}) == {
        "from": "applied",
        "to": "interview",
    }
    with pytest.raises(LifecycleEventError) as exc:
        validate_event_payload("unknown", {})
    assert exc.value.code == "unknown_event_kind"

    with pytest.raises(LifecycleEventError) as exc:
        validate_event_payload("first_visited", {"notes": "must not be stored"})
    assert exc.value.code == "invalid_event_payload"


def test_event_owner_rejects_foreign_links(db_session):
    owner = _user(db_session, "jg008-owner")
    foreign = _user(db_session, "jg008-foreign")
    foreign_row = CsvRow(
        user_id=foreign.id,
        upload_batch_id="foreign",
        url="https://foreign.example/job/1",
    )
    foreign_track = JobTrack(
        user_id=foreign.id,
        url="https://foreign.example/job/1",
        status="opened",
    )
    db_session.add_all([foreign_row, foreign_track])
    db_session.commit()

    with pytest.raises(LifecycleEventError) as exc:
        write_event(
            db_session,
            user_id=owner.id,
            job_url=foreign_row.url,
            kind="first_visited",
            occurred_at=datetime(2026, 9, 18, 6, 0, 0),
            source="test",
            csv_row_id=foreign_row.id,
        )
    assert exc.value.code == "inaccessible_csv_row"

    with pytest.raises(LifecycleEventError) as exc:
        write_event(
            db_session,
            user_id=owner.id,
            job_url=foreign_track.url,
            kind="first_applied",
            occurred_at=datetime(2026, 9, 18, 6, 5, 0),
            source="test",
            job_track_id=foreign_track.id,
        )
    assert exc.value.code == "inaccessible_job_track"
    assert db_session.query(JobLifecycleEvent).filter_by(user_id=owner.id).count() == 0


def test_transaction_rollback_removes_parent_and_event(db_session, engine):
    user = _user(db_session, "jg008-rollback")
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    url = f"https://rollback.example/{uuid.uuid4()}"
    try:
        with pytest.raises(RuntimeError):
            with session.begin():
                row = CsvRow(
                    user_id=user.id,
                    upload_batch_id="rollback",
                    url=url,
                )
                session.add(row)
                session.flush()
                write_event(
                    session,
                    user_id=user.id,
                    job_url=url,
                    kind="first_visited",
                    occurred_at=datetime(2026, 9, 18, 7, 0, 0),
                    source="test",
                    csv_row_id=row.id,
                )
                raise RuntimeError("synthetic parent mutation failure")
    finally:
        session.close()

    db_session.expire_all()
    assert db_session.query(CsvRow).filter_by(user_id=user.id, url=url).count() == 0
    assert db_session.query(JobLifecycleEvent).filter_by(user_id=user.id).count() == 0


def test_metric_definitions_keep_saved_visited_and_applied_distinct(db_session):
    user = _user(db_session, "jg008-metrics")
    saved = JobTrack(
        user_id=user.id,
        url="https://metrics.example/saved",
        status="opened",
        created_at=datetime(2026, 9, 18, 8, 0, 0),
    )
    db_session.add(saved)
    db_session.flush()

    write_event(
        db_session,
        user_id=user.id,
        job_url="https://metrics.example/visited",
        kind="first_visited",
        occurred_at=datetime(2026, 9, 18, 8, 30, 0),
        source="test",
    )
    write_event(
        db_session,
        user_id=user.id,
        job_url="https://metrics.example/applied",
        kind="first_applied",
        occurred_at=datetime(2026, 9, 18, 9, 0, 0),
        source="test",
    )
    db_session.commit()

    start = datetime(2026, 9, 18, 0, 0, 0, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    assert count_saved(db_session, user_id=user.id, start=start, end=end) == 1
    assert count_visited(db_session, user_id=user.id, start=start, end=end) == 1
    assert count_applied(db_session, user_id=user.id, start=start, end=end) == 1
