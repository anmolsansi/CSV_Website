from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Mapping
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model, model_validator

BACKUP_V2_VERSION = "2.0"
BACKUP_SCHEMA_REVISION = "2.3.0"
BACKUP_V2_SECTIONS = (
    "csv_rows",
    "url_history",
    "job_tracks",
    "lifecycle_events",
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


class JobLifecycleEventBackupV2(BackupRecordBase):
    event_key: str = Field(min_length=1, max_length=160)
    job_url: str = Field(min_length=1)
    csv_row_ref: str | None
    job_track_ref: str | None
    kind: Literal[
        "first_visited",
        "first_applied",
        "status_changed",
        "applied_date_corrected",
        "followup_changed",
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
            "status_changed": frozenset({"from", "to"}),
            "applied_date_corrected": frozenset({"from", "to"}),
            "followup_changed": frozenset({"from", "to"}),
        }
        if set(self.payload) - allowlists[self.kind]:
            raise ValueError("Lifecycle payload contains fields not allowed for its kind.")
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
    lifecycle_events: list[JobLifecycleEventBackupV2] = Field(default_factory=list)
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
    lifecycle_events: int = Field(default=0, ge=0)
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
    "archived_at", "is_duplicate", *CSV_ROW_TEXT_FIELDS
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
        **_entries(list(CSV_ROW_EXPORTED_COLUMNS), "exported", "Persisted CSV record data required for a lossless v2 record."),
    },
    "JobTrack": {
        **_entries(["id", "user_id"], "reconstructed", "Source database identity/ownership is replaced by backup_ref and authenticated user."),
        **_entries(["csv_row_id"], "reconstructed", "CsvRow relationship is represented as csv_row_ref and remapped on restore."),
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

    for event in document.sections.lifecycle_events:
        _require_target(
            refs, "csv_rows", event.csv_row_ref,
            source_section="lifecycle_events", source_ref=event.backup_ref,
        )
        _require_target(
            refs, "job_tracks", event.job_track_ref,
            source_section="lifecycle_events", source_ref=event.backup_ref,
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
    has_user_profile_section = (
        isinstance(raw_sections, Mapping) and "user_profile" in raw_sections
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
    if not has_user_profile_section:
        # Revisions 2.0.0 and 2.1.0 predate portable account timezone.
        checksum_sections.pop("user_profile", None)

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
    "lifecycle_events": JobLifecycleEventBackupV2,
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
