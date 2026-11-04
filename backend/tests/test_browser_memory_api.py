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
