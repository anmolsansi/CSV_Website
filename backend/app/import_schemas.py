from __future__ import annotations

import hashlib
import json
import unicodedata
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator, model_validator

from .models import CSV_COLUMNS


MAX_IMPORT_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_IMPORT_RECORDS = 2000
MAX_IMPORT_PREVIEW_ROWS = 100
IMPORT_PREVIEW_TTL_HOURS = 24
IMPORT_COMMITTED_RESULT_DAYS = 30

# Imports may enrich source-derived CSV data, but they never own lifecycle or
# application-memory state. URL is identity and is therefore not mutable on an
# exact-match update.
IMPORT_UPDATE_ALLOWLIST = frozenset(field for field in CSV_COLUMNS if field != "url")
FORBIDDEN_IMPORT_UPDATE_FIELDS = frozenset(
    {
        "url",
        "user_id",
        "id",
        "upload_batch_id",
        "clicked",
        "clicked_at",
        "archived",
        "archived_at",
        "status",
        "notes",
        "applied_at",
        "follow_up_at",
    }
)


class ImportContractError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 422,
        field: str = "__root__",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.field = field

    def as_detail(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "fields": [{"field": self.field, "message": self.message}],
        }


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def normalize_header_label(value: str) -> str:
    # NFC removes Unicode representation ambiguity without changing visible
    # labels or collapsing whitespace/case. Position remains part of the hash.
    return unicodedata.normalize("NFC", value)


def header_fingerprint(headers: list[str]) -> str:
    normalized = [normalize_header_label(value) for value in headers]
    return sha256_json(normalized)


def validate_mapping(mapping: Any, *, column_count: int) -> dict[str, str]:
    if not isinstance(mapping, dict) or not mapping:
        raise ImportContractError(
            "mapping_required",
            "Mapping must be a non-empty object from source column index to JobGrid field.",
            field="mapping",
        )

    normalized: dict[str, str] = {}
    used_targets: set[str] = set()
    for raw_index, target in mapping.items():
        try:
            source_index = int(raw_index)
        except (TypeError, ValueError) as exc:
            raise ImportContractError(
                "invalid_mapping_index",
                "Mapping source keys must be zero-based integer column indexes.",
                field="mapping",
            ) from exc
        if isinstance(raw_index, bool) or source_index < 0 or source_index >= column_count:
            raise ImportContractError(
                "invalid_mapping_index",
                "Mapping source index is outside the uploaded column range.",
                field=f"mapping.{raw_index}",
            )
        if str(source_index) in normalized:
            raise ImportContractError(
                "duplicate_mapping_index",
                "A source column may be mapped only once.",
                field=f"mapping.{raw_index}",
            )
        if not isinstance(target, str) or target not in CSV_COLUMNS:
            raise ImportContractError(
                "unknown_target_field",
                "Mapping targets must be known JobGrid CSV fields.",
                field=f"mapping.{raw_index}",
            )
        if target in used_targets:
            raise ImportContractError(
                "duplicate_target_field",
                "One JobGrid target field may have only one source column.",
                field=f"mapping.{raw_index}",
            )
        normalized[str(source_index)] = target
        used_targets.add(target)

    if "url" not in used_targets:
        raise ImportContractError(
            "url_mapping_required",
            "Exactly one source column must map to the required url field.",
            field="mapping",
        )
    return normalized


def validate_update_fields(fields: list[str]) -> list[str]:
    seen: set[str] = set()
    validated: list[str] = []
    for index, field in enumerate(fields):
        if field in seen:
            continue
        if field not in IMPORT_UPDATE_ALLOWLIST:
            raise ImportContractError(
                "forbidden_update_field",
                "Import updates may change only allowlisted source CSV fields and never lifecycle/application-memory fields.",
                field=f"update_fields[{index}]",
            )
        seen.add(field)
        validated.append(field)
    return validated


class ImportCommitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: StrictInt = Field(gt=0)
    idempotency_key: str = Field(min_length=36, max_length=36)
    mode: Literal["insert_only", "update_selected"] = "insert_only"
    update_fields: list[str] = Field(default_factory=list, max_length=len(CSV_COLUMNS))
    invalid_policy: Literal["reject", "skip"] = "reject"
    replace_empty: StrictBool = False
    possible_duplicate_policy: Literal["skip", "create"] = "skip"

    @field_validator("idempotency_key")
    @classmethod
    def valid_idempotency_key(cls, value: str) -> str:
        try:
            parsed = UUID(value)
        except (ValueError, AttributeError) as exc:
            raise ValueError("idempotency_key must be a UUID.") from exc
        canonical = str(parsed)
        if canonical != value.lower():
            raise ValueError("idempotency_key must use canonical UUID form.")
        return canonical

    @field_validator("update_fields")
    @classmethod
    def update_field_contract(cls, value: list[str]) -> list[str]:
        try:
            return validate_update_fields(value)
        except ImportContractError as exc:
            raise ValueError(exc.message) from exc

    @model_validator(mode="after")
    def mode_contract(self):
        if self.mode == "insert_only" and self.update_fields:
            raise ValueError("update_fields must be empty in insert_only mode.")
        if self.mode == "update_selected" and not self.update_fields:
            raise ValueError("update_selected mode requires at least one allowlisted update field.")
        return self
