import os
import subprocess
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import (
    ProductionConfigurationError,
    cookie_security_options,
    settings,
    validate_runtime_settings,
)
from app.routers import auth_router


BACKEND_ROOT = Path(__file__).resolve().parents[1]
SAFE_PRODUCTION_SECRET = "jg022-production-secret-0123456789abcdef"


def _production_settings(**overrides):
    values = {
        "ENVIRONMENT": "production",
        "TEST_AUTH": False,
        "SECRET_KEY": SAFE_PRODUCTION_SECRET,
        "FRONTEND_URL": "https://app.example.test",
        "OAUTH_REDIRECT_BASE": "https://api.example.test",
        "CORS_ORIGINS": ["https://app.example.test"],
        "CORS_ORIGINS_EXPLICIT": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _run_backend_python(code: str, **environment_overrides):
    environment = os.environ.copy()
    environment.update(
        {
            "DATABASE_URL": "sqlite:///:memory:",
            "ENVIRONMENT": "production",
            "TEST_AUTH": "false",
            "SECRET_KEY": SAFE_PRODUCTION_SECRET,
            "FRONTEND_URL": "https://app.example.test",
            "OAUTH_REDIRECT_BASE": "https://api.example.test",
            "CORS_ORIGINS": "https://app.example.test",
            "RUN_MAINTENANCE_JOBS": "false",
        }
    )
    environment.update(environment_overrides)
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_production_test_auth_rejected_before_serving():
    result = _run_backend_python("import app.main", TEST_AUTH="true")

    assert result.returncode != 0
    combined_output = f"{result.stdout}\n{result.stderr}"
    assert "TEST_AUTH must be disabled when ENVIRONMENT=production" in combined_output
    assert SAFE_PRODUCTION_SECRET not in combined_output


@pytest.mark.parametrize(
    "secret_key",
    [
        "",
        "dev-secret-change-me",
        "change-me-to-a-long-random-string",
        "changeme-generate-with-openssl-rand-hex-32",
        "short-production-secret",
    ],
)
def test_default_or_empty_key_rejected(secret_key):
    with pytest.raises(ProductionConfigurationError) as exc_info:
        validate_runtime_settings(_production_settings(SECRET_KEY=secret_key))

    message = str(exc_info.value)
    assert "SECRET_KEY" in message
    if secret_key:
        assert secret_key not in message


@pytest.mark.parametrize(
    ("overrides", "expected_field"),
    [
        ({"FRONTEND_URL": "http://app.example.test"}, "FRONTEND_URL"),
        ({"FRONTEND_URL": "https://localhost"}, "FRONTEND_URL"),
        ({"OAUTH_REDIRECT_BASE": "http://api.example.test"}, "OAUTH_REDIRECT_BASE"),
        ({"OAUTH_REDIRECT_BASE": "https://127.0.0.1:8000"}, "OAUTH_REDIRECT_BASE"),
        ({"CORS_ORIGINS_EXPLICIT": False}, "CORS_ORIGINS"),
        ({"CORS_ORIGINS": []}, "CORS_ORIGINS"),
        ({"CORS_ORIGINS": ["http://app.example.test"]}, "CORS_ORIGINS"),
        ({"CORS_ORIGINS": ["https://localhost:5173"]}, "CORS_ORIGINS"),
    ],
)
def test_https_and_cors_validation(overrides, expected_field):
    with pytest.raises(ProductionConfigurationError) as exc_info:
        validate_runtime_settings(_production_settings(**overrides))

    assert expected_field in str(exc_info.value)


def test_https_and_cors_validation_accepts_explicit_public_https_origins():
    validate_runtime_settings(
        _production_settings(
            CORS_ORIGINS=[
                "https://app.example.test",
                "https://admin.example.test",
            ]
        )
    )


def test_environment_dev_login_preserved(client, monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")
    monkeypatch.setattr(settings, "TEST_AUTH", True)

    response = client.post(
        "/auth/dev-login",
        json={"email": f"jg022-{uuid.uuid4()}@example.test"},
    )

    assert response.status_code == 200
    assert response.json()["email"].startswith("jg022-")


def test_production_dev_login_is_404_for_any_payload():
    script = """
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
for payload in ({}, {"email": "prod@example.test"}, {"email": 123}, "invalid"):
    response = client.post("/auth/dev-login", json=payload)
    assert response.status_code == 404, (payload, response.status_code, response.text)
print("production-dev-login-404")
"""
    result = _run_backend_python(script)

    assert result.returncode == 0, result.stderr
    assert "production-dev-login-404" in result.stdout


def test_cookie_policy_is_secure_and_cross_site_only_in_production():
    assert cookie_security_options("production") == {
        "secure": True,
        "samesite": "none",
    }
    assert cookie_security_options("test") == {
        "secure": False,
        "samesite": "lax",
    }
    assert cookie_security_options("development") == {
        "secure": False,
        "samesite": "lax",
    }


def test_production_oauth_session_middleware_uses_secure_none_cookie():
    script = """
from starlette.middleware.sessions import SessionMiddleware
from app.main import app

middleware = next(item for item in app.user_middleware if item.cls is SessionMiddleware)
assert middleware.kwargs["https_only"] is True
assert middleware.kwargs["same_site"] == "none"
print("production-session-cookie-secure-none")
"""
    result = _run_backend_python(script)

    assert result.returncode == 0, result.stderr
    assert "production-session-cookie-secure-none" in result.stdout


class _FakeOAuthClient:
    async def authorize_access_token(self, request, **kwargs):
        return {
            "userinfo": {
                "email": f"oauth-{uuid.uuid4()}@example.test",
                "sub": f"provider-{uuid.uuid4()}",
            }
        }


def test_production_oauth_callback_and_logout_use_secure_none_cookie(
    client,
    monkeypatch,
):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(auth_router, "_client", lambda provider: _FakeOAuthClient())

    callback = client.get("/auth/callback/google", follow_redirects=False)
    assert callback.status_code in {302, 307}
    callback_cookie = callback.headers["set-cookie"]
    assert "session_token=" in callback_cookie
    assert "HttpOnly" in callback_cookie
    assert "Secure" in callback_cookie
    assert "SameSite=none" in callback_cookie

    logout = client.post("/auth/logout", follow_redirects=False)
    assert logout.status_code == 303
    logout_cookie = logout.headers["set-cookie"]
    assert "session_token=" in logout_cookie
    assert "HttpOnly" in logout_cookie
    assert "Secure" in logout_cookie
    assert "SameSite=none" in logout_cookie
