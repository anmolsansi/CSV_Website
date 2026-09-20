from datetime import datetime

from app.config import settings
from app.jobs import cleanup_clicked_rows
from app.models import CsvRow, JobTrack, User


def _reset_and_seed(auth_client):
    reset = auth_client.post("/test/reset")
    assert reset.status_code == 200
    seed = auth_client.post("/test/seed")
    assert seed.status_code == 200
    rows = auth_client.get("/rows").json()["rows"]
    assert len(rows) >= 2
    return rows


def test_archive_twice_preserves_timestamp(auth_client, db_session):
    rows = _reset_and_seed(auth_client)
    row_id = rows[0]["id"]

    first = auth_client.request(
        "DELETE",
        "/rows",
        json={"row_ids": [row_id], "mode": "archive"},
    )
    assert first.status_code == 200
    assert first.json() == {"archived": 1, "deleted": 0}

    db_session.expire_all()
    first_timestamp = db_session.get(CsvRow, row_id).archived_at
    assert first_timestamp is not None

    second = auth_client.request(
        "DELETE",
        "/rows",
        json={"row_ids": [row_id], "mode": "archive"},
    )
    assert second.status_code == 200
    assert second.json() == {"archived": 0, "deleted": 0}

    db_session.expire_all()
    assert db_session.get(CsvRow, row_id).archived_at == first_timestamp


def test_existing_archived_unknown_date_is_not_purgeable(auth_client, db_session):
    rows = _reset_and_seed(auth_client)
    row_id = rows[0]["id"]

    row = db_session.get(CsvRow, row_id)
    row.archived = True
    row.archived_at = None
    db_session.commit()

    repeated = auth_client.request(
        "DELETE",
        "/rows",
        json={"row_ids": [row_id], "mode": "archive"},
    )
    assert repeated.status_code == 200
    assert repeated.json() == {"archived": 0, "deleted": 0}

    db_session.expire_all()
    legacy_row = db_session.get(CsvRow, row_id)
    assert legacy_row.archived is True
    assert legacy_row.archived_at is None
    assert settings.AUTO_PURGE_AFTER_DAYS == 0


def test_migration_does_not_hide_unvisited_rows(auth_client, db_session):
    rows = _reset_and_seed(auth_client)
    visible_ids = {row["id"] for row in rows}

    owner = db_session.query(User).filter_by(email="test@jobgrid.dev").one()
    unvisited = (
        db_session.query(CsvRow)
        .filter(
            CsvRow.user_id == owner.id,
            CsvRow.clicked.is_(False),
            CsvRow.archived.is_(False),
        )
        .first()
    )
    assert unvisited is not None
    assert unvisited.archived_at is None
    assert unvisited.id in visible_ids


def test_retention_defaults_are_disabled():
    assert settings.AUTO_ARCHIVE_AFTER_DAYS == 0
    assert settings.AUTO_PURGE_AFTER_DAYS == 0
    assert settings.RUN_MAINTENANCE_JOBS is False


def test_retired_legacy_cleanup_is_non_destructive(auth_client, db_session):
    rows = _reset_and_seed(auth_client)
    row_id = rows[0]["id"]
    before = db_session.get(CsvRow, row_id)
    assert before.archived is False
    assert before.archived_at is None

    owner = db_session.query(User).filter_by(email="test@jobgrid.dev").one()
    owner.retention_days = None
    db_session.commit()

    result = cleanup_clicked_rows()
    assert result["scanned"] == 0
    assert result["archived"] == 0
    assert result["skipped"] == 0
    assert result["failed"] == 0
    assert result["duration_ms"] >= 0

    db_session.expire_all()
    after = db_session.get(CsvRow, row_id)
    assert after.archived is False
    assert after.archived_at is None


def test_retention_preference_validation_and_account_isolation(auth_client):
    _reset_and_seed(auth_client)

    initial = auth_client.get("/preferences")
    assert initial.status_code == 200
    assert initial.json()["retention_days"] is None

    for value in (0, 7, 30, 3650):
        response = auth_client.put(
            "/preferences/retention",
            json={"retention_days": value},
        )
        assert response.status_code == 200
        assert response.json()["retention_days"] == value

    for value in (-1, 1, 6, 3651):
        response = auth_client.put(
            "/preferences/retention",
            json={"retention_days": value},
        )
        assert response.status_code == 422

    wrong_type = auth_client.put(
        "/preferences/retention",
        json={"retention_days": "30"},
    )
    assert wrong_type.status_code == 422

    primary = auth_client.put(
        "/preferences/retention",
        json={"retention_days": 30},
    )
    assert primary.status_code == 200

    other_login = auth_client.post(
        "/auth/dev-login",
        json={"email": "other-retention@jobgrid.dev"},
    )
    assert other_login.status_code == 200
    other_initial = auth_client.get("/preferences")
    assert other_initial.status_code == 200
    assert other_initial.json()["retention_days"] is None

    other_update = auth_client.put(
        "/preferences/retention",
        json={"retention_days": 60},
    )
    assert other_update.status_code == 200

    primary_login = auth_client.post(
        "/auth/dev-login",
        json={"email": "test@jobgrid.dev"},
    )
    assert primary_login.status_code == 200
    assert auth_client.get("/preferences").json()["retention_days"] == 30


def test_archive_preserves_application_snapshot_and_duplicate_link(
    auth_client, db_session
):
    rows = _reset_and_seed(auth_client)
    row_id = rows[0]["id"]
    duplicate_id = rows[1]["id"]

    owner = db_session.query(User).filter_by(email="test@jobgrid.dev").one()
    source = db_session.get(CsvRow, row_id)
    duplicate = db_session.get(CsvRow, duplicate_id)
    duplicate.duplicate_of_id = source.id
    track = JobTrack(
        user_id=owner.id,
        csv_row_id=source.id,
        url=source.url,
        company=source.company_guess,
        title=source.title,
        status="opened",
    )
    db_session.add(track)
    db_session.commit()
    track_id = track.id

    response = auth_client.request(
        "DELETE",
        "/rows",
        json={"row_ids": [source.id], "mode": "archive"},
    )
    assert response.status_code == 200
    assert response.json()["archived"] == 1

    db_session.expire_all()
    assert db_session.get(JobTrack, track_id).csv_row_id == source.id
    assert db_session.get(CsvRow, duplicate_id).duplicate_of_id == source.id
