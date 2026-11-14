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


def test_ever_applied_excludes_opened_and_legacy_unproven_status(ledger_owner):
    client, db, owner = ledger_owner
    saved = _track(db, owner, status="opened")
    unproven = _track(db, owner, status="applied")
    confirmed = _track(
        db, owner, status="rejected", applied_at=datetime(2026, 9, 15, 9),
    )
    outsider = User(email=f"al-outsider-{uuid.uuid4().hex}@example.test")
    db.add(outsider)
    db.flush()
    foreign = _track(
        db, outsider, status="offer", applied_at=datetime(2026, 9, 16, 9),
    )
    db.commit()

    listing = client.get("/crm/applications", params={"applied_only": True})
    assert listing.status_code == 200
    assert listing.json()["total_count"] == 1
    assert [item["id"] for item in listing.json()["rows"]] == [confirmed.id]

    filtered = client.get("/crm/applications", params={
        "applied_only": True, "status": "rejected",
    })
    assert [item["id"] for item in filtered.json()["rows"]] == [confirmed.id]
    assert client.get("/crm/applications", params={
        "applied_only": True, "status": "applied",
    }).json()["total_count"] == 0

    exported = client.get("/crm/export/applications", params={
        "scope": "filtered", "format": "json", "applied_only": True,
    })
    assert exported.status_code == 200
    assert [item["url"] for item in exported.json()] == [confirmed.url]
    assert saved.url not in exported.text
    assert unproven.url not in exported.text
    assert foreign.url not in exported.text

    validation = client.get("/crm/applications/validation-report")
    assert validation.status_code == 200
    assert validation.json()["repair_mode"] == "manual_only"

    assert client.post("/auth/dev-login", json={"email": outsider.email}).status_code == 200
    other_listing = client.get("/crm/applications", params={"applied_only": True})
    assert [item["id"] for item in other_listing.json()["rows"]] == [foreign.id]
    other_export = client.get("/crm/export/applications", params={
        "scope": "filtered", "format": "json", "applied_only": True,
    })
    assert [item["url"] for item in other_export.json()] == [foreign.url]


def test_applied_date_bounds_sort_pages_and_export_stay_in_sync(ledger_owner):
    client, db, owner = ledger_owner
    early = _track(
        db, owner, status="applied", applied_at=datetime(2026, 9, 1, 9),
    )
    middle = _track(
        db, owner, status="interview", applied_at=datetime(2026, 9, 15, 9),
    )
    late = _track(
        db, owner, status="offer", applied_at=datetime(2026, 10, 1, 12),
    )
    _track(db, owner, status="opened")
    db.commit()
    ordered_urls = [early.url, middle.url, late.url]

    base = {"applied_only": True, "sort_by": "applied_at", "sort_dir": "asc"}
    paged_urls = []
    for page in (1, 2, 3):
        response = client.get("/crm/applications", params={
            **base, "page_size": 1, "page": page,
        })
        assert response.status_code == 200
        assert response.json()["total_count"] == 3
        paged_urls.extend(item["url"] for item in response.json()["rows"])
    assert paged_urls == ordered_urls

    bounds = {
        **base,
        "date_applied_from": "2026-09-15T09:00:00+00:00",
        "date_applied_to": "2026-10-01T12:00:00Z",
    }
    listing = client.get("/crm/applications", params=bounds)
    assert listing.status_code == 200
    assert listing.json()["total_count"] == 1
    assert [item["url"] for item in listing.json()["rows"]] == [middle.url]

    for format in ("csv", "json"):
        export = client.get("/crm/export/applications", params={
            **bounds, "scope": "filtered", "format": format,
        })
        assert export.status_code == 200
        exported = (
            list(csv.DictReader(io.StringIO(export.text)))
            if format == "csv"
            else export.json()
        )
        assert [(item["url"], item["app_status"]) for item in exported] == [
            (middle.url, "interview"),
        ]

    whole_export = client.get("/crm/export/applications", params={
        **base, "scope": "filtered", "format": "json",
    })
    assert [item["url"] for item in whole_export.json()] == paged_urls
