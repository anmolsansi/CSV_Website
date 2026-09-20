import ipaddress
import os
from urllib.parse import urlsplit

from dotenv import load_dotenv

load_dotenv()


def _split_env_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def is_production_environment(value: str | None) -> bool:
    return str(value or "").strip().lower() == "production"


def cookie_security_options(environment: str | None) -> dict[str, object]:
    """Return the server-controlled cookie policy for the current environment."""
    is_production = is_production_environment(environment)
    return {
        "secure": is_production,
        "samesite": "none" if is_production else "lax",
    }


class ProductionConfigurationError(RuntimeError):
    """Raised when a production-only safety requirement is not satisfied."""


_INSECURE_SECRET_VALUES = {
    "dev-secret-change-me",
    "change-me-to-a-long-random-string",
    "changeme-generate-with-openssl-rand-hex-32",
    "test-secret",
}


def _is_local_or_loopback_hostname(hostname: str | None) -> bool:
    if not hostname:
        return True

    normalized = hostname.strip().lower()
    if normalized == "localhost" or normalized.endswith(".localhost"):
        return True

    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return False

    return address.is_loopback or address.is_unspecified


def _validate_public_https_url(field_name: str, value: str | None) -> None:
    raw_value = str(value or "").strip()
    parsed = urlsplit(raw_value)

    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or _is_local_or_loopback_hostname(parsed.hostname)
    ):
        raise ProductionConfigurationError(
            f"{field_name} must be a public HTTPS URL in production"
        )


def validate_runtime_settings(runtime_settings) -> None:
    """Fail fast on unsafe production configuration without exposing secrets."""
    if not is_production_environment(getattr(runtime_settings, "ENVIRONMENT", "")):
        return

    if bool(getattr(runtime_settings, "TEST_AUTH", False)):
        raise ProductionConfigurationError(
            "TEST_AUTH must be disabled when ENVIRONMENT=production"
        )

    secret_key = str(getattr(runtime_settings, "SECRET_KEY", "") or "")
    normalized_secret = secret_key.strip().lower()
    if (
        len(secret_key.encode("utf-8")) < 32
        or normalized_secret in _INSECURE_SECRET_VALUES
        or normalized_secret.startswith(("changeme", "change-me", "dev-secret", "test-secret"))
    ):
        raise ProductionConfigurationError(
            "SECRET_KEY must contain at least 32 random bytes and must not use a default or placeholder value"
        )

    _validate_public_https_url(
        "FRONTEND_URL",
        getattr(runtime_settings, "FRONTEND_URL", ""),
    )
    _validate_public_https_url(
        "OAUTH_REDIRECT_BASE",
        getattr(runtime_settings, "OAUTH_REDIRECT_BASE", ""),
    )

    if not bool(getattr(runtime_settings, "CORS_ORIGINS_EXPLICIT", False)):
        raise ProductionConfigurationError(
            "CORS_ORIGINS must be explicitly configured in production"
        )

    cors_origins = list(getattr(runtime_settings, "CORS_ORIGINS", []) or [])
    if not cors_origins:
        raise ProductionConfigurationError(
            "CORS_ORIGINS must contain at least one production origin"
        )

    for origin in cors_origins:
        _validate_public_https_url("CORS_ORIGINS", origin)


_EXPLICIT_CORS_ORIGINS = (
    _split_env_list(os.getenv("CORS_ORIGINS"))
    or _split_env_list(os.getenv("FRONTEND_URLS"))
)


class Settings:
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://postgres:postgres@localhost:5432/csvapp",
    )
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")

    MICROSOFT_CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID", "")
    MICROSOFT_CLIENT_SECRET = os.getenv("MICROSOFT_CLIENT_SECRET", "")
    # Use 'common' for multi-tenant + personal accounts, or a specific tenant id.
    MICROSOFT_TENANT = os.getenv("MICROSOFT_TENANT", "common")

    # Apple: client secret is a signed JWT generated from the .p8 key below.
    APPLE_CLIENT_ID = os.getenv("APPLE_CLIENT_ID", "")  # Services ID
    APPLE_TEAM_ID = os.getenv("APPLE_TEAM_ID", "")
    APPLE_KEY_ID = os.getenv("APPLE_KEY_ID", "")
    # Path to the .p8 private key file downloaded from Apple Developer.
    APPLE_PRIVATE_KEY_PATH = os.getenv("APPLE_PRIVATE_KEY_PATH", "")

    OAUTH_REDIRECT_BASE = os.getenv("OAUTH_REDIRECT_BASE", "http://localhost:8000")
    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
    CORS_ORIGINS_EXPLICIT = bool(_EXPLICIT_CORS_ORIGINS)
    CORS_ORIGINS = _EXPLICIT_CORS_ORIGINS or [
        FRONTEND_URL,
        "http://127.0.0.1:5173",
    ]
    CLEANUP_INTERVAL_MINUTES = int(os.getenv("CLEANUP_INTERVAL_MINUTES", "60"))

    # JG-012 retention contract. These new controls are deliberately disabled
    # by default and are not derived from the legacy DELETE_AFTER_DAYS value.
    AUTO_ARCHIVE_AFTER_DAYS = int(os.getenv("AUTO_ARCHIVE_AFTER_DAYS", "0"))
    AUTO_PURGE_AFTER_DAYS = int(os.getenv("AUTO_PURGE_AFTER_DAYS", "0"))
    RUN_MAINTENANCE_JOBS = (
        os.getenv("RUN_MAINTENANCE_JOBS", "false").lower() == "true"
    )

    # Deprecated compatibility setting. JG-013 removes the legacy cleanup
    # behavior that still references this name. Do not map it into either new
    # retention control, because that could silently activate destructive work.
    DELETE_AFTER_DAYS = int(os.getenv("DELETE_AFTER_DAYS", "2"))
    TEST_AUTH = os.getenv("TEST_AUTH", "false").lower() == "true"

    # Email / SMTP
    EMAIL_FROM = os.getenv("EMAIL_FROM", "")
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASS = os.getenv("SMTP_PASS", "")

    # Sentry
    SENTRY_DSN = os.getenv("SENTRY_DSN", "")


settings = Settings()

# Validate as soon as configuration is loaded so unsafe production settings fail
# before database initialization, route registration, or background-job startup.
validate_runtime_settings(settings)
