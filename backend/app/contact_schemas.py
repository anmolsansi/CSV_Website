from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator


CONTACT_ROLES = {"recruiter", "referrer", "interviewer", "other"}
INTERVIEW_KINDS = {"phone", "video", "onsite", "other"}
INTERVIEW_STATUSES = {"scheduled", "completed", "cancelled"}
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class ContactContractError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def validate_optional_email(value: str | None) -> str | None:
    if value in {None, ""}:
        return None
    if value != value.strip() or len(value) > 320 or not _EMAIL_RE.fullmatch(value):
        raise ContactContractError("invalid_email", "Email must be a valid address of at most 320 characters.")
    return value


def validate_optional_http_url(value: str | None, *, field_name: str) -> str | None:
    if value in {None, ""}:
        return None
    if value != value.strip() or len(value) > 2048 or any(char.isspace() for char in value):
        raise ContactContractError(f"invalid_{field_name}", f"{field_name.replace('_', ' ').title()} must be an HTTP(S) URL of at most 2,048 characters.")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username is not None or parsed.password is not None:
        raise ContactContractError(f"invalid_{field_name}", f"{field_name.replace('_', ' ').title()} must use HTTP or HTTPS and cannot contain credentials.")
    return value


def validate_timezone(value: str) -> str:
    if not value or value != value.strip() or len(value) > 64:
        raise ContactContractError("invalid_timezone", "Timezone must be a valid IANA timezone name.")
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ContactContractError("invalid_timezone", "Timezone must be a valid IANA timezone name.") from exc
    return value


def parse_utc_instant(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ContactContractError("timezone_required", "Interview timestamps require an explicit timezone offset.")
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def validate_interview_window(starts_at: datetime, ends_at: datetime) -> tuple[datetime, datetime]:
    starts = parse_utc_instant(starts_at)
    ends = parse_utc_instant(ends_at)
    if ends <= starts:
        raise ContactContractError("invalid_interview_range", "Interview end must be after the start.")
    if (ends - starts).total_seconds() > 24 * 60 * 60:
        raise ContactContractError("interview_too_long", "Interview duration cannot exceed 24 hours.")
    return starts, ends


class ContactCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    profile_url: str | None = Field(default=None, max_length=2048)
    company_display: str | None = Field(default=None, max_length=300)
    notes: str | None = Field(default=None, max_length=20000)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name is required.")
        return value

    @field_validator("email")
    @classmethod
    def email_contract(cls, value):
        try:
            return validate_optional_email(value)
        except ContactContractError as exc:
            raise ValueError(exc.message) from exc

    @field_validator("profile_url")
    @classmethod
    def profile_contract(cls, value):
        try:
            return validate_optional_http_url(value, field_name="profile_url")
        except ContactContractError as exc:
            raise ValueError(exc.message) from exc


class ContactPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: StrictInt = Field(gt=0)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    profile_url: str | None = Field(default=None, max_length=2048)
    company_display: str | None = Field(default=None, max_length=300)
    notes: str | None = Field(default=None, max_length=20000)

    @model_validator(mode="after")
    def require_change(self):
        if len(self.model_fields_set - {"version"}) == 0:
            raise ValueError("At least one contact field must change.")
        return self

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Name cannot be empty.")
        return value

    @field_validator("email")
    @classmethod
    def email_contract(cls, value):
        try:
            return validate_optional_email(value)
        except ContactContractError as exc:
            raise ValueError(exc.message) from exc

    @field_validator("profile_url")
    @classmethod
    def profile_contract(cls, value):
        try:
            return validate_optional_http_url(value, field_name="profile_url")
        except ContactContractError as exc:
            raise ValueError(exc.message) from exc


class ApplicationContactCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contact_id: StrictInt = Field(gt=0)
    role: Literal["recruiter", "referrer", "interviewer", "other"]
    referral_source: str | None = Field(default=None, max_length=300)


class InterviewCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contact_id: StrictInt | None = Field(default=None, gt=0)
    starts_at: datetime
    ends_at: datetime
    timezone: str = Field(min_length=1, max_length=64)
    kind: Literal["phone", "video", "onsite", "other"]
    meeting_url: str | None = Field(default=None, max_length=2048)
    location: str | None = Field(default=None, max_length=500)
    status: Literal["scheduled", "completed", "cancelled"] = "scheduled"
    notes: str | None = Field(default=None, max_length=20000)
    round_label: str | None = Field(default=None, max_length=100)
    preparation_notes: str | None = Field(default=None, max_length=20000)

    @field_validator("timezone")
    @classmethod
    def timezone_contract(cls, value):
        try:
            return validate_timezone(value)
        except ContactContractError as exc:
            raise ValueError(exc.message) from exc

    @field_validator("meeting_url")
    @classmethod
    def meeting_url_contract(cls, value):
        try:
            return validate_optional_http_url(value, field_name="meeting_url")
        except ContactContractError as exc:
            raise ValueError(exc.message) from exc

    @model_validator(mode="after")
    def range_contract(self):
        try:
            validate_interview_window(self.starts_at, self.ends_at)
        except ContactContractError as exc:
            raise ValueError(exc.message) from exc
        return self


class InterviewPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: StrictInt = Field(gt=0)
    contact_id: StrictInt | None = Field(default=None, gt=0)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    kind: Literal["phone", "video", "onsite", "other"] | None = None
    meeting_url: str | None = Field(default=None, max_length=2048)
    location: str | None = Field(default=None, max_length=500)
    status: Literal["scheduled", "completed", "cancelled"] | None = None
    notes: str | None = Field(default=None, max_length=20000)
    round_label: str | None = Field(default=None, max_length=100)
    preparation_notes: str | None = Field(default=None, max_length=20000)

    @model_validator(mode="after")
    def require_change(self):
        if len(self.model_fields_set - {"version"}) == 0:
            raise ValueError("At least one interview field must change.")
        return self

    @field_validator("timezone")
    @classmethod
    def timezone_contract(cls, value):
        if value is None:
            return None
        try:
            return validate_timezone(value)
        except ContactContractError as exc:
            raise ValueError(exc.message) from exc

    @field_validator("meeting_url")
    @classmethod
    def meeting_url_contract(cls, value):
        try:
            return validate_optional_http_url(value, field_name="meeting_url")
        except ContactContractError as exc:
            raise ValueError(exc.message) from exc
