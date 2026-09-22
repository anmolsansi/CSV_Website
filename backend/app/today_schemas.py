from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from .availability_schemas import deadline_action_key
from .models import CsvRow, JobAvailability, JobTrack, SavedView, WorkItem


class TodayContractError(ValueError):
    """Safe domain error for Today action/source validation."""

    def __init__(self, code: str, status_code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code

    def as_detail(self) -> dict[str, str]:
        return {"code": self.code, "message": str(self)}


class StrictTodayModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def _aware_utc(value: datetime, *, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone offset.")
    return value.astimezone(timezone.utc)


def _stored_utc(value: datetime) -> datetime:
    """Normalize persisted timestamps; legacy JobTrack timestamps are naive UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def canonical_utc_timestamp(value: datetime) -> str:
    normalized = _stored_utc(value)
    return normalized.isoformat().replace("+00:00", "Z")


class WorkItemCreate(StrictTodayModel):
    description: str = Field(min_length=1, max_length=500)
    due_at: datetime | None = None
    priority: int = Field(default=1, ge=0, le=3)
    track_id: int | None = Field(default=None, gt=0)
    row_id: int | None = Field(default=None, gt=0)
    source_view_id: int | None = Field(default=None, gt=0)

    @field_validator("description", mode="before")
    @classmethod
    def trim_description(cls, value):
        if not isinstance(value, str):
            return value
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("description must contain at least one non-whitespace character.")
        return trimmed

    @field_validator("due_at")
    @classmethod
    def normalize_due_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _aware_utc(value, field_name="due_at")


class WorkItemStored(WorkItemCreate):
    state: Literal["pending", "done"] = "pending"
    version: int = Field(default=1, gt=0)
    completed_at: datetime | None = None

    @field_validator("completed_at")
    @classmethod
    def normalize_completed_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _aware_utc(value, field_name="completed_at")

    @model_validator(mode="after")
    def require_done_timestamp(self):
        if self.state == "done" and self.completed_at is None:
            raise ValueError("completed_at is required when state is done.")
        return self


class SnoozeRequest(StrictTodayModel):
    action_key: str = Field(min_length=1, max_length=255)
    until: datetime
    version: int = Field(gt=0)

    @field_validator("until")
    @classmethod
    def normalize_until(cls, value: datetime) -> datetime:
        return _aware_utc(value, field_name="until")


def manual_action_key(work_item_id: int) -> str:
    if work_item_id <= 0:
        raise ValueError("work_item_id must be positive.")
    return f"manual:{work_item_id}"


def followup_action_key(track_id: int, due_at: datetime) -> str:
    if track_id <= 0:
        raise ValueError("track_id must be positive.")
    return f"followup:{track_id}:{canonical_utc_timestamp(due_at)}"


def _owned_source(
    db: Session,
    model,
    *,
    user_id: int,
    source_id: int | None,
    name: str,
):
    if source_id is None:
        return None
    record = (
        db.query(model)
        .filter(model.id == source_id, model.user_id == user_id)
        .first()
    )
    if record is None:
        raise TodayContractError(
            "source_not_found",
            404,
            f"Owned {name} source was not found.",
        )
    return record


def validate_owned_work_item_sources(
    db: Session,
    user_id: int,
    *,
    track_id: int | None = None,
    row_id: int | None = None,
    source_view_id: int | None = None,
) -> dict[str, object | None]:
    """Resolve optional sources only inside the authenticated account boundary."""
    return {
        "track": _owned_source(
            db, JobTrack, user_id=user_id, source_id=track_id, name="application"
        ),
        "row": _owned_source(
            db, CsvRow, user_id=user_id, source_id=row_id, name="job row"
        ),
        "source_view": _owned_source(
            db, SavedView, user_id=user_id, source_id=source_view_id, name="saved view"
        ),
    }


def validate_owned_action_key(
    db: Session,
    user_id: int,
    action_key: str,
) -> tuple[Literal["manual", "followup", "deadline"], WorkItem | JobTrack | JobAvailability]:
    """Validate a server-generated action key without leaking foreign ownership."""
    if action_key.startswith("manual:"):
        raw_id = action_key.removeprefix("manual:")
        if not raw_id.isdigit() or int(raw_id) <= 0:
            raise TodayContractError("invalid_action_key", 422, "Invalid Today action key.")
        item = (
            db.query(WorkItem)
            .filter(WorkItem.id == int(raw_id), WorkItem.user_id == user_id)
            .first()
        )
        if item is None:
            raise TodayContractError("action_not_found", 404, "Today action was not found.")
        if action_key != manual_action_key(item.id):
            raise TodayContractError("invalid_action_key", 422, "Invalid Today action key.")
        return "manual", item

    if action_key.startswith("followup:"):
        parts = action_key.split(":", 2)
        if len(parts) != 3 or not parts[1].isdigit() or int(parts[1]) <= 0:
            raise TodayContractError("invalid_action_key", 422, "Invalid Today action key.")
        track = (
            db.query(JobTrack)
            .filter(JobTrack.id == int(parts[1]), JobTrack.user_id == user_id)
            .first()
        )
        if track is None or track.follow_up_at is None:
            raise TodayContractError("action_not_found", 404, "Today action was not found.")
        if action_key != followup_action_key(track.id, track.follow_up_at):
            raise TodayContractError(
                "action_not_found",
                404,
                "Today action was not found.",
            )
        return "followup", track

    if action_key.startswith("deadline:"):
        parts = action_key.split(":", 2)
        if len(parts) != 3 or not parts[1].isdigit() or int(parts[1]) <= 0:
            raise TodayContractError("invalid_action_key", 422, "Invalid Today action key.")
        availability = (
            db.query(JobAvailability)
            .filter(
                JobAvailability.id == int(parts[1]),
                JobAvailability.user_id == user_id,
            )
            .first()
        )
        if availability is None or availability.deadline_at is None:
            raise TodayContractError("action_not_found", 404, "Today action was not found.")
        if action_key != deadline_action_key(availability.id, availability.deadline_at):
            raise TodayContractError(
                "action_not_found",
                404,
                "Today action was not found.",
            )
        return "deadline", availability

    raise TodayContractError("invalid_action_key", 422, "Invalid Today action key.")
