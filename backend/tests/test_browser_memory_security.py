"""EXT-21: account-scoped shared request windows and exact write trust boundary."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.config import settings
from app.models import BrowserApplyReceipt, JobVisit, JobTrack
from app.services import browser_memory


def _login(client, label):
    response = client.post(
        "/auth/dev-login",
        json={"email": f"ext21-{label}-{uuid4().hex}@example.test"},
    )
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _headers(account, **changes):
    headers = {
        "Origin": settings.FRONTEND_URL.rstrip("/"),
        "X-JobGrid-Browser": "1",
        "X-JobGrid-Account-ID": str(account),
        "Idempotency-Key": str(uuid4()),
    }
    headers.update(changes)
    return headers


def test_ext_21_default_windows_are_owner_and_action_specific():
    assert browser_memory._BROWSER_WINDOW_RULES == {
        "check": (120, 60),
        "visit": (60, 60),
        "apply": (20, 60),
        "forget": (5, 3600),
    }


def test_ext_21_shared_window_spans_independent_database_sessions(client, engine, monkeypatch):
    a = _login(client, "shared-a")
    fixed = datetime(2026, 11, 4, 10, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setitem(browser_memory._BROWSER_WINDOW_RULES, "check", (2, 60))
    with Session(bind=engine) as first, Session(bind=engine) as second:
        assert browser_memory.count_browser_memory_attempt(first, user_id=a, action="check", now=fixed) == 0
        assert browser_memory.count_browser_memory_attempt(second, user_id=a, action="check", now=fixed) == 0
        assert browser_memory.count_browser_memory_attempt(first, user_id=a, action="check", now=fixed) == 60
        # Window clears across process-independent sessions, not a Python dict.
        assert browser_memory.count_browser_memory_attempt(second, user_id=a, action="check", now=fixed.replace(minute=1)) == 0
    b = _login(client, "shared-b")
    with Session(bind=engine) as other:
        assert browser_memory.count_browser_memory_attempt(other, user_id=b, action="check", now=fixed) == 0


@pytest.mark.parametrize("action,path,method,payload", [
    ("check", "/crm/browser-memory/check", "post", {"url": "not a url"}),
    ("visit", "/crm/browser-memory/visit", "post", {"url": "not a url"}),
    ("apply", "/crm/browser-memory/apply", "post", {"url": "not a url"}),
    ("forget", "/crm/browser-memory/visits", "delete", None),
])
def test_ext_21_rejected_authenticated_attempts_count(client, monkeypatch, action, path, method, payload):
    account = _login(client, action)
    monkeypatch.setitem(browser_memory._BROWSER_WINDOW_RULES, action, (2, 60))
    for _ in range(2):
        if method == "post":
            response = client.post(path, json=payload, headers=_headers(account))
        else:
            response = client.request("DELETE", path, json={"unexpected": True}, headers=_headers(account))
        assert response.status_code == 422, response.text
    if method == "post":
        denied = client.post(path, json=payload, headers=_headers(account))
    else:
        denied = client.request("DELETE", path, headers=_headers(account))
    assert denied.status_code == 429, denied.text
    assert denied.json()["detail"]["code"] == "browser_memory_rate_limited"
    assert 1 <= int(denied.headers["retry-after"]) <= 3600
    assert denied.headers["cache-control"] == "no-store"


def test_ext_21_account_switch_and_spoofed_origin_cannot_write(client, db_session):
    source = _login(client, "selected")
    session = client.get("/crm/browser-memory/session").json()
    assert session["account_id"] == source
    target = _login(client, "switched")
    body = {"url": "https://jobs.example.test/21/a", "company": "Acme",
            "title": "Engineer", "confirmed": True}
    cases = [
        (_headers(source), 409, "account_changed"),
        (_headers(target, Origin="https://evil.example.test"), 403, "origin_not_allowed"),
        (_headers(target, Origin=settings.FRONTEND_URL.rstrip("/") + ".evil.example"), 403, "origin_not_allowed"),
        (_headers(target, **{"X-JobGrid-Browser": "true"}), 403, "origin_not_allowed"),
        (_headers(target, **{"X-JobGrid-Account-ID": ""}), 422, "invalid_browser_memory_payload"),
    ]
    for headers, status, code in cases:
        response = client.post("/crm/browser-memory/apply", json=body, headers=headers)
        assert response.status_code == status, response.text
        assert response.json()["detail"]["code"] == code
    for account in (source, target):
        assert db_session.query(JobVisit).filter_by(user_id=account).count() == 0
        assert db_session.query(BrowserApplyReceipt).filter_by(user_id=account).count() == 0
        assert db_session.query(JobTrack).filter_by(user_id=account).count() == 0


@pytest.mark.parametrize("path,body", [
    ("/crm/browser-memory/check", {"url": "https://jobs.example.test/21/check"}),
    ("/crm/browser-memory/visit", {"url": "https://jobs.example.test/21/visit"}),
])
def test_ext_21_limiter_storage_failure_fails_closed(client, monkeypatch, path, body):
    account = _login(client, "unavailable")
    def cannot_open_limiter(*args, **kwargs):
        raise RuntimeError("test limiter storage failure")
    monkeypatch.setattr(browser_memory, "Session", cannot_open_limiter)
    response = client.post(path, json=body, headers=_headers(account))
    assert response.status_code == 503, response.text
    assert response.json()["detail"]["code"] == "browser_memory_unavailable"
    assert response.headers["cache-control"] == "no-store"
    assert "test limiter" not in response.text
