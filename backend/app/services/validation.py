from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel

from ..models import JOB_TRACK_STATUS_VALUES, JobTrack

STATUS_VALUES = tuple(JOB_TRACK_STATUS_VALUES)
MAX_BULK_IDS = 500
MAX_JOB_URL_CHARS = 2048
MAX_COMPANY_TITLE_CHARS = 300
MAX_NOTES_CHARS = 20_000

_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ALLOWED_URL_SCHEMES = frozenset({"http", "https"})


@dataclass(frozen=True)
class ValidationFieldError:
    field: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"field": self.field, "message": self.message}


class ValidationContractError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        field: str = "__root__",
        code: str = "validation_error",
        status_code: int = 422,
    ):
        super().__init__(message)
        self.message = message
        self.field = field
        self.code = code
        self.status_code = status_code

    def to_detail(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "fields": [ValidationFieldError(self.field, self.message).as_dict()],
        }


@dataclass(frozen=True)
class NormalizedBulkIds:
    ids: tuple[int, ...]
    source_indices: dict[int, tuple[int, ...]]


def validate_status(value: Any, *, field: str = "status") -> str:
    if value is None:
        raise ValidationContractError(
            "Status may be omitted but cannot be null.",
            field=field,
        )
    if not isinstance(value, str) or value not in STATUS_VALUES:
        raise ValidationContractError(
            f"Status must be one of: {', '.join(STATUS_VALUES)}.",
            field=field,
        )
    return value


def explicit_model_fields(model: BaseModel) -> dict[str, Any]:
    """Return only caller-supplied Pydantic fields, preserving explicit clears."""
    supplied = set(model.model_fields_set)
    return model.model_dump(include=supplied, exclude_unset=True)


def _resolve_timezone(timezone_name: str | None, *, field: str) -> ZoneInfo:
    if not timezone_name:
        raise ValidationContractError(
            "A valid IANA timezone is required for date-only values.",
            field=field,
        )
    try:
        return ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValidationContractError(
            "A valid IANA timezone is required for date-only values.",
            field=field,
        ) from exc


def parse_timestamp(
    value: Any,
    *,
    timezone_name: str | None = None,
    field: str = "timestamp",
    allow_clear: bool = True,
) -> datetime | None:
    """Parse the R5 timestamp contract into the app's UTC-naive storage form."""
    if value is None or value == "":
        if allow_clear:
            return None
        raise ValidationContractError(
            "This timestamp cannot be cleared.",
            field=field,
        )

    if not isinstance(value, str):
        raise ValidationContractError(
            "Timestamp must be an ISO-8601 string, null, or an empty string.",
            field=field,
        )

    if _DATE_ONLY_RE.fullmatch(value):
        try:
            parsed_date = date.fromisoformat(value)
        except ValueError as exc:
            raise ValidationContractError(
                "Date is not valid.",
                field=field,
            ) from exc
        account_timezone = _resolve_timezone(timezone_name, field=field)
        local_midnight = datetime.combine(
            parsed_date,
            time.min,
            tzinfo=account_timezone,
        )
        return local_midnight.astimezone(timezone.utc).replace(tzinfo=None)

    normalized = value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValidationContractError(
            "Timestamp must be valid ISO-8601.",
            field=field,
        ) from exc

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValidationContractError(
            "Datetime values must include an explicit UTC offset or Z.",
            field=field,
        )
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def validate_text_limits(values: Mapping[str, Any]) -> dict[str, Any]:
    """Validate mutable JobTrack text fields without rewriting accepted values."""
    limits = {
        "company": MAX_COMPANY_TITLE_CHARS,
        "title": MAX_COMPANY_TITLE_CHARS,
        "notes": MAX_NOTES_CHARS,
    }
    validated = dict(values)
    for field, limit in limits.items():
        if field not in values:
            continue
        value = values[field]
        if value is None:
            continue
        if not isinstance(value, str):
            raise ValidationContractError(
                "Value must be a string or null.",
                field=field,
            )
        if len(value) > limit:
            raise ValidationContractError(
                f"Value must be at most {limit} characters.",
                field=field,
            )
    return validated


def prepare_job_track_patch(
    values: Mapping[str, Any],
    *,
    timezone_name: str | None,
    current_status: str,
    current_applied_at: datetime | None,
) -> dict[str, Any]:
    """Validate one application patch before the caller mutates ORM state."""
    prepared = validate_text_limits(values)

    if "status" in prepared:
        prepared["status"] = validate_status(prepared["status"])

    for field in ("applied_at", "follow_up_at"):
        if field in prepared:
            prepared[field] = parse_timestamp(
                prepared[field],
                timezone_name=timezone_name,
                field=field,
            )

    target_status = prepared.get("status", current_status)
    if prepared.get("mark_applied"):
        target_status = "applied"
    target_applied_at = prepared.get("applied_at", current_applied_at)

    if (
        "applied_at" in prepared
        and target_applied_at is None
        and target_status == "applied"
    ):
        raise ValidationContractError(
            "Applied date cannot be cleared while status remains applied.",
            field="applied_at",
        )

    return prepared


def validate_job_url(value: Any, *, field: str = "url") -> str:
    if not isinstance(value, str) or not value:
        raise ValidationContractError(
            "URL must be a non-empty HTTP(S) URL.",
            field=field,
        )
    if len(value) > MAX_JOB_URL_CHARS:
        raise ValidationContractError(
            f"URL must be at most {MAX_JOB_URL_CHARS} characters.",
            field=field,
            status_code=413,
        )
    if any(char.isspace() for char in value):
        raise ValidationContractError(
            "URL must not contain whitespace.",
            field=field,
        )

    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError as exc:
        raise ValidationContractError(
            "URL is malformed.",
            field=field,
        ) from exc

    if parsed.scheme.lower() not in _ALLOWED_URL_SCHEMES:
        raise ValidationContractError(
            "URL scheme must be http or https.",
            field=field,
        )
    if not parsed.hostname:
        raise ValidationContractError(
            "URL must include a host.",
            field=field,
        )
    if parsed.username is not None or parsed.password is not None:
        raise ValidationContractError(
            "URL credentials are not allowed.",
            field=field,
        )
    return value


def normalize_bulk_ids(values: Sequence[Any], *, field: str = "ids") -> NormalizedBulkIds:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ValidationContractError(
            "Bulk IDs must be a list.",
            field=field,
        )
    if not 1 <= len(values) <= MAX_BULK_IDS:
        raise ValidationContractError(
            f"Bulk IDs must contain between 1 and {MAX_BULK_IDS} entries.",
            field=field,
        )

    order: list[int] = []
    positions: dict[int, list[int]] = {}
    for index, value in enumerate(values):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValidationContractError(
                "Bulk IDs must be positive integers.",
                field=f"{field}[{index}]",
            )
        if value not in positions:
            positions[value] = []
            order.append(value)
        positions[value].append(index)

    return NormalizedBulkIds(
        ids=tuple(order),
        source_indices={
            value: tuple(source_indices)
            for value, source_indices in positions.items()
        },
    )


def require_owned_bulk_ids(
    normalized: NormalizedBulkIds,
    owned_ids: Iterable[int],
    *,
    field: str = "ids",
) -> tuple[int, ...]:
    owned = set(owned_ids)
    missing = [value for value in normalized.ids if value not in owned]
    if missing:
        first_missing = missing[0]
        source_index = normalized.source_indices[first_missing][0]
        raise ValidationContractError(
            "One or more applications were not found.",
            field=f"{field}[{source_index}]",
            code="not_found",
            status_code=404,
        )
    return normalized.ids


def legacy_invalid_application_counts(session: Any, *, user_id: int) -> dict[str, int]:
    """Return account-scoped aggregate validation warnings without exposing row data."""
    counts = {
        "total": 0,
        "invalid_status": 0,
        "applied_without_date": 0,
        "invalid_url": 0,
        "company_too_long": 0,
        "title_too_long": 0,
        "notes_too_long": 0,
    }
    query = (
        session.query(JobTrack)
        .filter(JobTrack.user_id == user_id)
        .order_by(JobTrack.id.asc())
        .yield_per(500)
    )
    for item in query:
        counts["total"] += 1
        if item.status not in STATUS_VALUES:
            counts["invalid_status"] += 1
        if item.status == "applied" and item.applied_at is None:
            counts["applied_without_date"] += 1
        try:
            validate_job_url(item.url)
        except ValidationContractError:
            counts["invalid_url"] += 1
        if item.company is not None and len(item.company) > MAX_COMPANY_TITLE_CHARS:
            counts["company_too_long"] += 1
        if item.title is not None and len(item.title) > MAX_COMPANY_TITLE_CHARS:
            counts["title_too_long"] += 1
        if item.notes is not None and len(item.notes) > MAX_NOTES_CHARS:
            counts["notes_too_long"] += 1
    return counts


def format_error_detail(
    detail: Any,
    *,
    default_code: str = "validation_error",
) -> dict[str, Any]:
    """Normalize legacy/new error details without serializing unknown payloads."""
    if isinstance(detail, Mapping):
        code = detail.get("code")
        if not isinstance(code, str) or not code:
            code = default_code

        fields = detail.get("fields")
        if isinstance(fields, list):
            normalized_fields = _normalize_field_list(fields)
            if normalized_fields:
                return {"code": code, "fields": normalized_fields}

        legacy_detail = detail.get("detail")
        if isinstance(legacy_detail, str):
            return {
                "code": code,
                "fields": [{"field": "__root__", "message": legacy_detail}],
            }

        legacy_message = detail.get("message")
        if isinstance(legacy_message, str):
            return {
                "code": code,
                "fields": [{"field": "__root__", "message": legacy_message}],
            }

        legacy_fields = [
            {"field": str(key), "message": value}
            for key, value in detail.items()
            if key not in {"code", "fields", "detail", "message"}
            and isinstance(value, str)
        ]
        if legacy_fields:
            return {"code": code, "fields": legacy_fields}

        return _generic_error_detail(code)

    if isinstance(detail, list):
        normalized_fields = _normalize_field_list(detail)
        if normalized_fields:
            return {"code": default_code, "fields": normalized_fields}
        return _generic_error_detail(default_code)

    if isinstance(detail, str):
        return {
            "code": default_code,
            "fields": [{"field": "__root__", "message": detail}],
        }

    return _generic_error_detail(default_code)


def _normalize_field_list(fields: list[Any]) -> list[dict[str, str]]:
    normalized = []
    for entry in fields:
        if not isinstance(entry, Mapping):
            continue
        field = entry.get("field")
        message = entry.get("message")
        if isinstance(field, str) and field and isinstance(message, str) and message:
            normalized.append({"field": field, "message": message})
    return normalized


def _generic_error_detail(code: str) -> dict[str, Any]:
    return {
        "code": code,
        "fields": [{"field": "__root__", "message": "Validation failed."}],
    }
