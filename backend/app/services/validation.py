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
