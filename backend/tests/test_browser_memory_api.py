"""EXT-04: session identity comes from the existing signed-in cookie."""
from uuid import uuid4


def _login(client, label):
    response = client.post(
        "/auth/dev-login",
        json={"email": f"ext04-{label}-{uuid4().hex}@example.test"},
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def test_browser_session_returns_only_server_account_identity(client):
    account_id = _login(client, "first")
    response = client.get("/crm/browser-memory/session")
    assert response.status_code == 200, response.text
    assert response.json() == {
        "protocol_version": 1,
        "account_id": account_id,
        "account_label": f"JobGrid account {account_id}",
    }
    assert response.headers["cache-control"] == "no-store"
    body = response.text.lower()
    assert "email" not in body
    assert "token" not in body
    assert "cookie" not in body


def test_browser_session_rejects_missing_and_invalid_cookie(client):
    no_cookie = client.get("/crm/browser-memory/session")
    assert no_cookie.status_code == 401
    assert no_cookie.json() == {"detail": "Not authenticated"}
    assert "account_id" not in no_cookie.text

    client.cookies.set("session_token", "invalid")
    invalid = client.get("/crm/browser-memory/session")
    assert invalid.status_code == 401
    assert invalid.json() == {"detail": "Invalid token"}
    assert "account_id" not in invalid.text

    # Expired signed cookies must use the same existing auth failure contract.
    from datetime import datetime, timedelta, timezone
    import jwt
    from app.config import settings

    expired_token = jwt.encode(
        {
            "sub": "1",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=2),
        },
        settings.SECRET_KEY,
        algorithm="HS256",
    )
    client.cookies.set("session_token", expired_token)
    expired = client.get("/crm/browser-memory/session")
    assert expired.status_code == 401
    assert expired.json() == {"detail": "Invalid token"}
    assert "account_id" not in expired.text


def test_browser_session_account_switch_is_not_cached(client):
    first = _login(client, "a")
    first_response = client.get("/crm/browser-memory/session")
    assert first_response.status_code == 200
    assert first_response.json()["account_id"] == first

    second = _login(client, "b")
    assert second != first
    second_response = client.get("/crm/browser-memory/session")
    assert second_response.status_code == 200
    assert second_response.json()["account_id"] == second
    assert second_response.json()["account_label"] == f"JobGrid account {second}"
    assert second_response.headers["cache-control"] == "no-store"


# EXT-14: frozen authenticated check API contract, errors and read-only behavior.
from datetime import datetime
from app.models import BrowserApplyReceipt, JobLifecycleEvent, JobTrack, JobVisit, User
from app.services.job_identity import apply_persisted_job_identity


def _memory_counts(db_session, user_id):
    return tuple(
        db_session.query(model).filter(model.user_id == user_id).count()
        for model in (JobVisit, JobTrack, JobLifecycleEvent, BrowserApplyReceipt)
    )


def test_ext_14_protocol_response_uses_cookie_owner_utc_z_and_exact_types(client, db_session):
    user_id = _login(client, "valid")
    url = "https://boards.example.test/14/role?req=3"
    owner_track = JobTrack(
        user_id=user_id, url=url, company="Acme", title="Developer",
        status="withdrawn", applied_at=datetime(2026, 7, 3, 10, 12, 0),
    )
    apply_persisted_job_identity(owner_track)
    db_session.add(owner_track)
    db_session.commit()
    checked = client.post("/crm/browser-memory/check", json={
        "url": url, "company": "Acme", "title": "Developer",
    })
    assert checked.status_code == 200, checked.text
    assert checked.headers["cache-control"] == "no-store"
    data = checked.json()
    assert set(data) == {
        "protocol_version", "checked_at", "account_id", "visit", "matches",
        "company_history_count", "company_known", "lookup_complete",
    }
    assert data["protocol_version"] == 1
    assert data["account_id"] == user_id
    assert datetime.fromisoformat(data["checked_at"].replace("Z", "+00:00"))
    assert data["checked_at"].endswith("Z")
    assert data["visit"] == {"visited": False, "first_visited_at": None}
    assert data["company_history_count"] == 1
    assert type(data["company_history_count"]) is int
    assert data["company_known"] is True
    assert data["lookup_complete"] is True
    assert len(data["matches"]) == 1
    assert data["matches"][0] == {
        "track_id": owner_track.id, "confidence": "exact",
        "reason": "same_original_url", "company": "Acme", "title": "Developer",
        "status": "withdrawn", "applied_at": "2026-07-03T10:12:00Z",
    }


def test_ext_14_missing_auth_and_invalid_payload_are_safe(client, db_session):
    url = "https://boards.example.test/14/check?req=9"
    missing_auth = client.post("/crm/browser-memory/check", json={"url": url})
    assert missing_auth.status_code == 401
    assert missing_auth.json() == {"detail": "Not authenticated"}
    user_id = _login(client, "errors")
    before = _memory_counts(db_session, user_id)
    for payload in (
        {"url": url, "user_id": 99},
        {"url": "http://127.0.0.1/private"},
        {"url": url, "company": 9},
        {"url": url, "title": "X" * 501},
        {"url": url, "not_allowed": "yes"},
        [],
    ):
        response = client.post("/crm/browser-memory/check", json=payload)
        assert response.status_code == 422, (payload, response.text)
        assert response.json()["detail"]["code"] == "invalid_browser_memory_payload"
        assert "99" not in response.text
    malformed = client.post(
        "/crm/browser-memory/check",
        content=b"{",
        headers={"Content-Type": "application/json"},
    )
    assert malformed.status_code == 422
    assert malformed.json()["detail"]["code"] == "invalid_browser_memory_payload"
    assert _memory_counts(db_session, user_id) == before


def test_ext_14_check_is_repeatable_and_never_writes_or_exposes_other_owner(client, db_session):
    first = _login(client, "first-check")
    url = "https://boards.example.test/14/private?req=77"
    private = JobTrack(
        user_id=first, url=url, company="Acme", title="Developer",
        status="applied", applied_at=datetime(2026, 2, 1, 8, 0, 0),
    )
    apply_persisted_job_identity(private)
    db_session.add(private)
    db_session.commit()
    second = _login(client, "second-check")
    snapshot = _memory_counts(db_session, first), _memory_counts(db_session, second)
    for _ in range(3):
        checked = client.post("/crm/browser-memory/check", json={"url": url})
        assert checked.status_code == 200, checked.text
        assert checked.json()["account_id"] == second
        assert checked.json()["visit"] == {"visited": False, "first_visited_at": None}
        assert checked.json()["matches"] == []
        assert checked.json()["company_history_count"] == 0
    assert (_memory_counts(db_session, first), _memory_counts(db_session, second)) == snapshot


# EXT-19: guarded write routes and durable attempt limits.
from app.config import settings
from app.services import browser_memory


def _browser_headers(user_id, **overrides):
    headers = {
        "Origin": settings.FRONTEND_URL.rstrip("/"),
        "X-JobGrid-Browser": "1",
        "X-JobGrid-Account-ID": str(user_id),
        "Idempotency-Key": str(uuid4()),
    }
    headers.update(overrides)
    return headers


def test_ext_19_visit_replay_and_forget_are_account_scoped(client, db_session):
    first = _login(client, "visit")
    url = "https://jobs.example.test/ext-19/visit?req=1"
    headers = _browser_headers(first)
    initial = client.post(
        "/crm/browser-memory/visit", json={"url": url}, headers=headers,
    )
    assert initial.status_code == 200, initial.text
    assert initial.headers["cache-control"] == "no-store"
    data = initial.json()
    assert set(data) == {
        "protocol_version", "account_id", "created", "first_visited_at",
    }
    assert data["protocol_version"] == 1 and data["account_id"] == first
    assert data["created"] is True and data["first_visited_at"].endswith("Z")
    repeated = client.post(
        "/crm/browser-memory/visit", json={"url": url}, headers=headers,
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json() == {**data, "created": False}
    second = _login(client, "visit-second")
    deletion = client.request(
        "DELETE", "/crm/browser-memory/visits",
        headers=_browser_headers(second),
    )
    assert deletion.status_code == 200 and deletion.json()["deleted"] == 0
    assert db_session.query(JobVisit).filter_by(user_id=first).count() == 1
    _login(client, "visit")  # new account; original owner is not selected
    assert db_session.query(JobVisit).filter_by(user_id=first).count() == 1


def test_ext_19_apply_replay_and_forget_counts_are_truthful(client, db_session):
    owner = _login(client, "apply")
    headers = _browser_headers(owner)
    body = {
        "url": "https://jobs.example.test/ext-19/role?req=2",
        "company": "Acme", "title": "Engineer", "confirmed": True,
    }
    first = client.post("/crm/browser-memory/apply", json=body, headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["created"] is True
    assert first.json()["already_applied"] is False
    replay = client.post("/crm/browser-memory/apply", json=body, headers=headers)
    assert replay.status_code == 200 and replay.json() == first.json()
    conflict = client.post(
        "/crm/browser-memory/apply",
        json={**body, "title": "Other title"}, headers=headers,
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "idempotency_conflict"
    visit = client.post(
        "/crm/browser-memory/visit", json={"url": body["url"]}, headers=headers,
    )
    assert visit.status_code == 200
    forget = client.request("DELETE", "/crm/browser-memory/visits", headers=headers)
    assert forget.status_code == 200
    assert forget.json() == {"protocol_version": 1, "account_id": owner, "deleted": 1}
    repeat = client.request("DELETE", "/crm/browser-memory/visits", headers=headers)
    assert repeat.status_code == 200 and repeat.json()["deleted"] == 0
    assert db_session.query(JobTrack).filter_by(user_id=owner).count() == 1
    assert db_session.query(BrowserApplyReceipt).filter_by(user_id=owner).count() == 1
    assert db_session.query(JobVisit).filter_by(user_id=owner).count() == 0


def test_ext_19_origin_expected_account_and_input_fail_before_mutation(client, db_session):
    no_auth = client.post(
        "/crm/browser-memory/apply",
        json={"url": "https://jobs.example.test/19/a"},
    )
    assert no_auth.status_code == 401
    owner = _login(client, "guards")
    headers = _browser_headers(owner)
    body = {
        "url": "https://jobs.example.test/19/a", "company": "Acme",
        "title": "Engineer", "confirmed": True,
    }
    cases = [
        (_browser_headers(owner, Origin="https://evil.example.test"), 403, "origin_not_allowed"),
        (_browser_headers(owner, **{"X-JobGrid-Browser": "0"}), 403, "origin_not_allowed"),
        (_browser_headers(owner, **{"X-JobGrid-Account-ID": "999999"}), 409, "account_changed"),
        (_browser_headers(owner, **{"X-JobGrid-Account-ID": "oops"}), 422, "invalid_browser_memory_payload"),
        (_browser_headers(owner, **{"Idempotency-Key": ""}), 422, "invalid_browser_memory_payload"),
    ]
    for h, status, code in cases:
        result = client.post("/crm/browser-memory/apply", json=body, headers=h)
        assert result.status_code == status, result.text
        assert result.json()["detail"]["code"] == code
    no_confirm = client.post(
        "/crm/browser-memory/apply", json={**body, "confirmed": 1},
        headers=headers,
    )
    assert no_confirm.status_code == 422
    malformed = client.post(
        "/crm/browser-memory/visit", content="{", headers=headers,
    )
    assert malformed.status_code == 422
    invalid_delete = client.request(
        "DELETE", "/crm/browser-memory/visits",
        json={"confirmed": True}, headers=headers,
    )
    assert invalid_delete.status_code == 422
    assert _memory_counts(db_session, owner) == (0, 0, 0, 0)


def test_ext_19_persisted_attempt_limit_counts_invalid_authenticated_attempts(
    client, monkeypatch,
):
    owner = _login(client, "rate")
    headers = _browser_headers(owner)
    monkeypatch.setitem(browser_memory._BROWSER_WINDOW_RULES, "apply", (2, 60))
    bad = {
        "url": "https://jobs.example.test/19/rate",
        "company": "Acme", "title": "Engineer", "confirmed": False,
    }
    for _ in range(2):
        response = client.post(
            "/crm/browser-memory/apply", json=bad, headers=headers,
        )
        assert response.status_code == 422, response.text
    third = client.post("/crm/browser-memory/apply", json=bad, headers=headers)
    assert third.status_code == 429
    assert third.json()["detail"]["code"] == "browser_memory_rate_limited"
    assert int(third.headers["Retry-After"]) >= 1
