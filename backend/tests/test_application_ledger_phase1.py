"""AL-01 through AL-06: existing dated application truth and export contracts.

No destructive repairs or new backend API behavior. Tests use isolated test users.
"""
import csv
import io
import uuid
from datetime import datetime

import pytest

from app.models import CsvRow, JobLifecycleEvent, JobTrack, User


@pytest.fixture
def ledger_owner(client, db_session):
    email = f"al-phase1-{uuid.uuid4().hex}@example.test"
    assert client.post("/auth/dev-login", json={"email": email}).status_code == 200
    return client, db_session, db_session.query(User).filter_by(email=email).one()


def _track(db, owner, *, status, applied_at=None, opened_at=None, company="Acme"):
    suffix = uuid.uuid4().hex
    track = JobTrack(
        user_id=owner.id,
        url=f"https://jobs.example.test/ledger-{suffix}",
        company=company,
        title=f"Engineer {suffix[:8]}",
        status=status,
        applied_at=applied_at,
        opened_at=opened_at or datetime(2026, 8, 1, 9),
    )
    db.add(track)
    db.flush()
    return track


def test_ever_applied_survives_stage_changes_and_source_csv_deletion(ledger_owner):
    client, db, owner = ledger_owner
    row = CsvRow(
        user_id=owner.id, upload_batch_id="al-phase1",
        url=f"https://jobs.example.test/from-csv/{uuid.uuid4().hex}",
        title="API Engineer", company_guess="Acme",
    )
    db.add(row)
    db.commit()
    row_id = row.id

    submitted = client.post("/crm/from-rows/bulk", json={"row_ids": [row_id], "status": "applied"})
    assert submitted.status_code == 200
    track_id = submitted.json()["application_ids"][0]
    first_date = client.get("/crm/applications", params={"applied_only": True}).json()["rows"][0]["applied_at"]
    assert first_date

    for stage in ("interview", "rejected", "offer", "not_applying"):
        changed = client.patch(f"/crm/applications/{track_id}", json={"status": stage})
        assert changed.status_code == 200

        listing = client.get("/crm/applications", params={"applied_only": True, "status": stage})
        assert listing.status_code == 200
        assert listing.json()["total_count"] == 1
        assert listing.json()["rows"][0]["applied_at"] == first_date

        exported = client.get("/crm/export/applications", params={
            "scope": "filtered", "applied_only": True, "format": "json", "status": stage,
        })
        assert exported.status_code == 200
        assert [(item["url"], item["app_status"]) for item in exported.json()] == [
            (row.url, stage),
        ]

    deleted = client.request("DELETE", "/rows", json={"row_ids": [row_id]})
    assert deleted.status_code == 200
    listing = client.get("/crm/applications", params={"applied_only": True})
    assert listing.status_code == 200
    assert listing.json()["total_count"] == 1
    assert listing.json()["rows"][0]["csv_row_id"] is None

    csv_export = client.get("/crm/export/applications", params={
        "scope": "filtered", "applied_only": True, "format": "csv",
    })
    assert csv_export.status_code == 200
    rows = list(csv.DictReader(io.StringIO(csv_export.text)))
    assert len(rows) == 1
    assert rows[0]["url"] == row.url
    assert rows[0]["app_status"] == "not_applying"
    assert rows[0]["applied_at"]

    db.expire_all()
    assert db.query(JobLifecycleEvent).filter_by(
        user_id=owner.id, job_track_id=track_id, kind="first_applied",
    ).count() == 1
    assert db.get(JobTrack, track_id).applied_at is not None
