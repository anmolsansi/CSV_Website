from datetime import datetime
from uuid import uuid4

from app.models import CsvRow, JobTrack, User
from app.services import capture as capture_service


def _capture(client, *, url, key=None, title="Engineer", company="Example", notes=None):
    payload = {
        "job_url": url,
        "title": title,
        "company": company,
        "source": "manual",
    }
    if notes is not None:
        payload["notes"] = notes
    return client.post(
        "/crm/jobs/capture",
        json=payload,
        headers={"Idempotency-Key": str(key or uuid4())},
    )


def test_capture_not_visited_or_applied(auth_client, db_session):
    url = f"https://capture.example/jobs/{uuid4()}"
    response = _capture(auth_client, url=url)
    assert response.status_code == 201, response.text
    row = db_session.get(CsvRow, response.json()["row_id"])
    assert row.clicked is False
    assert row.clicked_at is None
    assert db_session.query(JobTrack).filter_by(
        user_id=row.user_id,
        url=url,
    ).count() == 0


def test_concurrent_repeat_creates_one_row(auth_client, db_session):
    # Independent idempotency keys model two requests that race on the exact URL.
    # The owner/url unique contract is the final concurrency guard.
    url = f"https://capture.example/jobs/{uuid4()}"
    first = _capture(auth_client, url=url)
    second = _capture(auth_client, url=url)
    assert first.status_code == 201, first.text
    assert second.status_code == 200, second.text
    assert first.json()["row_id"] == second.json()["row_id"]

    user = db_session.query(User).filter_by(email="test@jobgrid.dev").one()
    assert db_session.query(CsvRow).filter_by(user_id=user.id, url=url).count() == 1


def test_same_key_different_payload409(auth_client):
    key = uuid4()
    url = f"https://capture.example/jobs/{uuid4()}"
    assert _capture(auth_client, url=url, key=key, title="Engineer").status_code == 201
    conflict = _capture(auth_client, url=url, key=key, title="Senior Engineer")
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "idempotency_conflict"


def test_foreign_existing_url_not_disclosed(auth_client, db_session):
    url = f"https://capture.example/jobs/{uuid4()}"
    auth_client.post("/auth/logout")
    foreign_email = f"foreign-{uuid4()}@example.test"
    assert auth_client.post("/auth/dev-login", json={"email": foreign_email}).status_code == 200
    foreign = _capture(auth_client, url=url)
    assert foreign.status_code == 201

    auth_client.post("/auth/logout")
    assert auth_client.post(
        "/auth/dev-login", json={"email": "test@jobgrid.dev"}
    ).status_code == 200
    own = _capture(auth_client, url=url)
    assert own.status_code == 201, own.text
    assert own.json()["row_id"] != foreign.json()["row_id"]
    assert not any(
        match.get("row_id") == foreign.json()["row_id"]
        for match in own.json()["matches"]
    )


def test_existing_notes_not_overwritten(auth_client, db_session):
    url = f"https://capture.example/jobs/{uuid4()}"
    captured = _capture(
        auth_client,
        url=url,
        notes="Draft note from capture",
    )
    assert captured.status_code == 201
    row_id = captured.json()["row_id"]

    user = db_session.query(User).filter_by(email="test@jobgrid.dev").one()
    track = JobTrack(
        user_id=user.id,
        csv_row_id=None,
        url=url,
        company="Example",
        title="Engineer",
        status="opened",
        notes="Existing application note",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(track)
    db_session.commit()

    response = auth_client.post(
        "/crm/from-rows/bulk",
        json={"row_ids": [row_id]},
    )
    assert response.status_code == 200, response.text
    db_session.refresh(track)
    assert track.notes == "Existing application note"

    appended = auth_client.post(
        "/crm/from-rows/bulk",
        json={"row_ids": [row_id], "capture_notes_mode": "append"},
    )
    assert appended.status_code == 200, appended.text
    db_session.refresh(track)
    assert track.notes == "Existing application note\n\nDraft note from capture"



def test_invalid_attempt_counts_toward_rate_limit(
    auth_client, monkeypatch
):
    auth_client.post("/auth/logout")
    email = f"capture-rate-{uuid4()}@example.test"
    assert auth_client.post(
        "/auth/dev-login", json={"email": email}
    ).status_code == 200
    monkeypatch.setattr(capture_service, "CAPTURE_RATE_LIMIT", 1)

    invalid = auth_client.post(
        "/crm/jobs/capture",
        json={
            "job_url": f"https://capture.example/jobs/{uuid4()}",
            "company": "Example",
            "source": "manual",
        },
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert invalid.status_code == 422

    limited = _capture(
        auth_client,
        url=f"https://capture.example/jobs/{uuid4()}",
    )
    assert limited.status_code == 429
    assert limited.json()["detail"]["code"] == "capture_rate_limited"
    assert int(limited.headers["Retry-After"]) > 0



def test_capture_returns_owned_application_identity_warning(
    auth_client, db_session
):
    user = db_session.query(User).filter_by(email="test@jobgrid.dev").one()
    url = f"https://capture.example/jobs/{uuid4()}"
    track = JobTrack(
        user_id=user.id,
        url=url,
        company="Example",
        title="Engineer",
        status="opened",
        notes=None,
    )
    db_session.add(track)
    db_session.commit()

    response = _capture(
        auth_client,
        url=url,
        title="Engineer",
        company="Example",
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["created"] is True
    assert body["matches"][0]["track_id"] == track.id
    assert body["matches"][0]["confidence"] == "exact"
    assert body["company_history_count"] >= 1
