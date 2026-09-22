from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


EvidenceKind = Literal["confirmation_url", "confirmation_text", "note"]

MAX_EVIDENCE_TEXT_CHARS = 20_000
MAX_EVIDENCE_URL_CHARS = 2_048
MAX_CORRECTION_REASON_CHARS = 500
EVIDENCE_SOFT_DELETE_RETENTION_DAYS = 30
EVIDENCE_RECEIPT_RETENTION_DAYS = 30
EVIDENCE_BODY_RETENTION = timedelta(days=EVIDENCE_SOFT_DELETE_RETENTION_DAYS)
EVIDENCE_RECEIPT_RETENTION = timedelta(days=EVIDENCE_RECEIPT_RETENTION_DAYS)


class EvidenceContractError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class EvidenceCreateData(BaseModel):
    """Strict validated evidence input shared by the future JG-034 route."""

    model_config = ConfigDict(extra="forbid", strict=True)

    kind: EvidenceKind
    body: str = Field(min_length=1, max_length=MAX_EVIDENCE_TEXT_CHARS)
    occurred_at: datetime | None = None

    @model_validator(mode="after")
    def validate_kind_body(self):
        if not self.body.strip():
            raise ValueError("Evidence body must contain non-whitespace text.")
        if self.kind == "confirmation_url":
            validate_confirmation_url(self.body)
        return self


def validate_confirmation_url(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_EVIDENCE_URL_CHARS:
        raise EvidenceContractError(
            "invalid_evidence_url",
            "Confirmation URL must contain 1 to 2048 characters.",
        )
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise EvidenceContractError(
            "invalid_evidence_url", "Confirmation URL is invalid."
        ) from exc
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or port is not None and not 0 < port <= 65535
    ):
        raise EvidenceContractError(
            "invalid_evidence_url",
            "Confirmation URL must be credential-free HTTP(S).",
        )
    return value


def validate_correction_reason(value: str) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or len(value) > MAX_CORRECTION_REASON_CHARS
    ):
        raise EvidenceContractError(
            "invalid_correction_reason",
            "Correction reason must contain 1 to 500 trimmed characters.",
        )
    return value


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def evidence_body_purge_at(deleted_at: datetime) -> datetime:
    """Return the absolute end of the deleted-body recovery window."""
    return _aware_utc(deleted_at) + EVIDENCE_BODY_RETENTION


def evidence_body_is_recoverable(
    *,
    is_deleted: bool,
    body: str | None,
    updated_at: datetime,
    now: datetime | None = None,
) -> bool:
    if not is_deleted or body is None:
        return False
    reference = _aware_utc(now or datetime.now(timezone.utc))
    return reference < evidence_body_purge_at(updated_at)


def receipt_expires_at(created_at: datetime) -> datetime:
    return _aware_utc(created_at) + EVIDENCE_RECEIPT_RETENTION


def evidence_create_payload_hash(
    *,
    track_id: int,
    request_key: UUID | str,
    data: EvidenceCreateData,
) -> str:
    """Hash the exact create intent without logging or persisting private text."""
    key = UUID(str(request_key))
    occurred_at = data.occurred_at
    if occurred_at is not None:
        occurred_at = _aware_utc(occurred_at)
        occurred_value = occurred_at.isoformat().replace("+00:00", "Z")
    else:
        occurred_value = None
    material = {
        "track_id": track_id,
        "request_key": str(key),
        "kind": data.kind,
        "body": data.body,
        "occurred_at": occurred_value,
    }
    encoded = json.dumps(
        material, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
