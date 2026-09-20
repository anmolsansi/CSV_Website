from datetime import datetime, timedelta

import app.routers.crm as crm_module
from app.models import CsvRow, MaintenanceStatus, User
from app.services.retention import ARCHIVE_MAINTENANCE_JOB_NAME


def _reset_and_seed(auth_client):
    assert auth_client.post("/test/reset").status_code == 200
    assert auth_client.post("/test/seed").status_code == 200


def _owner(db_session, email="test@jobgrid.dev"):
    db_session.expire_all()
    return db_session.query(User).filter_by(email=email).one()


def test_retention_profile_defaults_off_and_values_validated(auth_client, db_session):
    _reset_and_seed(auth_client)

    initial = auth_client.get("/crm/profile/retention")
    assert initial.status_code == 200
    assert initial.json() == {
        "archive_after_days": 0,
        "eligible_row_count": 0,
        "maintenance": {
            "status": "disabled",
            "last_successful_cleanup_at": None,
            "last_attempted_cleanup_at": None,
            "last_outcome": "disabled",
        },
        "purge_available": False,
        "archived_rows_ui_available": False,
        "recovery_message": (
            "Archived rows are preserved. Until JG-062 ships recovery requires "
            "the existing API/operator workflow."
        ),
    }

    for value in (0, 7, 30, 3650):
        response = auth_client.patch(
            "/crm/profile/retention",
            json={"archive_after_days": value},
        )
        assert response.status_code == 200
        assert response.json()["archive_after_days"] == value

    for value in (-1, 1, 6, 3651, "30", True, None):
        response = auth_client.patch(
            "/crm/profile/retention",
            json={"archive_after_days": value},
        )
        assert response.status_code == 422

    extra = auth_client.patch(
        "/crm/profile/retention",
        json={"archive_after_days": 30, "user_id": 999999},
    )
    assert extra.status_code == 422


def test_preview_has_no_side_effect(auth_client, db_session):
    _reset_and_seed(auth_client)
    owner = _owner(db_session)
    now = datetime.utcnow()

    rows = (
        db_session.query(CsvRow)
        .filter(CsvRow.user_id == owner.id)
        .order_by(CsvRow.id.asc())
        .all()
    )
    assert len(rows) >= 3
    for row in rows:
        row.clicked = False
        row.clicked_at = None
        row.archived = False
        row.archived_at = None

    rows[0].clicked = True
    rows[0].clicked_at = now - timedelta(days=31)
    rows[1].clicked = True
    rows[1].clicked_at = now - timedelta(days=1)
    owner.retention_days = 30
    db_session.commit()

    response = auth_client.get("/crm/profile/retention")
    assert response.status_code == 200
    assert response.json()["archive_after_days"] == 30
    assert response.json()["eligible_row_count"] == 1

    db_session.expire_all()
    persisted = (
        db_session.query(CsvRow)
        .filter(CsvRow.user_id == owner.id)
        .order_by(CsvRow.id.asc())
        .all()
    )
    assert all(row.archived is False for row in persisted)
    assert all(row.archived_at is None for row in persisted)


def test_policy_save_does_not_run_cleanup(auth_client, db_session):
    _reset_and_seed(auth_client)
    owner = _owner(db_session)
    row = (
        db_session.query(CsvRow)
        .filter(CsvRow.user_id == owner.id)
        .order_by(CsvRow.id.asc())
        .first()
    )
    assert row is not None
    row.clicked = True
    row.clicked_at = datetime.utcnow() - timedelta(days=90)
    row.archived = False
    row.archived_at = None
    db_session.commit()

    response = auth_client.patch(
        "/crm/profile/retention",
        json={"archive_after_days": 30},
    )
    assert response.status_code == 200
    assert response.json()["eligible_row_count"] >= 1

    db_session.expire_all()
    persisted = db_session.get(CsvRow, row.id)
    assert persisted.archived is False
    assert persisted.archived_at is None


def test_cross_account_policy_write_is_denied(auth_client, db_session):
    _reset_and_seed(auth_client)
    assert auth_client.patch(
        "/crm/profile/retention",
        json={"archive_after_days": 30},
    ).status_code == 200

    assert auth_client.post(
        "/auth/dev-login",
        json={"email": "other-retention-profile@jobgrid.dev"},
    ).status_code == 200
    assert auth_client.patch(
        "/crm/profile/retention",
        json={"archive_after_days": 60},
    ).status_code == 200
    other = _owner(db_session, "other-retention-profile@jobgrid.dev")

    forbidden_shape = auth_client.patch(
        "/crm/profile/retention",
        json={"archive_after_days": 90, "user_id": other.id},
    )
    assert forbidden_shape.status_code == 422
    db_session.expire_all()
    assert db_session.get(User, other.id).retention_days == 60

    assert auth_client.post(
        "/auth/dev-login",
        json={"email": "test@jobgrid.dev"},
    ).status_code == 200
    primary = auth_client.get("/crm/profile/retention")
    assert primary.status_code == 200
    assert primary.json()["archive_after_days"] == 30


def test_failed_health_does_not_look_healthy(auth_client, db_session, monkeypatch):
    _reset_and_seed(auth_client)
    monkeypatch.setattr(crm_module.settings, "AUTO_ARCHIVE_AFTER_DAYS", 30)
    now = datetime.utcnow()

    db_session.query(MaintenanceStatus).delete()
    db_session.add(
        MaintenanceStatus(
            job_name=ARCHIVE_MAINTENANCE_JOB_NAME,
            outcome="failed",
            last_attempted_at=now,
            last_successful_at=now - timedelta(minutes=10),
            last_failed_at=now,
            result_json={
                "scanned": 1,
                "archived": 0,
                "skipped": 0,
                "failed": 1,
                "duration_ms": 5,
            },
            updated_at=now,
        )
    )
    db_session.commit()

    response = auth_client.get("/crm/profile/retention")
    assert response.status_code == 200
    health = response.json()["maintenance"]
    assert health["status"] == "unavailable"
    assert health["last_outcome"] == "failed"
    assert health["last_successful_cleanup_at"] is not None


def test_stale_health_is_unavailable(auth_client, db_session, monkeypatch):
    _reset_and_seed(auth_client)
    monkeypatch.setattr(crm_module.settings, "AUTO_ARCHIVE_AFTER_DAYS", 30)
    now = datetime.utcnow()
    stale_minutes = max(
        crm_module.settings.CLEANUP_INTERVAL_MINUTES * 2,
        crm_module.settings.CLEANUP_INTERVAL_MINUTES + 5,
    ) + 1
    stale_success = now - timedelta(minutes=stale_minutes)

    db_session.query(MaintenanceStatus).delete()
    db_session.add(
        MaintenanceStatus(
            job_name=ARCHIVE_MAINTENANCE_JOB_NAME,
            outcome="no_work",
            last_attempted_at=stale_success,
            last_successful_at=stale_success,
            last_failed_at=None,
            result_json={
                "scanned": 0,
                "archived": 0,
                "skipped": 0,
                "failed": 0,
                "duration_ms": 1,
            },
            updated_at=stale_success,
        )
    )
    db_session.commit()

    response = auth_client.get("/crm/profile/retention")
    assert response.status_code == 200
    assert response.json()["maintenance"]["status"] == "unavailable"
    assert response.json()["maintenance"]["last_outcome"] == "no_work"
