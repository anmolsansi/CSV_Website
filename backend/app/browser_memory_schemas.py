"""Strict, offline-only input boundaries for JobGrid browser memory (EXT-07).

These models are intentionally not wired to HTTP routes until EXT-14/19. The
existing import/capture URL validation and canonical identity are unchanged.
"""
from __future__ import annotations

from ipaddress import ip_address
import re
from typing import Literal
from urllib.parse import unquote_plus, urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .services.job_identity import JobIdentityError, canonicalize_job_url


_SECRET_QUERY_KEYS = frozenset({
    "token", "access_token", "auth", "authorization", "code",
    "password", "session", "session_token",
})
_HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$", re.IGNORECASE)
_LOCAL_SUFFIXES = (".localhost", ".local", ".internal")


class BrowserMemoryValidationError(ValueError):
    """Safe error shape for later browser-memory HTTP adapters."""

    code = "invalid_browser_memory_payload"
    status_code = 422

    def __init__(self, message: str, *, field: str | None = None):
        super().__init__(message)
        self.message = message
        self.field = field

    def as_detail(self) -> dict:
        detail = {"code": self.code, "message": self.message}
        if self.field is not None:
            detail["field"] = self.field
        return detail


def validate_public_job_url(url: str) -> str:
    """Validate untrusted navigation metadata without DNS, HTTP or page access.

    This deliberately adds restrictions only for extension callers. It must
    not be applied to legacy imports or persisted original URLs.
    """
    try:
        canonicalize_job_url(url)
        parts = urlsplit(url)
    except (JobIdentityError, ValueError) as exc:
        raise ValueError("A valid public HTTP(S) job URL is required.") from exc

    hostname = parts.hostname or ""
    host = hostname.rstrip(".").casefold()
    if not host or host == "localhost" or host.endswith(_LOCAL_SUFFIXES):
        raise ValueError("A public hostname is required.")

    try:
        address = ip_address(host)
    except ValueError:
        try:
            ascii_host = host.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise ValueError("A public hostname is required.") from exc
        labels = ascii_host.split(".")
        # Refuse single-label names and numeric shorthand for private IPs.
        if len(labels) < 2 or not all(_HOST_LABEL.fullmatch(part) for part in labels):
            raise ValueError("A public hostname is required.")
        if all(part.isdigit() for part in labels) or host.startswith("0x"):
            raise ValueError("A public hostname is required.")
    else:
        if not address.is_global:
            raise ValueError("A public IP address is required.")

    for segment in parts.query.split("&"):
        key = unquote_plus(segment.split("=", 1)[0]).casefold()
        if key in _SECRET_QUERY_KEYS:
            raise ValueError("Job URL must not contain credential-like query keys.")
    return url


class _PublicJobURL(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    url: str = Field(min_length=1, max_length=2048)

    @field_validator("url")
    @classmethod
    def _url_is_public(cls, value: str) -> str:
        return validate_public_job_url(value)


class BrowserCheckIn(_PublicJobURL):
    company: str | None = Field(default=None, max_length=320)
    title: str | None = Field(default=None, max_length=500)


class BrowserVisitIn(_PublicJobURL):
    pass


class BrowserApplyIn(_PublicJobURL):
    company: str = Field(min_length=1, max_length=320)
    title: str = Field(min_length=1, max_length=500)
    confirmed: bool

    @field_validator("company", "title")
    @classmethod
    def _nonempty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("This field must not be blank.")
        return value

    @field_validator("confirmed", mode="before")
    @classmethod
    def _literal_true(cls, value: object) -> object:
        if value is not True:
            raise ValueError("Explicit boolean true confirmation is required.")
        return value


def validate_apply_idempotency_key(value: object) -> str:
    """Validate one canonical, hyphenated UUID header, not an owner key."""
    if not isinstance(value, str) or len(value) != 36:
        raise BrowserMemoryValidationError("A UUID Idempotency-Key is required.", field="Idempotency-Key")
    try:
        parsed = UUID(value)
    except ValueError as exc:
        raise BrowserMemoryValidationError("A UUID Idempotency-Key is required.", field="Idempotency-Key") from exc
    if str(parsed) != value.lower():
        raise BrowserMemoryValidationError("A UUID Idempotency-Key is required.", field="Idempotency-Key")
    return str(parsed)


def parse_browser_memory_payload(kind: Literal["check", "visit", "apply"], payload: object):
    """Wrap Pydantic failures in the frozen API-safe detail contract.

    The router added by a later ticket maps the returned exception to
    HTTP 422 {detail: {code, message, field?}} without echoing private input.
    """
    schema = {"check": BrowserCheckIn, "visit": BrowserVisitIn, "apply": BrowserApplyIn}[kind]
    try:
        return schema.model_validate(payload)
    except ValidationError as exc:
        first = exc.errors()[0]
        field = str(first["loc"][0]) if first["loc"] else None
        message = "Unexpected field." if first["type"] == "extra_forbidden" else "Invalid browser-memory input."
        raise BrowserMemoryValidationError(message, field=field) from exc
