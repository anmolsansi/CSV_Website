"""Email/password auth: verified ownership, account safety, reset, rate limiting."""
import re
from datetime import datetime, timedelta

from app.config import settings
from app.models import EmailActionToken, PasswordCredential, User


def _enable(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_PASSWORD_AUTH_ENABLED", True)
    monkeypatch.setattr(settings, "EMAIL_AUTH_TRANSPORT", "smtp")
    monkeypatch.setattr(settings, "SMTP_HOST", "example.test")
    monkeypatch.setattr(settings, "EMAIL_FROM", "noreply@example.test")


def _capture(monkeypatch):
    from app.routers import email_auth
    messages = []
    monkeypatch.setattr(email_auth, "send_via_smtp", lambda msg: messages.append(msg))
    return messages


def _token(messages):
    html = messages[-1].get_payload()[0].get_payload(decode=True).decode()
    return re.search(r"token=([A-Za-z0-9_-]+)", html).group(1)


def test_auth_email_disabled_by_default(client, monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_PASSWORD_AUTH_ENABLED", False)
    assert client.post("/auth/email/login", json={
        "email": "disabled@example.test", "password": "strong password with spaces"
    }).status_code == 404


def test_verified_signup_and_password_login(client, db_session, monkeypatch):
    _enable(monkeypatch)
    messages = _capture(monkeypatch)
    email = "verified-email-user@example.test"
    password = "a long secure passphrase 123"
    registered = client.post("/auth/email/register", json={"email": email, "password": password})
    assert registered.status_code == 202, registered.text
    assert db_session.query(User).filter_by(email=email).first() is None
    assert len(messages) == 1
    token = _token(messages)
    # A token cannot be used twice.
    verified = client.post("/auth/email/verify", json={"token": token})
    assert verified.status_code == 200, verified.text
    assert "HttpOnly" in verified.headers["set-cookie"]
    assert "session_token=" in verified.headers["set-cookie"]
    user = db_session.query(User).filter_by(email=email).one()
    credential = db_session.get(PasswordCredential, user.id)
    assert credential.password_hash != password
    assert credential.password_hash.startswith("$argon2id$")
    assert client.post("/auth/email/verify", json={"token": token}).status_code == 400
    assert client.post("/auth/email/login", json={
        "email": email, "password": "a long incorrect password 123"
    }).status_code == 401
    signed_in = client.post("/auth/email/login", json={"email": email, "password": password})
    assert signed_in.status_code == 200, signed_in.text
    assert client.get("/auth/me").json()["email"] == email


def test_existing_oauth_account_not_claimable_by_registration(client, db_session, monkeypatch):
    _enable(monkeypatch)
    messages = _capture(monkeypatch)
    email = "linked-oauth-user@example.test"
    assert client.post("/auth/dev-login", json={"email": email}).status_code == 200
    user = db_session.query(User).filter_by(email=email).one()
    registered = client.post("/auth/email/register", json={
        "email": email, "password": "unauthorized password 123"
    })
    assert registered.status_code == 202
    assert messages == []
    assert db_session.get(PasswordCredential, user.id) is None
    forgot = client.post("/auth/email/forgot", json={"email": email})
    assert forgot.status_code == 202
    assert len(messages) == 1
    token = _token(messages)
    reset = client.post("/auth/email/reset", json={
        "token": token, "password": "new authorized password 123"
    })
    assert reset.status_code == 200, reset.text
    assert db_session.get(PasswordCredential, user.id) is not None
    assert client.post("/auth/email/reset", json={
        "token": token, "password": "another authorized password 123"
    }).status_code == 400
    assert client.post("/auth/email/login", json={
        "email": email, "password": "new authorized password 123"
    }).status_code == 200


def test_invalid_expired_token_and_generic_recovery(client, db_session, monkeypatch):
    _enable(monkeypatch)
    messages = _capture(monkeypatch)
    email = "expired-email-user@example.test"
    assert client.post("/auth/email/forgot", json={"email": email}).status_code == 202
    assert messages == []
    assert client.post("/auth/email/verify", json={"token": "x" * 45}).status_code == 400
    assert client.post("/auth/email/register", json={
        "email": email, "password": "a secure registration password"
    }).status_code == 202
    token = _token(messages)
    record = db_session.query(EmailActionToken).filter_by(purpose="verify", email=email).one()
    record.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db_session.commit()
    assert client.post("/auth/email/verify", json={"token": token}).status_code == 400


def test_rate_limit_and_retry_after(client, monkeypatch):
    _enable(monkeypatch)
    email = "throttled-user@example.test"
    data = {"email": email, "password": "long wrong password 123"}
    for _ in range(5):
        assert client.post("/auth/email/login", json=data).status_code == 401
    denied = client.post("/auth/email/login", json=data)
    assert denied.status_code == 429
    assert int(denied.headers["retry-after"]) >= 1


def test_register_fails_closed_without_smtp(client, monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    assert client.post("/auth/email/register", json={
        "email": "no-smtp@example.test", "password": "a secure registration password"
    }).status_code == 503



def test_brevo_transport_sends_via_https_api_and_signup_link(client, db_session, monkeypatch):
    """Actual route uses HTTPS, with API call mocked to avoid sending real email."""
    from types import SimpleNamespace
    from app.services import email_transport
    _enable(monkeypatch)
    monkeypatch.setattr(settings, "EMAIL_AUTH_TRANSPORT", "brevo")
    monkeypatch.setattr(settings, "BREVO_API_KEY", "private-test-api-key")
    monkeypatch.setattr(settings, "BREVO_SENDER_EMAIL", "verified@example.test")
    monkeypatch.setattr(settings, "BREVO_SENDER_NAME", "JobGrid")
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return SimpleNamespace(status_code=201)

    monkeypatch.setattr("httpx.post", fake_post)
    email = "brevo-test-registration@example.test"
    response = client.post("/auth/email/register", json={
        "email": email, "password": "a strong production password"
    })
    assert response.status_code == 202, response.text
    assert len(calls) == 1
    url, sent = calls[0]
    assert url == "https://api.brevo.com/v3/smtp/email"
    assert sent["headers"]["api-key"] == "private-test-api-key"
    assert sent["timeout"] <= 10.0
    assert sent["json"]["sender"] == {
        "email": "verified@example.test", "name": "JobGrid"
    }
    assert sent["json"]["to"] == [{"email": email}]
    assert "#email_action=verify&token=" in sent["json"]["htmlContent"]
    assert "private-test-api-key" not in sent["json"]["htmlContent"]
    assert db_session.query(User).filter_by(email=email).first() is None


def test_brevo_missing_key_fails_closed_without_smtp_fallback(client, monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(settings, "EMAIL_AUTH_TRANSPORT", "brevo")
    monkeypatch.setattr(settings, "BREVO_API_KEY", "")
    monkeypatch.setattr(settings, "BREVO_SENDER_EMAIL", "sender@example.test")
    response = client.post("/auth/email/register", json={
        "email": "missing-key@example.test", "password": "a strong production password"
    })
    assert response.status_code == 503


def test_brevo_provider_rejection_cleans_up_token(client, db_session, monkeypatch):
    from types import SimpleNamespace
    _enable(monkeypatch)
    monkeypatch.setattr(settings, "EMAIL_AUTH_TRANSPORT", "brevo")
    monkeypatch.setattr(settings, "BREVO_API_KEY", "private-test-api-key")
    monkeypatch.setattr(settings, "BREVO_SENDER_EMAIL", "verified@example.test")
    monkeypatch.setattr(
        "httpx.post",
        lambda *args, **kwargs: SimpleNamespace(status_code=401, text="sensitive data"),
    )
    email = "brevo-provider-error@example.test"
    response = client.post("/auth/email/register", json={
        "email": email, "password": "a strong production password"
    })
    assert response.status_code == 503
    assert "sensitive data" not in response.text
    assert "private-test-api-key" not in response.text
    assert db_session.query(EmailActionToken).filter_by(email=email).count() == 0


def test_brevo_transport_network_error_does_not_leak_credentials(monkeypatch):
    import httpx
    import pytest
    from app.services.email_transport import BrevoDeliveryError, send_via_brevo
    monkeypatch.setattr(settings, "BREVO_API_KEY", "private-test-api-key")
    monkeypatch.setattr(settings, "BREVO_SENDER_EMAIL", "verified@example.test")

    def offline(*args, **kwargs):
        raise httpx.ConnectError("Provider unreachable", request=httpx.Request("POST", "https://api.brevo.com/v3/smtp/email"))

    monkeypatch.setattr("httpx.post", offline)
    with pytest.raises(BrevoDeliveryError) as exc:
        send_via_brevo("recipient@example.test", "Subject", "<p>Message</p>")
    assert "private-test-api-key" not in str(exc.value)
