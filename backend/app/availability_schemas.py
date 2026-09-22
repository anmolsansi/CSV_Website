from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from .services.lifecycle import local_day_utc_bounds, validate_timezone_name


AVAILABILITY_STATES = frozenset({"unknown", "available", "unavailable", "closed"})
DEADLINE_SOURCES = frozenset({"user", "import"})
TERMINAL_APPLICATION_STATUSES = frozenset({"rejected", "offer", "not_applying"})
JOB_CHECK_REQUEST_RETENTION_DAYS = 7
_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class AvailabilityContractError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class DeadlineConversion:
    deadline_at: datetime
    interpretation: str
    date_only: bool


@dataclass(frozen=True)
class AvailabilityEvidence:
    state: Literal["unknown", "available", "unavailable", "closed"]
    check_reason: str


def validate_job_url(value: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > 2048:
        raise AvailabilityContractError(
            "invalid_job_url",
            "Job URL must be a non-empty HTTP(S) URL of at most 2,048 characters.",
        )
    if any(char.isspace() for char in value):
        raise AvailabilityContractError("invalid_job_url", "Job URL cannot contain whitespace.")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise AvailabilityContractError("invalid_job_url", "Job URL must use HTTP or HTTPS.")
    if parsed.username is not None or parsed.password is not None:
        raise AvailabilityContractError(
            "invalid_job_url",
            "Job URL cannot contain embedded credentials.",
        )
    return value


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def parse_deadline_input(value: str, timezone_name: str) -> DeadlineConversion:
    """Convert an explicit timestamp or account-local date-only value to stored UTC."""
    timezone_name = validate_timezone_name(timezone_name)
    if not isinstance(value, str) or not value or value != value.strip():
        raise AvailabilityContractError("invalid_deadline", "Deadline is required.")

    if _DATE_ONLY_RE.fullmatch(value):
        try:
            local_date = date.fromisoformat(value)
        except ValueError as exc:
            raise AvailabilityContractError("invalid_deadline", "Deadline date is invalid.") from exc
        zone = ZoneInfo(timezone_name)
        local_end = datetime.combine(local_date, time.max, tzinfo=zone)
        deadline_at = local_end.astimezone(timezone.utc).replace(tzinfo=None)
        return DeadlineConversion(
            deadline_at=deadline_at,
            interpretation=f"{local_date.isoformat()} 23:59:59.999999 {timezone_name}",
            date_only=True,
        )

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AvailabilityContractError(
            "invalid_deadline",
            "Deadline must be ISO-8601 with an explicit timezone, or YYYY-MM-DD.",
        ) from exc
    if parsed.tzinfo is None:
        raise AvailabilityContractError(
            "deadline_timezone_required",
            "Timestamp deadlines require an explicit timezone.",
        )
    return DeadlineConversion(
        deadline_at=parsed.astimezone(timezone.utc).replace(tzinfo=None),
        interpretation=parsed.isoformat(),
        date_only=False,
    )


def apply_checker_evidence(
    current_state: str,
    *,
    http_status: int | None = None,
    failure_reason: str | None = None,
) -> AvailabilityEvidence:
    """Map future checker evidence conservatively without overriding user closure."""
    if current_state not in AVAILABILITY_STATES:
        raise AvailabilityContractError("invalid_state", "Availability state is invalid.")
    if current_state == "closed":
        return AvailabilityEvidence("closed", "user_confirmed_closed")

    if failure_reason:
        return AvailabilityEvidence("unknown", failure_reason[:64])
    if http_status is None:
        return AvailabilityEvidence("unknown", "no_response")
    if 200 <= http_status < 300:
        return AvailabilityEvidence("available", "link_reachable")
    if http_status in {404, 410}:
        return AvailabilityEvidence("unavailable", f"http_{http_status}")
    if http_status in {403, 429}:
        return AvailabilityEvidence("unknown", f"http_{http_status}")
    return AvailabilityEvidence("unknown", f"http_{http_status}")


def deadline_today_eligible(
    *,
    deadline_at: datetime | None,
    availability_state: str,
    application_status: str | None,
    timezone_name: str,
    reference: datetime | None = None,
) -> bool:
    """Mirror Today's due-before-next-local-midnight membership for deadlines."""
    if deadline_at is None or availability_state == "closed":
        return False
    if application_status in TERMINAL_APPLICATION_STATUSES:
        return False
    if availability_state not in AVAILABILITY_STATES:
        raise AvailabilityContractError("invalid_state", "Availability state is invalid.")

    _, day_end = local_day_utc_bounds(timezone_name, reference=reference)
    return _naive_utc(deadline_at) < day_end


def check_request_retention_cutoff(reference: datetime | None = None) -> datetime:
    now = reference or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return (now.astimezone(timezone.utc) - timedelta(days=JOB_CHECK_REQUEST_RETENTION_DAYS)).replace(tzinfo=None)
