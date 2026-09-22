from uuid import uuid4

from app.models import CaptureRequest, CsvRow, RequestWindowCounter, User


def _login(client, email):
    response = client.post("/auth/dev-login", json={"email": email})
    assert response.status_code == 200
    return response.json()


def test_legacy_rows_unchanged_after_migration(db_session):
    user = User(email=f"legacy-capture-{uuid4()}@example.test")
    db_session.add(user)
    db_session.flush()
    row = CsvRow(
        user_id=user.id,
        upload_batch_id=str(uuid4()),
        url=f"https://example.test/jobs/{uuid4()}",
        title="Legacy role",
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)

    assert row.capture_source is None
    assert row.captured_at is None
    assert row.capture_notes is None


def test_capture_required_column_defaults_valid(auth_client, db_session):
    response = auth_client.post(
        "/crm/jobs/capture",
        json={
            "job_url": f"https://example.test/jobs/{uuid4()}",
            "title": "Backend Engineer",
            "company": "Example",
            "source": "manual",
        },
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 201, response.text
    row = db_session.get(CsvRow, response.json()["row_id"])
    assert row is not None
    assert row.upload_batch_id.startswith("capture-")
    assert row.url.startswith("https://")
    assert row.clicked is False
    assert row.archived is False
    assert row.is_duplicate is False
    assert row.capture_source == "manual"
    assert row.captured_at is not None


def test_request_key_conflicting_payload_rejected(auth_client):
    key = str(uuid4())
    url = f"https://example.test/jobs/{uuid4()}"
    first = auth_client.post(
        "/crm/jobs/capture",
        json={
            "job_url": url,
            "title": "Engineer",
            "company": "Example",
            "source": "manual",
        },
        headers={"Idempotency-Key": key},
    )
    assert first.status_code == 201, first.text

    second = auth_client.post(
        "/crm/jobs/capture",
        json={
            "job_url": url,
            "title": "Different Engineer",
            "company": "Example",
            "source": "manual",
        },
        headers={"Idempotency-Key": key},
    )
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "idempotency_conflict"


def test_capture_notes_round_trip(auth_client, db_session):
    source_url = f"https://example.test/jobs/{uuid4()}"
    captured = auth_client.post(
        "/crm/jobs/capture",
        json={
            "job_url": source_url,
            "title": "Engineer",
            "company": "Example",
            "source": "bookmarklet",
            "notes": "Recruiter said backend-heavy.",
        },
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert captured.status_code == 201

    exported = auth_client.get("/crm/backup/export?version=2")
    assert exported.status_code == 200
    payload = exported.json()
    record = next(
        item for item in payload["sections"]["csv_rows"]
        if item["url"] == source_url
    )
    assert record["capture_source"] == "bookmarklet"
    assert record["capture_notes"] == "Recruiter said backend-heavy."
    assert record["captured_at"]

    auth_client.post("/auth/logout")
    destination_email = f"restore-capture-{uuid4()}@example.test"
    _login(auth_client, destination_email)
    restored = auth_client.post(
        "/crm/backup/import?mode=merge_missing",
        files={"file": ("backup.json", exported.content, "application/json")},
    )
    assert restored.status_code == 200, restored.text

    destination = db_session.query(User).filter_by(email=destination_email).one()
    row = db_session.query(CsvRow).filter_by(
        user_id=destination.id,
        url=source_url,
    ).one()
    assert row.capture_source == "bookmarklet"
    assert row.capture_notes == "Recruiter said backend-heavy."
    assert row.captured_at is not None
