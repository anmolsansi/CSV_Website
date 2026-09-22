from __future__ import annotations

import hashlib
import json
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .services.validation import ValidationContractError, validate_job_url


CAPTURE_NOTES_MAX_CHARS = 20_000
CAPTURE_TEXT_MAX_CHARS = 300
CaptureSource = Literal["manual", "bookmarklet"]


class CaptureContractError(ValueError):
    def __init__(self, code: str, message: str, *, field: str | None = None):
        super().__init__(message)
        self.code = code
        self.field = field


class CaptureRequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    job_url: str
    title: str = Field(min_length=1, max_length=CAPTURE_TEXT_MAX_CHARS)
    company: str = Field(min_length=1, max_length=CAPTURE_TEXT_MAX_CHARS)
    source: CaptureSource
    notes: str | None = Field(default=None, max_length=CAPTURE_NOTES_MAX_CHARS)

    @field_validator("job_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        try:
            return validate_job_url(value, field="job_url")
        except ValidationContractError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("title", "company")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Value must contain non-whitespace text.")
        return value

    @field_validator("notes")
    @classmethod
    def reject_oversize_notes_bytes(cls, value: str | None) -> str | None:
        if value is not None and len(value) > CAPTURE_NOTES_MAX_CHARS:
            raise ValueError("notes must be at most 20000 characters.")
        return value


class CaptureMatchOut(BaseModel):
    track_id: int | None = None
    row_id: int | None = None
    confidence: Literal["exact", "canonical", "possible"]
    reason: str
    company: str | None = None
    title: str | None = None
    status: str | None = None
    applied_at: str | None = None


class CaptureResponseOut(BaseModel):
    row_id: int
    created: bool
    replayed: bool = False
    matches: list[CaptureMatchOut] = Field(default_factory=list)
    company_history_count: int = 0


def normalized_capture_payload(payload: CaptureRequestIn) -> dict:
    return payload.model_dump(mode="json", exclude_none=False)


def capture_payload_hash(payload: CaptureRequestIn) -> str:
    encoded = json.dumps(
        normalized_capture_payload(payload),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalize_request_key(value: str) -> str:
    try:
        return str(UUID(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise CaptureContractError(
            "invalid_idempotency_key",
            "Idempotency-Key must be a valid UUID.",
            field="Idempotency-Key",
        ) from exc
