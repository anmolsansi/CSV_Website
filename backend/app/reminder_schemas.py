from __future__ import annotations

import re
from datetime import date, datetime, time, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, field_validator


HHMM_RE = re.compile(r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
OCCURRENCE_RE = re.compile(
    r"^track:(?P<track_id>[1-9][0-9]*):due:(?P<due>[^:]+T[^:]+:[^:]+Z):date:(?P<local_date>[0-9]{4}-[0-9]{2}-[0-9]{2})$"
)

REMINDER_CHANNELS = frozenset({"in_app", "email"})
REMINDER_DELIVERY_STATUSES = frozenset(
    {"pending", "sending", "sent", "failed", "unknown", "cancelled"}
)

LEGAL_DELIVERY_TRANSITIONS = {
    "pending": frozenset({"sending", "cancelled"}),
    "sending": frozenset({"sent", "failed", "unknown", "cancelled"}),
    "sent": frozenset(),
    "failed": frozenset({"sending", "cancelled"}),
    "unknown": frozenset(),
    "cancelled": frozenset(),
}


class ReminderContractError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class StrictReminderModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ReminderPreferenceData(StrictReminderModel):
    enabled: bool = False
    channel: Literal["in_app", "email"] = "in_app"
    local_time: str = "09:00"
    quiet_start: str = "21:00"
    quiet_end: str = "08:00"

    @field_validator("local_time", "quiet_start", "quiet_end")
    @classmethod
    def validate_hhmm(cls, value: str) -> str:
        if not HHMM_RE.fullmatch(value):
            raise ValueError("Time must use 24-hour HH:MM format.")
        return value


def validate_timezone_name(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ReminderContractError(
            "invalid_timezone",
            "Reminder scheduling requires a valid IANA account timezone.",
        ) from exc


def parse_local_time(value: str) -> time:
    if not HHMM_RE.fullmatch(value):
        raise ReminderContractError(
            "invalid_local_time",
            "Reminder times must use 24-hour HH:MM format.",
        )
    hour, minute = value.split(":")
    return time(hour=int(hour), minute=int(minute))


def is_quiet_local_time(
    value: time,
    *,
    quiet_start: str,
    quiet_end: str,
) -> bool:
    """Return whether a local wall-clock time falls in the quiet interval.

    Equal start/end explicitly means no quiet period.
    """

    start = parse_local_time(quiet_start)
    end = parse_local_time(quiet_end)
    if start == end:
        return False
    if start < end:
        return start <= value < end
    return value >= start or value < end


def validate_preference_for_timezone(
    data: ReminderPreferenceData,
    timezone_name: str,
) -> ReminderPreferenceData:
    validate_timezone_name(timezone_name)
    return data


def _utc_key_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ReminderContractError(
            "naive_occurrence_time",
            "Reminder occurrence due time must be timezone-aware.",
        )
    utc = value.astimezone(timezone.utc).replace(microsecond=0)
    return utc.isoformat().replace("+00:00", "Z")


def reminder_occurrence_key(
    *,
    track_id: int,
    due_at: datetime,
    notification_local_date: date,
) -> str:
    if track_id <= 0:
        raise ReminderContractError(
            "invalid_track_id",
            "Reminder occurrence requires a positive track ID.",
        )
    return (
        f"track:{track_id}:due:{_utc_key_timestamp(due_at)}:"
        f"date:{notification_local_date.isoformat()}"
    )


def remap_reminder_occurrence_key(value: str, *, track_id: int) -> str:
    match = OCCURRENCE_RE.fullmatch(value)
    if match is None:
        raise ReminderContractError(
            "invalid_occurrence_key",
            "Reminder occurrence key does not match the frozen F4 format.",
        )
    return (
        f"track:{track_id}:due:{match.group('due')}:"
        f"date:{match.group('local_date')}"
    )


def apply_delivery_transition(
    delivery: Any,
    new_status: str,
    *,
    sent_at: datetime | None = None,
    explicit_unknown_retry: bool = False,
) -> None:
    current = str(delivery.status)
    if current not in REMINDER_DELIVERY_STATUSES or new_status not in REMINDER_DELIVERY_STATUSES:
        raise ReminderContractError(
            "invalid_delivery_status",
            "Reminder delivery status is invalid.",
        )

    if current == new_status:
        if current == "sent" and sent_at is not None and delivery.sent_at != sent_at:
            raise ReminderContractError(
                "sent_at_immutable",
                "sent_at cannot change after provider acceptance.",
            )
        return

    if current == "unknown" and new_status == "pending" and explicit_unknown_retry:
        if delivery.sent_at is not None:
            raise ReminderContractError(
                "sent_at_immutable",
                "Unknown delivery cannot carry an accepted sent_at timestamp.",
            )
    elif new_status not in LEGAL_DELIVERY_TRANSITIONS[current]:
        raise ReminderContractError(
            "illegal_delivery_transition",
            f"Reminder delivery cannot transition from {current} to {new_status}.",
        )

    if current == "sent" or delivery.sent_at is not None:
        raise ReminderContractError(
            "sent_at_immutable",
            "Accepted reminder delivery is immutable.",
        )

    if new_status == "sent":
        if sent_at is None:
            raise ReminderContractError(
                "sent_at_required",
                "sent_at is required when a delivery becomes sent.",
            )
        if sent_at.tzinfo is None:
            raise ReminderContractError(
                "sent_at_timezone_required",
                "sent_at must be timezone-aware.",
            )
        delivery.sent_at = sent_at
    elif sent_at is not None:
        raise ReminderContractError(
            "sent_at_not_allowed",
            "sent_at is only valid for an accepted sent delivery.",
        )

    delivery.status = new_status
    delivery.version = int(delivery.version or 0) + 1
