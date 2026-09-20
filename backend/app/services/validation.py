from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel

from ..models import JOB_TRACK_STATUS_VALUES

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
