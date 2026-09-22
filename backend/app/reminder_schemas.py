from __future__ import annotations

import re
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, model_validator


ReminderChannel = Literal["in_app", "email"]
ReminderDeliveryStatus = Literal[
    "pending",
    "sending",
    "sent",
    "failed",
    "unknown",
    "cancelled",
]

DEFAULT_REMINDER_LOCAL_TIME = "09:00"
DEFAULT_QUIET_START = "21:00"
DEFAULT_QUIET_END = "08:00"
MAX_OCCURRENCE_KEY_CHARS = 255
MAX_ERROR_CODE_CHARS = 64

_HHMM_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")

LEGAL_DELIVERY_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"sending", "cancelled"}),
    "sending": frozenset({"sent", "failed", "unknown", "cancelled"}),
    "failed": frozenset({"pending", "cancelled"}),
    # Unknown acceptance is quarantined. A later explicit user action may
    # deliberately place it back into pending with a duplicate-delivery warning.
    "unknown": frozenset(),
    "sent": frozenset(),
    "cancelled": frozenset(),
}


class ReminderContractError(ValueError):
    def __init__(self, code: str, message: str, *, field: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field


def validate_hhmm(value: str, *, field: str) -> str:
    if not isinstance(value, str) or _HHMM_RE.fullmatch(value) is None:
        raise ReminderContractError(
            "invalid_local_time",
            f"{field} must use 24-hour HH:MM format.",
            field=field,
        )
    return value


def validate_timezone_name(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ReminderContractError(
            "invalid_timezone",
            "Account timezone must be a valid IANA timezone name.",
            field="timezone",
        )
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ReminderContractError(
            "invalid_timezone",
            "Account timezone must be a valid IANA timezone name.",
            field="timezone",
        ) from exc
    return value


def _minutes(value: str, *, field: str) -> int:
    checked = validate_hhmm(value, field=field)
    hour, minute = checked.split(":")
    return int(hour) * 60 + int(minute)


def is_quiet_local_time(
    local_time: str,
    *,
    quiet_start: str,
    quiet_end: str,
) -> bool:
    """Return whether a local wall-clock time is inside configured quiet hours.

    Equal quiet start/end intentionally means no quiet period. Overnight ranges
    such as 21:00-08:00 wrap across local midnight.
    """
    value = _minutes(local_time, field="local_time")
    start = _minutes(quiet_start, field="quiet_start")
    end = _minutes(quiet_end, field="quiet_end")
    if start == end:
        return False
    if start < end:
        return start <= value < end
    return value >= start or value < end


class ReminderPreferenceData(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    enabled: bool = False
    channel: ReminderChannel = "in_app"
    local_time: str = DEFAULT_REMINDER_LOCAL_TIME
    quiet_start: str = DEFAULT_QUIET_START
    quiet_end: str = DEFAULT_QUIET_END

    @model_validator(mode="after")
    def validate_times(self):
        validate_hhmm(self.local_time, field="local_time")
        validate_hhmm(self.quiet_start, field="quiet_start")
        validate_hhmm(self.quiet_end, field="quiet_end")
        return self


def validate_preference_for_timezone(
    preference: ReminderPreferenceData,
    *,
    timezone_name: str,
) -> ReminderPreferenceData:
    validate_timezone_name(timezone_name)
    # Exercise quiet-hour parsing too so the full preference is validated
    # before a later API or worker persists/uses it.
    is_quiet_local_time(
        preference.local_time,
        quiet_start=preference.quiet_start,
        quiet_end=preference.quiet_end,
    )
    return preference


def validate_occurrence_key(value: str) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or len(value) > MAX_OCCURRENCE_KEY_CHARS
    ):
        raise ReminderContractError(
            "invalid_occurrence_key",
            "occurrence_key must contain 1 to 255 trimmed characters.",
            field="occurrence_key",
        )
    return value


def validate_error_code(value: str | None) -> str | None:
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or len(value) > MAX_ERROR_CODE_CHARS
    ):
        raise ReminderContractError(
            "invalid_error_code",
            "last_error_code must contain 1 to 64 trimmed characters.",
            field="last_error_code",
        )
    return value


def validate_delivery_transition(
    current_status: ReminderDeliveryStatus,
    target_status: ReminderDeliveryStatus,
    *,
    current_sent_at: datetime | None,
    target_sent_at: datetime | None,
    allow_unknown_retry: bool = False,
) -> ReminderDeliveryStatus:
    """Validate the persisted state-machine edge and sent timestamp contract.

    Unknown delivery is never retried automatically. A future deliberate retry
    path may pass allow_unknown_retry=True to move unknown -> pending while
    presenting the duplicate-delivery warning required by CCR-REMINDERS-1.
    """
    known = set(LEGAL_DELIVERY_TRANSITIONS)
    if current_status not in known or target_status not in known:
        raise ReminderContractError(
            "invalid_delivery_status",
            "Reminder delivery status is invalid.",
            field="status",
        )

    if current_sent_at is not None and target_sent_at != current_sent_at:
        raise ReminderContractError(
            "sent_at_immutable",
            "sent_at cannot change after provider acceptance.",
            field="sent_at",
        )

    if target_status == "sent":
        if target_sent_at is None:
            raise ReminderContractError(
                "sent_at_required",
                "sent_at is required when delivery status becomes sent.",
                field="sent_at",
            )
    elif target_sent_at is not None:
        raise ReminderContractError(
            "sent_at_without_acceptance",
            "sent_at is only valid for confirmed sent delivery.",
            field="sent_at",
        )

    if current_status == target_status:
        return target_status

    if current_status == "unknown" and target_status == "pending":
        if allow_unknown_retry:
            return target_status
        raise ReminderContractError(
            "unknown_retry_requires_explicit_action",
            "Unknown delivery may be retried only by an explicit user action.",
            field="status",
        )

    if target_status not in LEGAL_DELIVERY_TRANSITIONS[current_status]:
        raise ReminderContractError(
            "illegal_delivery_transition",
            f"Reminder delivery cannot transition from {current_status} to {target_status}.",
            field="status",
        )
    return target_status
