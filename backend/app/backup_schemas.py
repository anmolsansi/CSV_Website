from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Mapping
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model, model_validator

from .evidence_schemas import (
    MAX_EVIDENCE_TEXT_CHARS,
    MAX_EVIDENCE_URL_CHARS,
    EvidenceContractError,
    validate_confirmation_url,
    validate_correction_reason,
)
from .reminder_schemas import HHMM_RE, OCCURRENCE_RE

BACKUP_V2_VERSION = "2.0"
BACKUP_SCHEMA_REVISION = "2.11.0"
BACKUP_V2_SECTIONS = (
    "csv_rows",
    "url_history",
    "job_tracks",
    "job_availability",
    "document_versions",
    "application_documents",
    "application_evidence",
    "evidence_recovery",
    "company_aliases",
    "work_items",
    "work_item_overrides",
    "lifecycle_events",
    "reminder_preferences",
    "reminder_deliveries",
    "saved_views",
    "sessions",
    "audit_events",
    "applypilot_batches",
    "column_preferences",
    "user_goal",
    "user_profile",
)
MAX_BACKUP_JSON_BYTES = 20 * 1024 * 1024
MAX_TOTAL_RECORDS = 20_000
MAX_NOTE_CHARS = 20_000
MAX_JD_TEXT_BYTES = 1024 * 1024

CSV_ROW_TEXT_FIELDS = (
    "ats_group", "location_group", "search_bucket", "title",
    "title_match_status", "title_reject_reason", "url", "display_domain",
    "company_guess", "job_id_guess", "canonical_company_job_key",
    "application_url", "application_dedupe_key",
    "page_number", "decision", "rejection_reasons",
    "posted_status", "posted_value", "posted_source", "posted_age_days",
    "location_status", "location_evidence",
    "is_usa_role", "location_country", "location_city", "location_state",
    "location_raw_extracted", "location_confidence", "location_source",
    "sponsorship_status", "positive_sponsorship_matches",
    "negative_sponsorship_matches", "sponsorship_evidence_snippet",
    "positive_sponsorship_evidence_snippet",
    "clearance_matches", "clearance_evidence_snippet",
    "jd_quality_status", "jd_quality_reasons",
    "jd_text_length", "jd_text",
    "extraction_method", "retry_attempted", "error", "source_file",
    "work_model_extracted",
    "salary_min_extracted", "salary_max_extracted", "salary_currency_extracted",
    "posted_status_extracted", "posted_value_extracted",
    "posted_source_extracted", "posted_age_days_extracted",
    "sponsorship_status_extracted",
    "positive_sponsorship_matches_extracted",
    "negative_sponsorship_matches_extracted",
    "positive_sponsorship_evidence_extracted",
    "negative_sponsorship_evidence_extracted",
    "clearance_or_citizenship_extracted",
    "clearance_or_citizenship_evidence_extracted",
    "education_requirement_extracted", "employment_type_extracted",
    "resume_match_score", "resume_score", "fit_category",
    "score_confidence", "role_family", "seniority_level", "required_years_min",
    "core_languages_extracted", "core_frameworks_extracted",
    "core_cloud_devops_extracted", "database_requirements_extracted",
    "ai_ml_requirements_extracted",
    "matched_resume_skills", "missing_or_weaker_skills", "score_reason",
    "closed_or_unusable_jd", "closed_or_unusable_reason",
)


class BackupContractError(ValueError):
    """Stable domain error that route code can map to an HTTP response."""

    def __init__(
        self,
        code: str,
        status_code: int,
        message: str,
        *,
        section: str | None = None,
        backup_ref: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.section = section
        self.backup_ref = backup_ref

    def as_detail(self) -> dict[str, Any]:
        detail: dict[str, Any] = {"code": self.code, "message": str(self)}
        if self.section is not None:
            detail["section"] = self.section
        if self.backup_ref is not None:
            detail["backup_ref"] = self.backup_ref
        return detail


class StrictBackupModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class BackupRecordBase(StrictBackupModel):
    backup_ref: str = Field(min_length=1)


_csv_dynamic_fields: dict[str, tuple[Any, Any]] = {
    name: ((str if name == "url" else str | None), (... if name == "url" else ...))
    for name in CSV_ROW_TEXT_FIELDS
}
CsvRowBackupV2 = create_model(
    "CsvRowBackupV2",
    __base__=BackupRecordBase,
    __module__=__name__,
    upload_batch_id=(str, ...),
    created_at=(str | None, ...),
    clicked=(bool, ...),
    clicked_at=(str | None, ...),
    archived=(bool, ...),
    # Optional default keeps older v2 payloads valid while new exports carry
    # the explicit archive timestamp.
    archived_at=(str | None, None),
    # JG-045 capture provenance is additive. Defaults preserve pre-2.10 backups.
    capture_source=(Literal["manual", "bookmarklet"] | None, None),
    captured_at=(str | None, None),
    capture_notes=(str | None, Field(default=None, max_length=MAX_NOTE_CHARS)),
    is_duplicate=(bool, ...),
    duplicate_of_ref=(str | None, ...),
    **_csv_dynamic_fields,
)


class UrlHistoryBackupV2(BackupRecordBase):
    url: str
    first_seen_at: str


class JobTrackBackupV2(BackupRecordBase):
    csv_row_ref: str | None
    url: str
    company: str | None
    title: str | None
    ats_group: str | None
    search_bucket: str | None
    resume_match_score: str | None
    status: str
    opened_at: str | None
    applied_at: str | None
    follow_up_at: str | None
    notes: str | None
    session_id: str | None
    session_ref: str | None
    open_count: int
    last_opened_at: str | None
    created_at: str
    updated_at: str


class JobAvailabilityBackupV2(BackupRecordBase):
    job_url: str = Field(min_length=1, max_length=2048)
    deadline_at: str | None = None
    deadline_source: Literal["user", "import"] | None = None
    state: Literal["unknown", "available", "unavailable", "closed"] = "unknown"
    last_checked_at: str | None = None
    check_reason: str | None = Field(default=None, max_length=64)
    confirmed_closed_at: str | None = None
    version: int = Field(default=1, gt=0)

    @model_validator(mode="after")
    def validate_closed_confirmation(self):
        if self.state == "closed" and self.confirmed_closed_at is None:
            raise ValueError("Closed availability requires confirmed_closed_at.")
        if self.state != "closed" and self.confirmed_closed_at is not None:
            raise ValueError("Only user-confirmed closed availability may carry confirmed_closed_at.")
        if self.deadline_at is None and self.deadline_source is not None:
            raise ValueError("deadline_source requires deadline_at.")
        return self


class DocumentVersionBackupV2(BackupRecordBase):
    document_family_id: str = Field(min_length=36, max_length=36)
    kind: Literal["resume", "cover_letter"]
    label: str = Field(min_length=1, max_length=150)
    original_filename: str = Field(min_length=1, max_length=255)
    media_type: Literal["application/pdf", "text/plain"]
    size_bytes: int = Field(ge=0, le=10 * 1024 * 1024)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    version_number: int = Field(gt=0)
    created_at: str
    state: Literal["pending", "ready", "failed", "deleted"]


class ApplicationDocumentBackupV2(BackupRecordBase):
    track_ref: str
    document_ref: str
    kind: Literal["resume", "cover_letter"]
    usage: Literal["used", "reference"]
    attached_at: str


class ApplicationEvidenceBackupV2(BackupRecordBase):
    track_ref: str
    kind: Literal["confirmation_url", "confirmation_text", "note"]
    body: str | None
    occurred_at: str | None
    created_at: str
    updated_at: str
    version: int = Field(gt=0)
    is_deleted: bool

    @model_validator(mode="after")
    def validate_evidence_body(self):
        if self.is_deleted:
            if self.body is not None:
                raise ValueError(
                    "Deleted evidence body belongs only in evidence_recovery."
                )
            return self
        if self.body is None or not self.body.strip():
            raise ValueError("Active evidence requires a non-empty body.")
        if self.kind == "confirmation_url":
            if len(self.body) > MAX_EVIDENCE_URL_CHARS:
                raise ValueError("Confirmation URL exceeds 2048 characters.")
            try:
                validate_confirmation_url(self.body)
            except EvidenceContractError as exc:
                raise ValueError(exc.message) from exc
        elif len(self.body) > MAX_EVIDENCE_TEXT_CHARS:
            raise ValueError("Evidence text exceeds 20,000 characters.")
        return self


class EvidenceRecoveryBackupV2(BackupRecordBase):
    """Explicit recovery-only copy of a recently soft-deleted private body."""

    evidence_ref: str
    body: str = Field(min_length=1, max_length=MAX_EVIDENCE_TEXT_CHARS)
    body_purge_at: str


class CompanyAliasBackupV2(BackupRecordBase):
    alias_key: str = Field(min_length=1, max_length=320)
    display_name: str = Field(min_length=1, max_length=320)
    company_key: str = Field(min_length=36, max_length=36)
    created_at: str

    @model_validator(mode="after")
    def validate_company_key(self):
        try:
            UUID(self.company_key)
        except ValueError as exc:
            raise ValueError("company_key must be a UUID.") from exc
        return self


class WorkItemBackupV2(BackupRecordBase):
    track_ref: str | None
    row_ref: str | None
    source_view_ref: str | None
    origin_key: str | None = Field(default=None, max_length=255)
    description: str = Field(min_length=1, max_length=500)
    due_at: str | None
    priority: int = Field(ge=0, le=3)
    state: Literal["pending", "done"]
    version: int = Field(gt=0)
    created_at: str
    updated_at: str
    completed_at: str | None

    @model_validator(mode="after")
    def validate_work_item_state(self):
        if self.description != self.description.strip():
            raise ValueError("Work-item description must be trimmed.")
        if self.state == "done" and self.completed_at is None:
            raise ValueError("completed_at is required when state is done.")
        return self


class WorkItemOverrideBackupV2(BackupRecordBase):
    kind: Literal["manual", "followup"]
    work_item_ref: str | None = None
    track_ref: str | None = None
    follow_up_due_at: str | None = None
    snoozed_until: str
    version: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_override_target(self):
        _validate_utc_timestamp(
            self.snoozed_until,
            field_name="work_item_overrides.snoozed_until",
        )
        if self.kind == "manual":
            if self.work_item_ref is None or self.track_ref is not None or self.follow_up_due_at is not None:
                raise ValueError("Manual override requires exactly work_item_ref.")
        else:
            if self.track_ref is None or self.work_item_ref is not None or self.follow_up_due_at is None:
                raise ValueError("Follow-up override requires track_ref and follow_up_due_at.")
            _validate_utc_timestamp(
                self.follow_up_due_at,
                field_name="work_item_overrides.follow_up_due_at",
            )
        return self


class JobLifecycleEventBackupV2(BackupRecordBase):
    event_key: str = Field(min_length=1, max_length=160)
    job_url: str = Field(min_length=1)
    csv_row_ref: str | None
    job_track_ref: str | None
    evidence_ref: str | None = None
    correction_of_ref: str | None = None
    kind: Literal[
        "first_visited",
        "first_applied",
        "status_changed",
        "applied_date_corrected",
        "followup_changed",
        "evidence_added",
        "evidence_edited",
        "evidence_deleted",
    ]
    occurred_at: str
    recorded_at: str
    source: str = Field(min_length=1, max_length=32)
    payload: dict[str, Any]

    @model_validator(mode="after")
    def validate_payload_allowlist(self):
        allowlists = {
            "first_visited": frozenset(),
            "first_applied": frozenset(),
            "status_changed": frozenset({"from", "to", "reason"}),
            "applied_date_corrected": frozenset({"from", "to", "reason"}),
            "followup_changed": frozenset({"from", "to"}),
            # evidence_id is represented by portable evidence_ref in backups.
            "evidence_added": frozenset({"evidence_kind"}),
            "evidence_edited": frozenset({"evidence_kind", "version"}),
            "evidence_deleted": frozenset({"evidence_kind", "version"}),
        }
        if set(self.payload) - allowlists[self.kind]:
            raise ValueError("Lifecycle payload contains fields not allowed for its kind.")

        is_evidence = self.kind in {
            "evidence_added", "evidence_edited", "evidence_deleted"
        }
        if is_evidence:
            if self.evidence_ref is None:
                raise ValueError("Evidence lifecycle events require evidence_ref.")
            if self.payload.get("evidence_kind") not in {
                "confirmation_url", "confirmation_text", "note"
            }:
                raise ValueError("Evidence lifecycle event has invalid evidence_kind.")
            if self.kind in {"evidence_edited", "evidence_deleted"}:
                version = self.payload.get("version")
                if (
                    not isinstance(version, int)
                    or isinstance(version, bool)
                    or version < 1
                ):
                    raise ValueError("Edited/deleted evidence event requires version.")
        elif self.evidence_ref is not None:
            raise ValueError("Only evidence lifecycle events may carry evidence_ref.")

        reason = self.payload.get("reason")
        if reason is not None:
            try:
                validate_correction_reason(reason)
            except EvidenceContractError as exc:
                raise ValueError(exc.message) from exc
        if self.kind == "status_changed" and (
            self.correction_of_ref is not None or reason is not None
        ):
            if self.correction_of_ref is None or reason is None:
                raise ValueError(
                    "Status correction requires correction_of_ref and bounded reason."
                )
        elif self.correction_of_ref is not None:
            raise ValueError(
                "Only status_changed correction events may carry correction_of_ref."
            )
        return self


class ReminderPreferenceBackupV2(BackupRecordBase):
    enabled: bool
    channel: Literal["in_app", "email"]
    local_time: str
    quiet_start: str
    quiet_end: str

    @model_validator(mode="after")
    def validate_reminder_times(self):
        for value in (self.local_time, self.quiet_start, self.quiet_end):
            if HHMM_RE.fullmatch(value) is None:
                raise ValueError("Reminder times must use 24-hour HH:MM format.")
        return self


class ReminderDeliveryBackupV2(BackupRecordBase):
    track_ref: str | None
    occurrence_key: str = Field(min_length=1, max_length=255)
    channel: Literal["in_app", "email"]
    status: Literal["pending", "sending", "sent", "failed", "unknown", "cancelled"]
    scheduled_at: str
    attempt_count: int = Field(ge=0)
    next_attempt_at: str | None
    sent_at: str | None
    # Added in backup schema 2.8.0. Default None preserves 2.7.0 payloads and
    # their original checksum shape during validation.
    read_at: str | None = None
    last_error_code: str | None = Field(default=None, max_length=64)
    version: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_delivery_history(self):
        if OCCURRENCE_RE.fullmatch(self.occurrence_key) is None:
            raise ValueError("Reminder occurrence key does not match the frozen F4 format.")
        if self.status == "sent" and self.sent_at is None:
            raise ValueError("Sent reminder delivery requires sent_at.")
        if self.status != "sent" and self.sent_at is not None:
            raise ValueError("Only sent reminder delivery may carry sent_at.")
        return self


class SavedViewBackupV2(BackupRecordBase):
    name: str
    view_type: str
    filters: dict[str, Any]
    is_pinned: bool
    created_at: str


class SearchSessionBackupV2(BackupRecordBase):
    name: str
    started_at: str
    ended_at: str | None
    notes: str | None


class ColumnPreferenceBackupV2(BackupRecordBase):
    hidden_columns: list[str]
    column_order: list[str]


class AuditEventBackupV2(BackupRecordBase):
    session_ref: str | None
    event_type: str
    entity_type: str
    entity_ref: str | None
    legacy_entity_id: int | None
    metadata_json: dict[str, Any] | None
    created_at: str


class ApplyPilotBatchBackupV2(BackupRecordBase):
    session_ref: str | None
    name: str | None
    payload_json: Any
    status: str
    job_count: int
    created_at: str
    updated_at: str | None


class UserGoalBackupV2(BackupRecordBase):
    open_per_day: int | None
    apply_per_day: int | None
    followup_per_day: int | None
    applypilot_per_day: int | None


class UserProfileBackupV2(BackupRecordBase):
    timezone: str = Field(min_length=1, max_length=64)
    # Missing/null remains valid for v2 backups produced before JG-012.
    retention_days: int | None = None

    @model_validator(mode="after")
    def validate_profile_preferences(self):
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("timezone must be a valid IANA timezone name.") from exc

        if (
            self.retention_days is not None
            and self.retention_days != 0
            and not 7 <= self.retention_days <= 3650
        ):
            raise ValueError(
                "retention_days must be 0 (disabled) or between 7 and 3650 days."
            )
        return self


class BackupSectionsV2(StrictBackupModel):
    csv_rows: list[CsvRowBackupV2]
    url_history: list[UrlHistoryBackupV2]
    job_tracks: list[JobTrackBackupV2]
    job_availability: list[JobAvailabilityBackupV2] = Field(default_factory=list)
    document_versions: list[DocumentVersionBackupV2] = Field(default_factory=list)
    application_documents: list[ApplicationDocumentBackupV2] = Field(default_factory=list)
    application_evidence: list[ApplicationEvidenceBackupV2] = Field(default_factory=list)
    evidence_recovery: list[EvidenceRecoveryBackupV2] = Field(default_factory=list)
    company_aliases: list[CompanyAliasBackupV2] = Field(default_factory=list)
    work_items: list[WorkItemBackupV2] = Field(default_factory=list)
    work_item_overrides: list[WorkItemOverrideBackupV2] = Field(default_factory=list)
    lifecycle_events: list[JobLifecycleEventBackupV2] = Field(default_factory=list)
    reminder_preferences: list[ReminderPreferenceBackupV2] = Field(default_factory=list, max_length=1)
    reminder_deliveries: list[ReminderDeliveryBackupV2] = Field(default_factory=list)
    saved_views: list[SavedViewBackupV2]
    sessions: list[SearchSessionBackupV2]
    audit_events: list[AuditEventBackupV2]
    applypilot_batches: list[ApplyPilotBatchBackupV2]
    column_preferences: list[ColumnPreferenceBackupV2]
    user_goal: list[UserGoalBackupV2]
    user_profile: list[UserProfileBackupV2] = Field(default_factory=list, max_length=1)


class BackupCountsV2(StrictBackupModel):
    csv_rows: int = Field(ge=0)
    url_history: int = Field(ge=0)
    job_tracks: int = Field(ge=0)
    job_availability: int = Field(default=0, ge=0)
    document_versions: int = Field(default=0, ge=0)
    application_documents: int = Field(default=0, ge=0)
    application_evidence: int = Field(default=0, ge=0)
    evidence_recovery: int = Field(default=0, ge=0)
    company_aliases: int = Field(default=0, ge=0)
    work_items: int = Field(default=0, ge=0)
    work_item_overrides: int = Field(default=0, ge=0)
    lifecycle_events: int = Field(default=0, ge=0)
    reminder_preferences: int = Field(default=0, ge=0)
    reminder_deliveries: int = Field(default=0, ge=0)
    saved_views: int = Field(ge=0)
    sessions: int = Field(ge=0)
    audit_events: int = Field(ge=0)
    applypilot_batches: int = Field(ge=0)
    column_preferences: int = Field(ge=0)
    user_goal: int = Field(ge=0)
    user_profile: int = Field(default=0, ge=0)


class BackupDocumentV2(StrictBackupModel):
    version: Literal["2.0"]
    backup_id: str
    exported_at: str
    schema_revision: str = Field(min_length=1)
    identity_rule_version: str | None = None
    document_bytes_included: Literal[False] = False
    sections: BackupSectionsV2
    counts: BackupCountsV2
    checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class FieldInventoryEntry:
    disposition: Literal["exported", "reconstructed", "excluded", "migration_blocker"]
    reason: str


def _entries(
    names: tuple[str, ...] | list[str],
    disposition: Literal["exported", "reconstructed", "excluded", "migration_blocker"],
    reason: str,
) -> dict[str, FieldInventoryEntry]:
    return {name: FieldInventoryEntry(disposition, reason) for name in names}


CSV_ROW_EXPORTED_COLUMNS = (
    "upload_batch_id", "created_at", "clicked", "clicked_at", "archived",
    "archived_at", "capture_source", "captured_at", "capture_notes",
    "is_duplicate", *CSV_ROW_TEXT_FIELDS
)

MODEL_FIELD_INVENTORY: dict[str, dict[str, FieldInventoryEntry]] = {
    "User": {
        **_entries(
            ["id", "email", "created_at"],
            "excluded",
            "User/account identity is not portable backup data; restore is owned by the authenticated destination user.",
        ),
        **_entries(
            ["timezone", "retention_days"],
            "exported",
            "Account timezone and retention policy are portable user preferences; authentication identity remains excluded.",
        ),
    },
    "OAuthIdentity": _entries(
        ["id", "user_id", "provider", "provider_id", "created_at"],
        "excluded",
        "Authentication identities and provider credentials/identifiers are intentionally excluded.",
    ),
    "UrlHistory": {
        **_entries(["id", "user_id"], "reconstructed", "Destination identity/ownership is allocated from backup_ref and authenticated user."),
        **_entries(["url", "first_seen_at"], "exported", "Durable user history required for a complete portable backup."),
    },
    "CsvRow": {
        **_entries(["id", "user_id"], "reconstructed", "Source database identity/ownership is replaced by backup_ref and authenticated user."),
        **_entries(["duplicate_of_id"], "reconstructed", "Cross-row identity is represented as duplicate_of_ref and remapped on restore."),
        **_entries(
            ["capture_source", "captured_at", "capture_notes"],
            "exported",
            "Manual/bookmarklet capture provenance and bounded draft notes are durable portable row data.",
        ),
        **_entries(
            ["canonical_url", "canonical_url_hash"],
            "reconstructed",
            "Derived identity is rebuilt from the preserved original URL using the recorded identity rule version.",
        ),
        **_entries(list(CSV_ROW_EXPORTED_COLUMNS), "exported", "Persisted CSV record data required for a lossless v2 record."),
    },
    "JobTrack": {
        **_entries(["id", "user_id"], "reconstructed", "Source database identity/ownership is replaced by backup_ref and authenticated user."),
        **_entries(["csv_row_id"], "reconstructed", "CsvRow relationship is represented as csv_row_ref and remapped on restore."),
        **_entries(
            ["canonical_url", "canonical_url_hash"],
            "reconstructed",
            "Derived identity is rebuilt from the preserved original URL using the recorded identity rule version.",
        ),
        **_entries(
            [
                "url", "company", "title", "ats_group", "search_bucket",
                "resume_match_score", "status", "opened_at", "applied_at",
                "follow_up_at", "notes", "session_id", "open_count",
                "last_opened_at", "created_at", "updated_at",
            ],
            "exported",
            "Persisted application-memory data required for a lossless v2 record; session_id remains a scalar Text value.",
        ),
    },

    "JobAvailability": {
        **_entries(
            ["id", "user_id"],
            "reconstructed",
            "Destination identity/ownership is allocated from backup_ref and the authenticated user.",
        ),
        **_entries(
            [
                "job_url", "deadline_at", "deadline_source", "state",
                "last_checked_at", "check_reason", "confirmed_closed_at", "version",
            ],
            "exported",
            "URL-scoped deadline and availability evidence is durable portable user data independent of CSV source rows.",
        ),
    },
    "JobCheckRequest": _entries(
        [
            "id", "user_id", "availability_id", "requested_at", "status",
            "lease_until", "completed_at", "error_code",
        ],
        "excluded",
        "Seven-day check request, lease, and rate metadata is transient operational state and is intentionally excluded from portable backups.",
    ),
    "DocumentVersion": {
        **_entries(
            ["id", "user_id"],
            "reconstructed",
            "Document database identity/ownership is represented by backup_ref and the authenticated user.",
        ),
        **_entries(
            [
                "document_family_id", "kind", "label", "original_filename",
                "media_type", "size_bytes", "sha256", "version_number",
                "created_at", "state",
            ],
            "exported",
            "Immutable document metadata and checksum are portable; file bytes remain excluded until JG-044.",
        ),
        **_entries(
            ["storage_key"],
            "excluded",
            "Private storage keys are environment-local implementation details and never portable user data.",
        ),
    },
    "ApplicationDocument": {
        **_entries(
            ["id", "user_id"],
            "reconstructed",
            "Association identity/ownership is represented by backup_ref and the authenticated user.",
        ),
        **_entries(
            ["track_id", "document_version_id"],
            "reconstructed",
            "Application and document identities are represented as portable references.",
        ),
        **_entries(
            ["kind", "usage", "attached_at"],
            "exported",
            "Used/reference attachment semantics are portable metadata.",
        ),
    },
    "DocumentCreateReceipt": _entries(
        ["id", "user_id", "request_key", "payload_hash", "document_id", "status", "created_at"],
        "excluded",
        "Short-lived upload idempotency receipts are operational replay state, not portable user content.",
    ),
    "CaptureRequest": _entries(
        ["id", "user_id", "request_key", "payload_hash", "row_id", "created_at"],
        "excluded",
        "Thirty-day capture replay receipts are operational idempotency state and are intentionally reconstructed by future requests rather than exported.",
    ),
    "RequestWindowCounter": _entries(
        ["id", "user_id", "scope", "window_start", "count"],
        "excluded",
        "Forty-eight-hour abuse counters are operational rate-limit state and are intentionally excluded from portable user backups.",
    ),
    "ApplicationEvidence": {
        **_entries(
            ["id", "user_id"],
            "reconstructed",
            "Destination identity/ownership is allocated from backup_ref and the authenticated user.",
        ),
        **_entries(
            ["track_id"],
            "reconstructed",
            "Application identity is represented as track_ref and remapped on restore.",
        ),
        **_entries(
            ["kind", "body", "occurred_at", "created_at", "updated_at", "version", "is_deleted"],
            "exported",
            "Evidence metadata is portable; a deleted private body is redacted from the ordinary section and exported only in the bounded recovery section.",
        ),
    },
    "EvidenceCreateReceipt": _entries(
        ["id", "user_id", "request_key", "payload_hash", "evidence_id", "created_at"],
        "excluded",
        "Short-lived create idempotency receipts are operational replay state, not portable user content.",
    ),
    "CompanyAlias": {
        **_entries(
            ["id", "user_id"],
            "reconstructed",
            "Destination identity/ownership is allocated from backup_ref and the authenticated user.",
        ),
        **_entries(
            ["alias_key", "display_name", "company_key", "created_at"],
            "exported",
            "Explicit owner-local alias grouping is durable portable user data.",
        ),
    },
    "JobLifecycleEvent": {
        **_entries(["id", "user_id"], "reconstructed", "Destination identity/ownership is allocated from backup_ref and authenticated user."),
        **_entries(["csv_row_id"], "reconstructed", "CSV-row identity is represented as csv_row_ref and remapped on restore."),
        **_entries(["job_track_id"], "reconstructed", "Application identity is represented as job_track_ref and remapped on restore."),
        **_entries(
            ["event_key", "job_url", "kind", "occurred_at", "recorded_at", "source", "payload"],
            "exported",
            "Durable lifecycle facts are portable user data and preserve original occurrence time.",
        ),
    },
    "ReminderPreference": {
        **_entries(
            ["user_id"],
            "reconstructed",
            "Ownership is always the authenticated destination user.",
        ),
        **_entries(
            ["enabled", "channel", "local_time", "quiet_start", "quiet_end"],
            "exported",
            "Reminder opt-in and local scheduling preferences are portable; restore forces enabled=false until explicit re-enable.",
        ),
    },
    "ReminderDelivery": {
        **_entries(
            ["id", "user_id"],
            "reconstructed",
            "Destination identity/ownership is allocated from backup_ref and authenticated user.",
        ),
        **_entries(
            ["track_id"],
            "reconstructed",
            "Application identity is represented as track_ref and remapped on restore.",
        ),
        **_entries(
            [
                "occurrence_key", "channel", "status", "scheduled_at",
                "attempt_count", "next_attempt_at", "sent_at", "read_at",
                "last_error_code", "version",
            ],
            "exported",
            "Durable delivery history is portable; occurrence keys are remapped to destination track IDs and retry timing is paused on restore.",
        ),
        **_entries(
            ["lease_until"],
            "excluded",
            "Worker leases are environment-local operational claim state and are cleared on restore.",
        ),
    },
    "SavedView": {
        **_entries(["id", "user_id"], "reconstructed", "Source database identity/ownership is replaced by backup_ref and authenticated user."),
        **_entries(["name", "view_type", "filters", "is_pinned", "created_at"], "exported", "Durable saved-view state is portable user data."),
    },
    "SearchSession": {
        **_entries(["id", "user_id"], "reconstructed", "Source database identity/ownership is replaced by backup_ref and authenticated user."),
        **_entries(["name", "started_at", "ended_at", "notes"], "exported", "Durable search-session state is portable user data."),
    },
    "ColumnPreference": {
        **_entries(["user_id"], "reconstructed", "Ownership is always the authenticated destination user."),
        **_entries(["hidden_columns", "column_order"], "exported", "Durable UI preferences are portable user data."),
    },
    "AuditEvent": {
        **_entries(["id", "user_id"], "reconstructed", "Source database identity/ownership is replaced by backup_ref and authenticated user."),
        **_entries(["session_id"], "reconstructed", "Session identity is represented as session_ref and remapped on restore."),
        **_entries(["entity_id"], "reconstructed", "Typed entity identity is represented as entity_ref; legacy numeric identity is historical metadata only."),
        **_entries(["event_type", "entity_type", "metadata_json", "created_at"], "exported", "Durable audit history is portable user data."),
    },
    "ApplyPilotBatch": {
        **_entries(["id", "user_id"], "reconstructed", "Source database identity/ownership is replaced by backup_ref and authenticated user."),
        **_entries(["session_id"], "reconstructed", "Session identity is represented as session_ref and remapped on restore."),
        **_entries(["name", "payload_json", "status", "job_count", "created_at", "updated_at"], "exported", "Durable batch history is portable user data."),
    },
    "UserGoal": {
        **_entries(["user_id"], "reconstructed", "Ownership is always the authenticated destination user."),
        **_entries(["open_per_day", "apply_per_day", "followup_per_day", "applypilot_per_day"], "exported", "Durable goal preferences are portable user data."),
    },

    "WorkItem": {
        **_entries(
            ["id", "user_id"],
            "reconstructed",
            "Destination identity/ownership is allocated from backup_ref and authenticated user.",
        ),
        **_entries(
            ["track_id"],
            "reconstructed",
            "Application identity is represented as track_ref and remapped on restore.",
        ),
        **_entries(
            ["row_id"],
            "reconstructed",
            "CSV-row identity is represented as row_ref and remapped on restore.",
        ),
        **_entries(
            ["source_view_id"],
            "reconstructed",
            "Saved-view identity is represented as source_view_ref and remapped on restore.",
        ),
        **_entries(
            [
                "origin_key", "description", "due_at", "priority", "state",
                "version", "created_at", "updated_at", "completed_at",
            ],
            "exported",
            "Durable manual Today actions are portable user data.",
        ),
    },
    "WorkItemOverride": {
        **_entries(
            ["user_id", "action_key"],
            "reconstructed",
            "Ownership is the authenticated user and action keys are regenerated from remapped destination IDs.",
        ),
        **_entries(
            ["snoozed_until", "version"],
            "exported",
            "Durable per-action snooze state is portable user data.",
        ),
    },
    "MaintenanceStatus": _entries(
        [
            "job_name",
            "outcome",
            "last_attempted_at",
            "last_successful_at",
            "last_failed_at",
            "result_json",
            "updated_at",
        ],
        "excluded",
        "Operational worker health is environment state, not portable user data.",
    ),
}


def inventory_gaps(model_classes: Mapping[str, Any]) -> dict[str, dict[str, set[str]]]:
    """Return missing/stale inventory fields. Empty result means the schema is still frozen to ORM columns."""
    gaps: dict[str, dict[str, set[str]]] = {}
    for model_name, model in model_classes.items():
        actual = {column.name for column in model.__table__.columns}
        frozen = set(MODEL_FIELD_INVENTORY.get(model_name, {}))
        missing = actual - frozen
        stale = frozen - actual
        if missing or stale:
            gaps[model_name] = {"missing": missing, "stale": stale}
    unknown_models = set(MODEL_FIELD_INVENTORY) - set(model_classes)
    for model_name in unknown_models:
        gaps[model_name] = {"missing": set(), "stale": set(MODEL_FIELD_INVENTORY[model_name])}
    return gaps


def canonical_json_bytes(value: Any) -> bytes:
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise BackupContractError("invalid_json_value", 400, "Backup contains a value that cannot be canonically serialized.") from exc
    return text.encode("utf-8")


def compute_sections_checksum(sections: BackupSectionsV2 | Mapping[str, Any]) -> str:
    if isinstance(sections, BaseModel):
        value = sections.model_dump(mode="json", exclude_none=False)
    else:
        value = dict(sections)
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BackupContractError("duplicate_json_key", 400, f"Duplicate JSON object key: {key}")
        result[key] = value
    return result


def _reject_non_finite(token: str) -> None:
    raise BackupContractError("non_finite_number", 400, f"Non-finite JSON number is not allowed: {token}")


def parse_backup_json(raw: bytes | str) -> Any:
    if isinstance(raw, bytes):
        if len(raw) > MAX_BACKUP_JSON_BYTES:
            raise BackupContractError("backup_too_large", 413, "Backup JSON exceeds the 20 MiB uncompressed limit.")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise BackupContractError("invalid_json", 400, "Backup must be UTF-8 JSON.") from exc
    else:
        text = raw
        if len(text.encode("utf-8")) > MAX_BACKUP_JSON_BYTES:
            raise BackupContractError("backup_too_large", 413, "Backup JSON exceeds the 20 MiB uncompressed limit.")

    try:
        return json.loads(
            text,
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_non_finite,
        )
    except BackupContractError:
        raise
    except (json.JSONDecodeError, TypeError) as exc:
        raise BackupContractError("invalid_json", 400, "Backup is not valid JSON.") from exc


def _validate_utc_timestamp(value: str | None, *, field_name: str) -> None:
    if value is None:
        return
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BackupContractError("invalid_timestamp", 400, f"{field_name} must be an ISO-8601 UTC timestamp.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise BackupContractError("invalid_timestamp", 400, f"{field_name} must include a UTC offset.")


def _validate_timestamp_fields(document: BackupDocumentV2) -> None:
    _validate_utc_timestamp(document.exported_at, field_name="exported_at")
    for section_name in BACKUP_V2_SECTIONS:
        for record in getattr(document.sections, section_name):
            for field_name, value in record.model_dump(mode="python").items():
                if field_name.endswith("_at") and value is not None:
                    _validate_utc_timestamp(value, field_name=f"{section_name}.{field_name}")


def _validate_ref_uniqueness(document: BackupDocumentV2) -> dict[str, set[str]]:
    refs: dict[str, set[str]] = {}
    for section_name in BACKUP_V2_SECTIONS:
        seen: set[str] = set()
        for record in getattr(document.sections, section_name):
            if record.backup_ref in seen:
                raise BackupContractError(
                    "duplicate_backup_ref",
                    409,
                    "backup_ref must be unique within its section.",
                    section=section_name,
                    backup_ref=record.backup_ref,
                )
            seen.add(record.backup_ref)
        refs[section_name] = seen
    return refs


def _require_target(
    refs: dict[str, set[str]],
    section: str,
    backup_ref: str | None,
    *,
    source_section: str,
    source_ref: str,
) -> None:
    if backup_ref is None:
        return
    if backup_ref not in refs[section]:
        raise BackupContractError(
            "conflicting_reference_graph",
            409,
            f"Reference target does not exist in section {section}.",
            section=source_section,
            backup_ref=source_ref,
        )


AUDIT_ENTITY_SECTION = {
    "csv_row": "csv_rows",
    "job_track": "job_tracks",
    "search_session": "sessions",
    "session": "sessions",
    "saved_view": "saved_views",
    "applypilot_batch": "applypilot_batches",
    "url_history": "url_history",
}


def _validate_reference_graph(document: BackupDocumentV2, refs: dict[str, set[str]]) -> None:
    for row in document.sections.csv_rows:
        _require_target(refs, "csv_rows", row.duplicate_of_ref, source_section="csv_rows", source_ref=row.backup_ref)
        if row.duplicate_of_ref == row.backup_ref:
            raise BackupContractError(
                "conflicting_reference_graph", 409, "A CSV row cannot duplicate itself.",
                section="csv_rows", backup_ref=row.backup_ref,
            )

    for track in document.sections.job_tracks:
        _require_target(refs, "csv_rows", track.csv_row_ref, source_section="job_tracks", source_ref=track.backup_ref)
        _require_target(refs, "sessions", track.session_ref, source_section="job_tracks", source_ref=track.backup_ref)


    for link in document.sections.application_documents:
        _require_target(
            refs, "job_tracks", link.track_ref,
            source_section="application_documents", source_ref=link.backup_ref,
        )
        _require_target(
            refs, "document_versions", link.document_ref,
            source_section="application_documents", source_ref=link.backup_ref,
        )

    for evidence in document.sections.application_evidence:
        _require_target(
            refs, "job_tracks", evidence.track_ref,
            source_section="application_evidence", source_ref=evidence.backup_ref,
        )

    evidence_by_ref = {
        evidence.backup_ref: evidence
        for evidence in document.sections.application_evidence
    }
    for recovery in document.sections.evidence_recovery:
        _require_target(
            refs, "application_evidence", recovery.evidence_ref,
            source_section="evidence_recovery", source_ref=recovery.backup_ref,
        )
        evidence = evidence_by_ref[recovery.evidence_ref]
        if not evidence.is_deleted:
            raise BackupContractError(
                "conflicting_reference_graph",
                409,
                "Recovery body may target only soft-deleted evidence.",
                section="evidence_recovery",
                backup_ref=recovery.backup_ref,
            )
        if evidence.kind == "confirmation_url":
            try:
                validate_confirmation_url(recovery.body)
            except EvidenceContractError as exc:
                raise BackupContractError(
                    "invalid_schema", 400, exc.message,
                    section="evidence_recovery", backup_ref=recovery.backup_ref,
                ) from exc
        updated_at = datetime.fromisoformat(
            evidence.updated_at.replace("Z", "+00:00")
        )
        purge_at = datetime.fromisoformat(
            recovery.body_purge_at.replace("Z", "+00:00")
        )
        if purge_at > updated_at + timedelta(days=30):
            raise BackupContractError(
                "invalid_schema",
                400,
                "Evidence recovery deadline cannot extend beyond 30 days after deletion.",
                section="evidence_recovery",
                backup_ref=recovery.backup_ref,
            )

    for item in document.sections.work_items:
        _require_target(
            refs, "job_tracks", item.track_ref,
            source_section="work_items", source_ref=item.backup_ref,
        )
        _require_target(
            refs, "csv_rows", item.row_ref,
            source_section="work_items", source_ref=item.backup_ref,
        )
        _require_target(
            refs, "saved_views", item.source_view_ref,
            source_section="work_items", source_ref=item.backup_ref,
        )

    for override in document.sections.work_item_overrides:
        if override.kind == "manual":
            _require_target(
                refs, "work_items", override.work_item_ref,
                source_section="work_item_overrides", source_ref=override.backup_ref,
            )
        else:
            _require_target(
                refs, "job_tracks", override.track_ref,
                source_section="work_item_overrides", source_ref=override.backup_ref,
            )

    lifecycle_positions = {
        event.backup_ref: index
        for index, event in enumerate(document.sections.lifecycle_events)
    }
    for index, event in enumerate(document.sections.lifecycle_events):
        _require_target(
            refs, "csv_rows", event.csv_row_ref,
            source_section="lifecycle_events", source_ref=event.backup_ref,
        )
        _require_target(
            refs, "job_tracks", event.job_track_ref,
            source_section="lifecycle_events", source_ref=event.backup_ref,
        )
        _require_target(
            refs, "application_evidence", event.evidence_ref,
            source_section="lifecycle_events", source_ref=event.backup_ref,
        )
        _require_target(
            refs, "lifecycle_events", event.correction_of_ref,
            source_section="lifecycle_events", source_ref=event.backup_ref,
        )
        if (
            event.correction_of_ref is not None
            and lifecycle_positions[event.correction_of_ref] >= index
        ):
            raise BackupContractError(
                "conflicting_reference_graph",
                409,
                "Correction events must reference an earlier lifecycle event.",
                section="lifecycle_events",
                backup_ref=event.backup_ref,
            )

    for delivery in document.sections.reminder_deliveries:
        _require_target(
            refs, "job_tracks", delivery.track_ref,
            source_section="reminder_deliveries", source_ref=delivery.backup_ref,
        )

    for event in document.sections.audit_events:
        _require_target(refs, "sessions", event.session_ref, source_section="audit_events", source_ref=event.backup_ref)
        if event.entity_ref is not None:
            target_section = AUDIT_ENTITY_SECTION.get(event.entity_type)
            if target_section is None:
                raise BackupContractError(
                    "conflicting_reference_graph",
                    409,
                    "Unknown audit entity types must remain detached from active references.",
                    section="audit_events",
                    backup_ref=event.backup_ref,
                )
            _require_target(refs, target_section, event.entity_ref, source_section="audit_events", source_ref=event.backup_ref)

    for batch in document.sections.applypilot_batches:
        _require_target(refs, "sessions", batch.session_ref, source_section="applypilot_batches", source_ref=batch.backup_ref)


def _validate_counts_and_limits(document: BackupDocumentV2) -> None:
    total = 0
    for section_name in BACKUP_V2_SECTIONS:
        records = getattr(document.sections, section_name)
        actual = len(records)
        expected = getattr(document.counts, section_name)
        if actual != expected:
            raise BackupContractError(
                "count_mismatch",
                400,
                f"counts.{section_name} does not match the section record count.",
                section=section_name,
            )
        total += actual
    if total > MAX_TOTAL_RECORDS:
        raise BackupContractError("record_limit_exceeded", 413, "Backup contains more than 20,000 records.")

    for row in document.sections.csv_rows:
        if row.jd_text is not None and len(row.jd_text.encode("utf-8")) > MAX_JD_TEXT_BYTES:
            raise BackupContractError(
                "field_too_large", 413, "jd_text exceeds the 1 MiB UTF-8 limit.",
                section="csv_rows", backup_ref=row.backup_ref,
            )
    for section_name, records in (
        ("job_tracks", document.sections.job_tracks),
        ("sessions", document.sections.sessions),
    ):
        for record in records:
            if record.notes is not None and len(record.notes) > MAX_NOTE_CHARS:
                raise BackupContractError(
                    "field_too_large", 413, "notes exceeds the 20,000 character limit.",
                    section=section_name, backup_ref=record.backup_ref,
                )


def validate_backup_v2(raw: bytes | str | Mapping[str, Any]) -> BackupDocumentV2:
    """Parse and fully validate v2 before any ORM object is constructed."""
    payload = parse_backup_json(raw) if isinstance(raw, (bytes, str)) else dict(raw)
    raw_sections = payload.get("sections")
    has_lifecycle_section = (
        isinstance(raw_sections, Mapping) and "lifecycle_events" in raw_sections
    )
    has_application_evidence_section = (
        isinstance(raw_sections, Mapping) and "application_evidence" in raw_sections
    )
    has_document_versions_section = (
        isinstance(raw_sections, Mapping) and "document_versions" in raw_sections
    )
    has_application_documents_section = (
        isinstance(raw_sections, Mapping) and "application_documents" in raw_sections
    )
    has_evidence_recovery_section = (
        isinstance(raw_sections, Mapping) and "evidence_recovery" in raw_sections
    )
    has_company_aliases_section = (
        isinstance(raw_sections, Mapping) and "company_aliases" in raw_sections
    )
    has_work_items_section = (
        isinstance(raw_sections, Mapping) and "work_items" in raw_sections
    )
    has_work_item_overrides_section = (
        isinstance(raw_sections, Mapping) and "work_item_overrides" in raw_sections
    )
    has_user_profile_section = (
        isinstance(raw_sections, Mapping) and "user_profile" in raw_sections
    )
    has_reminder_preferences_section = (
        isinstance(raw_sections, Mapping) and "reminder_preferences" in raw_sections
    )
    has_reminder_deliveries_section = (
        isinstance(raw_sections, Mapping) and "reminder_deliveries" in raw_sections
    )
    try:
        document = BackupDocumentV2.model_validate(payload)
    except ValidationError as exc:
        raise BackupContractError("invalid_schema", 400, "Backup does not match the frozen v2 schema.") from exc

    try:
        UUID(document.backup_id)
    except ValueError as exc:
        raise BackupContractError("invalid_backup_id", 400, "backup_id must be a UUID.") from exc

    _validate_timestamp_fields(document)
    _validate_counts_and_limits(document)
    refs = _validate_ref_uniqueness(document)
    _validate_reference_graph(document, refs)

    checksum_sections = document.sections.model_dump(mode="json", exclude_none=False)
    if not has_lifecycle_section:
        # Revision 2.0.0 predates the additive lifecycle section.
        checksum_sections.pop("lifecycle_events", None)
    if not has_application_evidence_section:
        # Revisions before JG-033 predate application evidence.
        checksum_sections.pop("application_evidence", None)
    if not has_document_versions_section:
        # Revisions before JG-041 predate document metadata.
        checksum_sections.pop("document_versions", None)
    if not has_application_documents_section:
        # Revisions before JG-041 predate application/document associations.
        checksum_sections.pop("application_documents", None)
    if not has_evidence_recovery_section:
        # Revisions before JG-033 predate the explicit deleted-body recovery section.
        checksum_sections.pop("evidence_recovery", None)
    if not has_company_aliases_section:
        # Revisions before JG-030 predate owner-local company aliases.
        checksum_sections.pop("company_aliases", None)
    if not has_work_items_section:
        # Revisions before JG-025 predate durable manual Today actions.
        checksum_sections.pop("work_items", None)
    if not has_work_item_overrides_section:
        # Revisions before JG-025 predate durable Today snooze overrides.
        checksum_sections.pop("work_item_overrides", None)
    if not has_user_profile_section:
        # Revisions 2.0.0 and 2.1.0 predate portable account timezone.
        checksum_sections.pop("user_profile", None)
    if not has_reminder_preferences_section:
        # Revisions before JG-037 predate durable reminder preferences.
        checksum_sections.pop("reminder_preferences", None)
    if not has_reminder_deliveries_section:
        # Revisions before JG-037 predate durable reminder delivery history.
        checksum_sections.pop("reminder_deliveries", None)

    # Preserve the exact canonical shape of older v2 documents. Pydantic fills
    # the new nullable JG-012 fields with None for runtime compatibility, but
    # those keys did not exist when older checksums were produced.
    raw_csv_rows = (
        raw_sections.get("csv_rows", [])
        if isinstance(raw_sections, Mapping)
        else []
    )
    for index, raw_record in enumerate(raw_csv_rows):
        if (
            isinstance(raw_record, Mapping)
            and "archived_at" not in raw_record
            and index < len(checksum_sections.get("csv_rows", []))
        ):
            checksum_sections["csv_rows"][index].pop("archived_at", None)
        if isinstance(raw_record, Mapping) and index < len(checksum_sections.get("csv_rows", [])):
            for additive_field in ("capture_source", "captured_at", "capture_notes"):
                if additive_field not in raw_record:
                    checksum_sections["csv_rows"][index].pop(additive_field, None)

    raw_lifecycle = (
        raw_sections.get("lifecycle_events", [])
        if isinstance(raw_sections, Mapping)
        else []
    )
    for index, raw_record in enumerate(raw_lifecycle):
        if (
            isinstance(raw_record, Mapping)
            and "evidence_ref" not in raw_record
            and index < len(checksum_sections.get("lifecycle_events", []))
        ):
            checksum_sections["lifecycle_events"][index].pop("evidence_ref", None)
        if (
            isinstance(raw_record, Mapping)
            and "correction_of_ref" not in raw_record
            and index < len(checksum_sections.get("lifecycle_events", []))
        ):
            checksum_sections["lifecycle_events"][index].pop("correction_of_ref", None)

    raw_profiles = (
        raw_sections.get("user_profile", [])
        if isinstance(raw_sections, Mapping)
        else []
    )
    for index, raw_record in enumerate(raw_profiles):
        if (
            isinstance(raw_record, Mapping)
            and "retention_days" not in raw_record
            and index < len(checksum_sections.get("user_profile", []))
        ):
            checksum_sections["user_profile"][index].pop("retention_days", None)

    raw_reminder_deliveries = (
        raw_sections.get("reminder_deliveries", [])
        if isinstance(raw_sections, Mapping)
        else []
    )
    for index, raw_record in enumerate(raw_reminder_deliveries):
        if (
            isinstance(raw_record, Mapping)
            and "read_at" not in raw_record
            and index < len(checksum_sections.get("reminder_deliveries", []))
        ):
            # Schema 2.7.0 predates persisted in-app read state. Pydantic fills
            # the additive field for runtime compatibility, but old checksums
            # were calculated without the key.
            checksum_sections["reminder_deliveries"][index].pop("read_at", None)

    expected_checksum = compute_sections_checksum(checksum_sections)
    if document.checksum_sha256 != expected_checksum:
        raise BackupContractError("invalid_checksum", 400, "Backup checksum does not match canonical sections JSON.")
    return document


@dataclass(frozen=True)
class LegacyV1Record:
    data: dict[str, Any]
    missing_fields: frozenset[str]


@dataclass(frozen=True)
class LegacyV1Adaptation:
    version: str
    exported_at: str | None
    sections: dict[str, tuple[LegacyV1Record, ...]]
    absent_sections: frozenset[str]
    warnings: tuple[str, ...]


SECTION_RECORD_MODELS: dict[str, type[BaseModel]] = {
    "csv_rows": CsvRowBackupV2,
    "url_history": UrlHistoryBackupV2,
    "job_tracks": JobTrackBackupV2,
    "document_versions": DocumentVersionBackupV2,
    "application_documents": ApplicationDocumentBackupV2,
    "application_evidence": ApplicationEvidenceBackupV2,
    "evidence_recovery": EvidenceRecoveryBackupV2,
    "company_aliases": CompanyAliasBackupV2,
    "work_items": WorkItemBackupV2,
    "work_item_overrides": WorkItemOverrideBackupV2,
    "lifecycle_events": JobLifecycleEventBackupV2,
    "reminder_preferences": ReminderPreferenceBackupV2,
    "reminder_deliveries": ReminderDeliveryBackupV2,
    "saved_views": SavedViewBackupV2,
    "sessions": SearchSessionBackupV2,
    "audit_events": AuditEventBackupV2,
    "applypilot_batches": ApplyPilotBatchBackupV2,
    "column_preferences": ColumnPreferenceBackupV2,
    "user_goal": UserGoalBackupV2,
    "user_profile": UserProfileBackupV2,
}


def adapt_v1_backup(payload: Mapping[str, Any]) -> LegacyV1Adaptation:
    """Preserve known v1 values and record loss explicitly instead of fabricating v2 history."""
    version = str(payload.get("version", ""))
    if version not in {"1", "1.0"}:
        raise BackupContractError("unsupported_backup_version", 400, "Legacy adapter only accepts backup version 1/1.0.")
    if "user_id" in payload:
        raise BackupContractError("ownership_field_forbidden", 400, "Legacy backup must not provide user_id ownership.")

    adapted: dict[str, tuple[LegacyV1Record, ...]] = {}
    absent_sections: set[str] = set()
    warnings: list[str] = ["incomplete_legacy_backup"]

    for section_name in BACKUP_V2_SECTIONS:
        raw_records = payload.get(section_name)
        if raw_records is None:
            raw_records = []
            absent_sections.add(section_name)
        if not isinstance(raw_records, list):
            raise BackupContractError("invalid_legacy_schema", 400, f"Legacy section {section_name} must be a list.")

        model_fields = set(SECTION_RECORD_MODELS[section_name].model_fields)
        records: list[LegacyV1Record] = []
        for raw_record in raw_records:
            if not isinstance(raw_record, dict):
                raise BackupContractError("invalid_legacy_schema", 400, f"Legacy section {section_name} contains a non-object record.")
            if "user_id" in raw_record:
                raise BackupContractError("ownership_field_forbidden", 400, "Legacy records must not provide user_id ownership.")
            data = dict(raw_record)
            missing = frozenset(sorted(model_fields - set(data)))
            records.append(LegacyV1Record(data=data, missing_fields=missing))
        adapted[section_name] = tuple(records)

    return LegacyV1Adaptation(
        version=version,
        exported_at=payload.get("exported_at") if isinstance(payload.get("exported_at"), str) else None,
        sections=adapted,
        absent_sections=frozenset(absent_sections),
        warnings=tuple(warnings),
    )
