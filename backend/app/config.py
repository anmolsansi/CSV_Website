import ipaddress
import os
import tempfile
from pathlib import Path
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


class DocumentStorageConfigurationError(RuntimeError):
    """Raised when private document storage is absent or unsafe."""


def validate_document_storage_path(
    storage_dir: str | None,
    *,
    environment: str | None,
) -> Path:
    """Resolve a private filesystem root for local/dev filesystem storage."""
    raw = str(storage_dir or "").strip()
    if not raw:
        raise DocumentStorageConfigurationError(
            "DOCUMENT_STORAGE_DIR is not configured"
        )

    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        raise DocumentStorageConfigurationError(
            "DOCUMENT_STORAGE_DIR must be an absolute path"
        )
    candidate = candidate.resolve(strict=False)

    repo_root = Path(__file__).resolve().parents[2]
    public_roots = (
        repo_root,
        repo_root / "frontend" / "public",
        repo_root / "frontend" / "dist",
    )
    for unsafe_root in public_roots:
        unsafe = unsafe_root.resolve(strict=False)
        if candidate == unsafe or unsafe in candidate.parents:
            raise DocumentStorageConfigurationError(
                "DOCUMENT_STORAGE_DIR must be outside the repository and served directories"
            )

    if is_production_environment(environment):
        temp_root = Path(tempfile.gettempdir()).resolve(strict=False)
        if candidate == temp_root or temp_root in candidate.parents:
            raise DocumentStorageConfigurationError(
                "DOCUMENT_STORAGE_DIR must use durable storage in production"
            )

    return candidate


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
        or normalized_secret.startswith(
            ("changeme", "change-me", "dev-secret", "test-secret")
        )
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

    origins = list(getattr(runtime_settings, "CORS_ORIGINS", []) or [])
    if not origins:
        raise ProductionConfigurationError(
            "CORS_ORIGINS must include at least one public HTTPS origin in production"
        )
    for origin in origins:
        _validate_public_https_url("CORS_ORIGINS", origin)


class Settings:
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data.db")
    # APP_SECRET_KEY intentionally takes precedence over the historical
    # SECRET_KEY variable so hosted services can rotate away from an old value.
    SECRET_KEY = os.getenv("APP_SECRET_KEY") or os.getenv(
        "SECRET_KEY", "change-me-to-a-long-random-string"
    )
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    TEST_AUTH = os.getenv("TEST_AUTH", "false").lower() == "true"
    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")
    OAUTH_REDIRECT_BASE = os.getenv(
        "OAUTH_REDIRECT_BASE", "http://localhost:8000"
    ).rstrip("/")

    _raw_cors = os.getenv("CORS_ORIGINS")
    CORS_ORIGINS_EXPLICIT = bool(_raw_cors and _raw_cors.strip())
    CORS_ORIGINS = _split_env_list(_raw_cors) or [FRONTEND_URL]

    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
    MICROSOFT_CLIENT_ID = os.getenv("MICROSOFT_CLIENT_ID", "")
    MICROSOFT_CLIENT_SECRET = os.getenv("MICROSOFT_CLIENT_SECRET", "")
    APPLE_CLIENT_ID = os.getenv("APPLE_CLIENT_ID", "")
    APPLE_CLIENT_SECRET = os.getenv("APPLE_CLIENT_SECRET", "")

    SENTRY_DSN = os.getenv("SENTRY_DSN", "")

    RUN_MAINTENANCE_JOBS = os.getenv("RUN_MAINTENANCE_JOBS", "false").lower() == "true"
    CLEANUP_INTERVAL_MINUTES = max(
        1, int(os.getenv("CLEANUP_INTERVAL_MINUTES", "60"))
    )
    AUTO_ARCHIVE_AFTER_DAYS = max(
        0, int(os.getenv("AUTO_ARCHIVE_AFTER_DAYS", "0"))
    )
    AUTO_PURGE_AFTER_DAYS = max(
        0, int(os.getenv("AUTO_PURGE_AFTER_DAYS", "0"))
    )
    JOB_URL_CHECKS_ENABLED = os.getenv("JOB_URL_CHECKS_ENABLED", "false").lower() == "true"

    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
    EMAIL_FROM = os.getenv("EMAIL_FROM", "")

    RUN_REMINDER_WORKER = os.getenv("RUN_REMINDER_WORKER", "false").lower() == "true"
    REMINDER_EMAIL_DELIVERY_ENABLED = os.getenv(
        "REMINDER_EMAIL_DELIVERY_ENABLED", "false"
    ).lower() == "true"
    REMINDER_WORKER_INTERVAL_SECONDS = max(
        30, int(os.getenv("REMINDER_WORKER_INTERVAL_SECONDS", "60"))
    )
    REMINDER_LEASE_SECONDS = max(
        30, int(os.getenv("REMINDER_LEASE_SECONDS", "300"))
    )

    # Local/dev filesystem document storage. Production C-09 uses the S3
    # adapter configured through DOCUMENT_STORAGE_BACKEND and provider secrets.
    DOCUMENT_STORAGE_DIR = os.getenv("DOCUMENT_STORAGE_DIR", "")


settings = Settings()
validate_runtime_settings(settings)
