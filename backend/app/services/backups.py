from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4, uuid5

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..backup_schemas import (
    AUDIT_ENTITY_SECTION,
    BACKUP_SCHEMA_REVISION,
    BACKUP_V2_SECTIONS,
    CSV_ROW_TEXT_FIELDS,
    BackupContractError,
    BackupDocumentV2,
    adapt_v1_backup,
    canonical_json_bytes,
    compute_sections_checksum,
    parse_backup_json,
    validate_backup_v2,
)
from ..models import (
    ApplicationDocument,
    ApplicationEvidence,
    ApplyPilotBatch,
    AuditEvent,
    BackupImportMap,
    ColumnPreference,
    CompanyAlias,
    CsvRow,
    DocumentVersion,
    JobTrack,
    JobLifecycleEvent,
    ReminderDelivery,
    ReminderPreference,
    SavedView,
    SearchSession,
    UrlHistory,
    User,
    UserGoal,
    WorkItem,
    WorkItemOverride,
)
from ..today_schemas import followup_action_key, manual_action_key
from ..reminder_schemas import remap_reminder_occurrence_key
from ..evidence_schemas import (
    evidence_body_is_recoverable,
    evidence_body_purge_at,
)
from .job_identity import CANONICALIZATION_VERSION, apply_persisted_job_identity


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def _backup_ref(backup_id: UUID, section: str, source_key: str | int) -> str:
    """Opaque, deterministic within one backup document and section."""
    return str(uuid5(backup_id, f"{section}:{source_key}"))


def _required_ref(
    ref_map: dict[int, str],
    source_id: int | None,
    *,
    section: str,
    backup_ref: str,
) -> str | None:
    if source_id is None:
        return None
    target = ref_map.get(source_id)
    if target is None:
        raise BackupContractError(
            "conflicting_reference_graph",
            409,
            "Export contains a relationship target outside the authenticated backup snapshot.",
            section=section,
            backup_ref=backup_ref,
        )
    return target


def _query_snapshot(session: Session, user_id: int) -> dict[str, list[Any]]:
    evidence = (
        session.query(ApplicationEvidence)
        .filter(ApplicationEvidence.user_id == user_id)
        .order_by(ApplicationEvidence.id.asc())
        .all()
    )
    recoverable_evidence = [
        item
        for item in evidence
        if evidence_body_is_recoverable(
            is_deleted=item.is_deleted,
            body=item.body,
            updated_at=item.updated_at,
        )
    ]
    return {
        "csv_rows": session.query(CsvRow).filter(CsvRow.user_id == user_id).order_by(CsvRow.id.asc()).all(),
        "url_history": session.query(UrlHistory).filter(UrlHistory.user_id == user_id).order_by(UrlHistory.id.asc()).all(),
        "job_tracks": session.query(JobTrack).filter(JobTrack.user_id == user_id).order_by(JobTrack.id.asc()).all(),
        "document_versions": session.query(DocumentVersion).filter(DocumentVersion.user_id == user_id).order_by(DocumentVersion.created_at.asc(), DocumentVersion.id.asc()).all(),
        "application_documents": session.query(ApplicationDocument).filter(ApplicationDocument.user_id == user_id).order_by(ApplicationDocument.id.asc()).all(),
        "application_evidence": evidence,
        "evidence_recovery": recoverable_evidence,
        "company_aliases": session.query(CompanyAlias).filter(CompanyAlias.user_id == user_id).order_by(CompanyAlias.id.asc()).all(),
        "work_items": session.query(WorkItem).filter(WorkItem.user_id == user_id).order_by(WorkItem.id.asc()).all(),
        "work_item_overrides": session.query(WorkItemOverride).filter(WorkItemOverride.user_id == user_id).order_by(WorkItemOverride.action_key.asc()).all(),
        "lifecycle_events": session.query(JobLifecycleEvent).filter(JobLifecycleEvent.user_id == user_id).order_by(JobLifecycleEvent.id.asc()).all(),
        "reminder_preferences": session.query(ReminderPreference).filter(ReminderPreference.user_id == user_id).all(),
        "reminder_deliveries": session.query(ReminderDelivery).filter(ReminderDelivery.user_id == user_id).order_by(ReminderDelivery.id.asc()).all(),
        "saved_views": session.query(SavedView).filter(SavedView.user_id == user_id).order_by(SavedView.id.asc()).all(),
        "sessions": session.query(SearchSession).filter(SearchSession.user_id == user_id).order_by(SearchSession.id.asc()).all(),
        "audit_events": session.query(AuditEvent).filter(AuditEvent.user_id == user_id).order_by(AuditEvent.id.asc()).all(),
        "applypilot_batches": session.query(ApplyPilotBatch).filter(ApplyPilotBatch.user_id == user_id).order_by(ApplyPilotBatch.id.asc()).all(),
        "column_preferences": session.query(ColumnPreference).filter(ColumnPreference.user_id == user_id).all(),
        "user_goal": session.query(UserGoal).filter(UserGoal.user_id == user_id).all(),
        "user_profile": session.query(User).filter(User.id == user_id).all(),
    }


def _ref_maps(snapshot: dict[str, list[Any]], backup_id: UUID) -> dict[str, dict[Any, str]]:
    refs: dict[str, dict[Any, str]] = {}
    for section in BACKUP_V2_SECTIONS:
        section_refs: dict[Any, str] = {}
        for item in snapshot[section]:
            if section == "work_item_overrides":
                source_key = item.action_key
            else:
                source_key = getattr(item, "id", getattr(item, "user_id", None))
            if source_key is None:
                raise BackupContractError(
                    "invalid_export_identity",
                    409,
                    "A record in the export snapshot has no stable source identity.",
                    section=section,
                )
            section_refs[source_key] = _backup_ref(backup_id, section, source_key)
        refs[section] = section_refs
    return refs


def _portable_work_item_origin_key(
    item: WorkItem,
    refs: dict[str, dict[Any, str]],
) -> str | None:
    if item.origin_key is None:
        return None
    if item.source_view_id is not None and item.row_id is not None:
        expected = f"view:{item.source_view_id}:row:{item.row_id}"
        if item.origin_key == expected:
            return (
                f"view:{refs['saved_views'][item.source_view_id]}:"
                f"row:{refs['csv_rows'][item.row_id]}"
            )
    return item.origin_key


def _serialize_override_target(
    item: WorkItemOverride,
    refs: dict[str, dict[Any, str]],
) -> dict[str, Any]:
    if item.action_key.startswith("manual:"):
        raw_id = item.action_key.removeprefix("manual:")
        if not raw_id.isdigit() or int(raw_id) not in refs["work_items"]:
            raise BackupContractError(
                "conflicting_reference_graph",
                409,
                "Today override references an unavailable manual action.",
                section="work_item_overrides",
            )
        return {
            "kind": "manual",
            "work_item_ref": refs["work_items"][int(raw_id)],
            "track_ref": None,
            "follow_up_due_at": None,
        }

    if item.action_key.startswith("followup:"):
        parts = item.action_key.split(":", 2)
        if len(parts) != 3 or not parts[1].isdigit() or int(parts[1]) not in refs["job_tracks"]:
            raise BackupContractError(
                "conflicting_reference_graph",
                409,
                "Today override references an unavailable follow-up action.",
                section="work_item_overrides",
            )
        return {
            "kind": "followup",
            "work_item_ref": None,
            "track_ref": refs["job_tracks"][int(parts[1])],
            "follow_up_due_at": parts[2],
        }

    raise BackupContractError(
        "invalid_today_action_key",
        409,
        "Today override contains an invalid server-generated action key.",
        section="work_item_overrides",
    )


def _serialize_sections(
    snapshot: dict[str, list[Any]],
    refs: dict[str, dict[Any, str]],
) -> dict[str, list[dict[str, Any]]]:
    sections: dict[str, list[dict[str, Any]]] = {name: [] for name in BACKUP_V2_SECTIONS}

    for row in snapshot["csv_rows"]:
        backup_ref = refs["csv_rows"][row.id]
        record = {
            "backup_ref": backup_ref,
            "upload_batch_id": row.upload_batch_id,
            "created_at": _utc_iso(row.created_at),
            "clicked": row.clicked,
            "clicked_at": _utc_iso(row.clicked_at),
            "archived": row.archived,
            "archived_at": _utc_iso(row.archived_at),
            "is_duplicate": row.is_duplicate,
            "duplicate_of_ref": _required_ref(
                refs["csv_rows"], row.duplicate_of_id,
                section="csv_rows", backup_ref=backup_ref,
            ),
        }
        record.update({name: getattr(row, name) for name in CSV_ROW_TEXT_FIELDS})
        sections["csv_rows"].append(record)

    for item in snapshot["url_history"]:
        sections["url_history"].append({
            "backup_ref": refs["url_history"][item.id],
            "url": item.url,
            "first_seen_at": _utc_iso(item.first_seen_at),
        })

    for item in snapshot["job_tracks"]:
        backup_ref = refs["job_tracks"][item.id]
        sections["job_tracks"].append({
            "backup_ref": backup_ref,
            "csv_row_ref": _required_ref(
                refs["csv_rows"], item.csv_row_id,
                section="job_tracks", backup_ref=backup_ref,
            ),
            "url": item.url,
            "company": item.company,
            "title": item.title,
            "ats_group": item.ats_group,
            "search_bucket": item.search_bucket,
            "resume_match_score": item.resume_match_score,
            "status": item.status,
            "opened_at": _utc_iso(item.opened_at),
            "applied_at": _utc_iso(item.applied_at),
            "follow_up_at": _utc_iso(item.follow_up_at),
            "notes": item.notes,
            "session_id": item.session_id,
            "session_ref": None,
            "open_count": item.open_count,
            "last_opened_at": _utc_iso(item.last_opened_at),
            "created_at": _utc_iso(item.created_at),
            "updated_at": _utc_iso(item.updated_at),
        })

    for item in snapshot["document_versions"]:
        sections["document_versions"].append({
            "backup_ref": refs["document_versions"][item.id],
            "document_family_id": item.document_family_id,
            "kind": item.kind,
            "label": item.label,
            "original_filename": item.original_filename,
            "media_type": item.media_type,
            "size_bytes": item.size_bytes,
            "sha256": item.sha256,
            "version_number": item.version_number,
            "created_at": _utc_iso(item.created_at),
            "state": item.state,
        })

    for item in snapshot["application_documents"]:
        backup_ref = refs["application_documents"][item.id]
        sections["application_documents"].append({
            "backup_ref": backup_ref,
            "track_ref": _required_ref(
                refs["job_tracks"], item.track_id,
                section="application_documents", backup_ref=backup_ref,
            ),
            "document_ref": _required_ref(
                refs["document_versions"], item.document_version_id,
                section="application_documents", backup_ref=backup_ref,
            ),
            "kind": item.kind,
            "usage": item.usage,
            "attached_at": _utc_iso(item.attached_at),
        })

    for item in snapshot["application_evidence"]:
        backup_ref = refs["application_evidence"][item.id]
        sections["application_evidence"].append({
            "backup_ref": backup_ref,
            "track_ref": _required_ref(
                refs["job_tracks"], item.track_id,
                section="application_evidence", backup_ref=backup_ref,
            ),
            "kind": item.kind,
            # Deleted bodies are never present in the ordinary evidence section.
            "body": None if item.is_deleted else item.body,
            "occurred_at": _utc_iso(item.occurred_at),
            "created_at": _utc_iso(item.created_at),
            "updated_at": _utc_iso(item.updated_at),
            "version": item.version,
            "is_deleted": item.is_deleted,
        })

    for item in snapshot["evidence_recovery"]:
        recovery_ref = refs["evidence_recovery"][item.id]
        sections["evidence_recovery"].append({
            "backup_ref": recovery_ref,
            "evidence_ref": _required_ref(
                refs["application_evidence"], item.id,
                section="evidence_recovery", backup_ref=recovery_ref,
            ),
            "body": item.body,
            "body_purge_at": _utc_iso(evidence_body_purge_at(item.updated_at)),
        })

    for item in snapshot["company_aliases"]:
        sections["company_aliases"].append({
            "backup_ref": refs["company_aliases"][item.id],
            "alias_key": item.alias_key,
            "display_name": item.display_name,
            "company_key": item.company_key,
            "created_at": _utc_iso(item.created_at),
        })

    for item in snapshot["work_items"]:
        backup_ref = refs["work_items"][item.id]
        sections["work_items"].append({
            "backup_ref": backup_ref,
            "track_ref": _required_ref(
                refs["job_tracks"], item.track_id,
                section="work_items", backup_ref=backup_ref,
            ),
            "row_ref": _required_ref(
                refs["csv_rows"], item.row_id,
                section="work_items", backup_ref=backup_ref,
            ),
            "source_view_ref": _required_ref(
                refs["saved_views"], item.source_view_id,
                section="work_items", backup_ref=backup_ref,
            ),
            "origin_key": _portable_work_item_origin_key(item, refs),
            "description": item.description,
            "due_at": _utc_iso(item.due_at),
            "priority": item.priority,
            "state": item.state,
            "version": item.version,
            "created_at": _utc_iso(item.created_at),
            "updated_at": _utc_iso(item.updated_at),
            "completed_at": _utc_iso(item.completed_at),
        })

    for item in snapshot["work_item_overrides"]:
        target = _serialize_override_target(item, refs)
        sections["work_item_overrides"].append({
            "backup_ref": refs["work_item_overrides"][item.action_key],
            **target,
            "snoozed_until": _utc_iso(item.snoozed_until),
            "version": item.version,
        })

    for item in snapshot["lifecycle_events"]:
        backup_ref = refs["lifecycle_events"][item.id]
        payload = dict(item.payload or {})
        evidence_ref = None
        correction_of_ref = None
        if item.kind in {"evidence_added", "evidence_edited", "evidence_deleted"}:
            evidence_id = payload.pop("evidence_id", None)
            evidence_ref = _required_ref(
                refs["application_evidence"], evidence_id,
                section="lifecycle_events", backup_ref=backup_ref,
            )
            if evidence_ref is None:
                raise BackupContractError(
                    "conflicting_reference_graph",
                    409,
                    "Evidence lifecycle event is missing its evidence reference.",
                    section="lifecycle_events",
                    backup_ref=backup_ref,
                )
        if item.kind == "status_changed" and "correction_of" in payload:
            correction_of = payload.pop("correction_of")
            correction_of_ref = _required_ref(
                refs["lifecycle_events"], correction_of,
                section="lifecycle_events", backup_ref=backup_ref,
            )
            if correction_of_ref is None:
                raise BackupContractError(
                    "conflicting_reference_graph",
                    409,
                    "Status correction is missing its original lifecycle reference.",
                    section="lifecycle_events",
                    backup_ref=backup_ref,
                )
        sections["lifecycle_events"].append({
            "backup_ref": backup_ref,
            "event_key": item.event_key,
            "job_url": item.job_url,
            "csv_row_ref": _required_ref(
                refs["csv_rows"], item.csv_row_id,
                section="lifecycle_events", backup_ref=backup_ref,
            ),
            "job_track_ref": _required_ref(
                refs["job_tracks"], item.job_track_id,
                section="lifecycle_events", backup_ref=backup_ref,
            ),
            "evidence_ref": evidence_ref,
            "correction_of_ref": correction_of_ref,
            "kind": item.kind,
            "occurred_at": _utc_iso(item.occurred_at),
            "recorded_at": _utc_iso(item.recorded_at),
            "source": item.source,
            "payload": payload,
        })

    for item in snapshot["reminder_preferences"]:
        sections["reminder_preferences"].append({
            "backup_ref": refs["reminder_preferences"][item.user_id],
            "enabled": item.enabled,
            "channel": item.channel,
            "local_time": item.local_time,
            "quiet_start": item.quiet_start,
            "quiet_end": item.quiet_end,
        })

    for item in snapshot["reminder_deliveries"]:
        backup_ref = refs["reminder_deliveries"][item.id]
        sections["reminder_deliveries"].append({
            "backup_ref": backup_ref,
            "track_ref": _required_ref(
                refs["job_tracks"], item.track_id,
                section="reminder_deliveries", backup_ref=backup_ref,
            ),
            "occurrence_key": item.occurrence_key,
            "channel": item.channel,
            "status": item.status,
            "scheduled_at": _utc_iso(item.scheduled_at),
            "attempt_count": item.attempt_count,
            "next_attempt_at": _utc_iso(item.next_attempt_at),
            "sent_at": _utc_iso(item.sent_at),
            "read_at": _utc_iso(item.read_at),
            "last_error_code": item.last_error_code,
            "version": item.version,
        })

    for item in snapshot["saved_views"]:
        sections["saved_views"].append({
            "backup_ref": refs["saved_views"][item.id],
            "name": item.name,
            "view_type": item.view_type,
            "filters": item.filters,
            "is_pinned": item.is_pinned,
            "created_at": _utc_iso(item.created_at),
        })

    for item in snapshot["sessions"]:
        sections["sessions"].append({
            "backup_ref": refs["sessions"][item.id],
            "name": item.name,
            "started_at": _utc_iso(item.started_at),
            "ended_at": _utc_iso(item.ended_at),
            "notes": item.notes,
        })

    for item in snapshot["audit_events"]:
        backup_ref = refs["audit_events"][item.id]
        entity_ref = None
        legacy_entity_id = item.entity_id
        target_section = AUDIT_ENTITY_SECTION.get(item.entity_type)
        if item.entity_id is not None and target_section is not None:
            entity_ref = refs[target_section].get(item.entity_id)
            if entity_ref is not None:
                legacy_entity_id = None
        sections["audit_events"].append({
            "backup_ref": backup_ref,
            "session_ref": _required_ref(
                refs["sessions"], item.session_id,
                section="audit_events", backup_ref=backup_ref,
            ),
            "event_type": item.event_type,
            "entity_type": item.entity_type,
            "entity_ref": entity_ref,
            "legacy_entity_id": legacy_entity_id,
            "metadata_json": item.metadata_json,
            "created_at": _utc_iso(item.created_at),
        })

    for item in snapshot["applypilot_batches"]:
        backup_ref = refs["applypilot_batches"][item.id]
        sections["applypilot_batches"].append({
            "backup_ref": backup_ref,
            "session_ref": _required_ref(
                refs["sessions"], item.session_id,
                section="applypilot_batches", backup_ref=backup_ref,
            ),
            "name": item.name,
            "payload_json": item.payload_json,
            "status": item.status,
            "job_count": item.job_count,
            "created_at": _utc_iso(item.created_at),
            "updated_at": _utc_iso(item.updated_at),
        })

    for item in snapshot["column_preferences"]:
        sections["column_preferences"].append({
            "backup_ref": refs["column_preferences"][item.user_id],
            "hidden_columns": item.hidden_columns,
            "column_order": item.column_order,
        })

    for item in snapshot["user_goal"]:
        sections["user_goal"].append({
            "backup_ref": refs["user_goal"][item.user_id],
            "open_per_day": item.open_per_day,
            "apply_per_day": item.apply_per_day,
            "followup_per_day": item.followup_per_day,
            "applypilot_per_day": item.applypilot_per_day,
        })

    for item in snapshot["user_profile"]:
        sections["user_profile"].append({
            "backup_ref": refs["user_profile"][item.id],
            "timezone": item.timezone,
            "retention_days": item.retention_days,
        })

    return sections


def _build_backup_v2(session: Session, user_id: int) -> dict[str, Any]:
    backup_id = uuid4()
    snapshot = _query_snapshot(session, user_id)
    refs = _ref_maps(snapshot, backup_id)
    sections = _serialize_sections(snapshot, refs)
    payload = {
        "version": "2.0",
        "backup_id": str(backup_id),
        "exported_at": _utc_iso(datetime.now(timezone.utc)),
        "schema_revision": BACKUP_SCHEMA_REVISION,
        "identity_rule_version": CANONICALIZATION_VERSION,
        "document_bytes_included": False,
        "sections": sections,
        "counts": {name: len(sections[name]) for name in BACKUP_V2_SECTIONS},
        "checksum_sha256": compute_sections_checksum(sections),
    }
    return validate_backup_v2(payload).model_dump(mode="json", exclude_none=False)


def export_backup_v2(db: Session, user_id: int) -> dict[str, Any]:
    """Build v2 from a dedicated read transaction without committing request state."""
    bind = db.get_bind()
    engine = getattr(bind, "engine", bind)
    isolation_level = "REPEATABLE READ" if engine.dialect.name == "postgresql" else "SERIALIZABLE"

    with engine.connect().execution_options(isolation_level=isolation_level) as connection:
        snapshot_session = Session(bind=connection, autoflush=False, expire_on_commit=False)
        try:
            with snapshot_session.begin():
                return _build_backup_v2(snapshot_session, user_id)
        finally:
            snapshot_session.close()


RESTORE_MODE_MERGE = "merge_missing"
RESTORE_MODE_VERIFY = "verify_only"
LEGACY_NAMESPACE = UUID("88fc885c-0996-4ff6-8ce5-9bb8df113273")


def _parse_backup_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _empty_restore_counts() -> dict[str, dict[str, int]]:
    return {
        section: {"created": 0, "skipped": 0, "conflicts": 0}
        for section in BACKUP_V2_SECTIONS
    }


def _restore_warning(
    code: str,
    *,
    section: str | None = None,
    backup_ref: str | None = None,
) -> dict[str, str]:
    warning = {"code": code}
    if section is not None:
        warning["section"] = section
    if backup_ref is not None:
        warning["backup_ref"] = backup_ref
    return warning


def _portable_equal(actual: Any, expected: Any) -> bool:
    if isinstance(actual, datetime):
        if expected is None:
            return False
        parsed = datetime.fromisoformat(str(expected).replace("Z", "+00:00"))
        actual_utc = (
            actual.replace(tzinfo=timezone.utc)
            if actual.tzinfo is None
            else actual.astimezone(timezone.utc)
        )
        expected_utc = (
            parsed.replace(tzinfo=timezone.utc)
            if parsed.tzinfo is None
            else parsed.astimezone(timezone.utc)
        )
        return actual_utc == expected_utc
    return actual == expected


def _record_equal(actual: Any, record: Any, fields: tuple[str, ...]) -> bool:
    for field in fields:
        if not _portable_equal(getattr(actual, field), getattr(record, field)):
            return False
    return True


def _lookup_import_map(
    session: Session,
    user_id: int,
    backup_id: str,
    section: str,
    backup_ref: str,
):
    return session.query(BackupImportMap).filter_by(
        user_id=user_id,
        backup_id=backup_id,
        section=section,
        backup_ref=backup_ref,
    ).first()


def _persist_import_map(
    session: Session,
    user_id: int,
    backup_id: str,
    section: str,
    backup_ref: str,
    target_id: int,
) -> int:
    existing = _lookup_import_map(session, user_id, backup_id, section, backup_ref)
    if existing is not None:
        if existing.target_id != target_id:
            raise BackupContractError(
                "restore_mapping_conflict",
                409,
                "Backup reference is already mapped to a different destination record.",
                section=section,
                backup_ref=backup_ref,
            )
        return existing.target_id

    try:
        with session.begin_nested():
            session.add(BackupImportMap(
                user_id=user_id,
                backup_id=backup_id,
                section=section,
                backup_ref=backup_ref,
                target_id=target_id,
            ))
            session.flush()
        return target_id
    except IntegrityError:
        concurrent = _lookup_import_map(session, user_id, backup_id, section, backup_ref)
        if concurrent is None or concurrent.target_id != target_id:
            raise BackupContractError(
                "restore_mapping_conflict",
                409,
                "Concurrent restore produced an incompatible destination mapping.",
                section=section,
                backup_ref=backup_ref,
            )
        return concurrent.target_id


def _mapped_target(
    session: Session,
    user_id: int,
    backup_id: str,
    section: str,
    backup_ref: str,
    model: Any,
) -> Any | None:
    mapping = _lookup_import_map(session, user_id, backup_id, section, backup_ref)
    if mapping is None:
        return None
    target = session.query(model).filter(model.user_id == user_id, model.id == mapping.target_id).first()
    if target is None:
        raise BackupContractError(
            "stale_restore_mapping",
            409,
            "Restore mapping points to a destination record that no longer exists.",
            section=section,
            backup_ref=backup_ref,
        )
    return target


def _classify_existing(equal: bool) -> str:
    return "skipped" if equal else "conflicts"


def _mapped_ref_target(
    session: Session,
    user_id: int,
    backup_id: str,
    section: str,
    backup_ref: str | None,
) -> int | None:
    if backup_ref is None:
        return None
    mapping = _lookup_import_map(session, user_id, backup_id, section, backup_ref)
    return mapping.target_id if mapping is not None else None


def _restored_origin_key(
    record: Any,
    refs: dict[str, dict[str, int]],
) -> str | None:
    if record.origin_key is None:
        return None
    if (
        record.source_view_ref is not None
        and record.row_ref is not None
        and record.origin_key.startswith("view:")
    ):
        return (
            f"view:{_target_id(refs, 'saved_views', record.source_view_ref, 'work_items', record.backup_ref)}:"
            f"row:{_target_id(refs, 'csv_rows', record.row_ref, 'work_items', record.backup_ref)}"
        )
    return record.origin_key


def _override_action_key_from_refs(
    record: Any,
    refs: dict[str, dict[str, int]],
) -> str:
    if record.kind == "manual":
        work_item_id = _target_id(
            refs, "work_items", record.work_item_ref,
            "work_item_overrides", record.backup_ref,
        )
        return manual_action_key(work_item_id)
    track_id = _target_id(
        refs, "job_tracks", record.track_ref,
        "work_item_overrides", record.backup_ref,
    )
    due_at = datetime.fromisoformat(record.follow_up_due_at.replace("Z", "+00:00"))
    return followup_action_key(track_id, due_at)


def _preflight_v2(session: Session, user_id: int, document: BackupDocumentV2) -> dict[str, dict[str, int]]:
    if (
        document.identity_rule_version is not None
        and document.identity_rule_version != CANONICALIZATION_VERSION
    ):
        raise BackupContractError(
            "unsupported_identity_rule_version",
            409,
            "Backup identity rule version is not supported by this release.",
        )
    counts = _empty_restore_counts()
    backup_id = document.backup_id

    for record in document.sections.sessions:
        mapping = _lookup_import_map(session, user_id, backup_id, "sessions", record.backup_ref)
        counts["sessions"]["skipped" if mapping else "created"] += 1

    for record in document.sections.csv_rows:
        mapping = _lookup_import_map(session, user_id, backup_id, "csv_rows", record.backup_ref)
        if mapping:
            counts["csv_rows"]["skipped"] += 1
            continue
        existing = session.query(CsvRow).filter_by(user_id=user_id, url=record.url).first()
        if existing is None:
            counts["csv_rows"]["created"] += 1
        else:
            fields = ("upload_batch_id", "created_at", "clicked", "clicked_at", "archived", "archived_at", "is_duplicate", *CSV_ROW_TEXT_FIELDS)
            counts["csv_rows"][_classify_existing(_record_equal(existing, record, fields))] += 1

    for record in document.sections.url_history:
        mapping = _lookup_import_map(session, user_id, backup_id, "url_history", record.backup_ref)
        if mapping:
            counts["url_history"]["skipped"] += 1
            continue
        existing = session.query(UrlHistory).filter_by(user_id=user_id, url=record.url).first()
        if existing is None:
            counts["url_history"]["created"] += 1
        else:
            counts["url_history"][_classify_existing(_record_equal(existing, record, ("url", "first_seen_at")))] += 1

    for record in document.sections.saved_views:
        mapping = _lookup_import_map(session, user_id, backup_id, "saved_views", record.backup_ref)
        if mapping:
            counts["saved_views"]["skipped"] += 1
            continue
        existing = session.query(SavedView).filter_by(
            user_id=user_id, name=record.name, view_type=record.view_type
        ).first()
        if existing is None:
            counts["saved_views"]["created"] += 1
        else:
            fields = ("name", "view_type", "filters", "is_pinned", "created_at")
            counts["saved_views"][_classify_existing(_record_equal(existing, record, fields))] += 1

    for record in document.sections.column_preferences:
        mapping = _lookup_import_map(session, user_id, backup_id, "column_preferences", record.backup_ref)
        if mapping:
            counts["column_preferences"]["skipped"] += 1
            continue
        existing = session.query(ColumnPreference).filter_by(user_id=user_id).first()
        if existing is None:
            counts["column_preferences"]["created"] += 1
        else:
            fields = ("hidden_columns", "column_order")
            counts["column_preferences"][_classify_existing(_record_equal(existing, record, fields))] += 1

    for record in document.sections.user_goal:
        mapping = _lookup_import_map(session, user_id, backup_id, "user_goal", record.backup_ref)
        if mapping:
            counts["user_goal"]["skipped"] += 1
            continue
        existing = session.query(UserGoal).filter_by(user_id=user_id).first()
        if existing is None:
            counts["user_goal"]["created"] += 1
        else:
            fields = ("open_per_day", "apply_per_day", "followup_per_day", "applypilot_per_day")
            counts["user_goal"][_classify_existing(_record_equal(existing, record, fields))] += 1

    for record in document.sections.user_profile:
        mapping = _lookup_import_map(session, user_id, backup_id, "user_profile", record.backup_ref)
        counts["user_profile"]["skipped" if mapping else "created"] += 1

    for record in document.sections.reminder_preferences:
        mapping = _lookup_import_map(
            session, user_id, backup_id,
            "reminder_preferences", record.backup_ref,
        )
        if mapping:
            counts["reminder_preferences"]["skipped"] += 1
            continue
        existing = session.query(ReminderPreference).filter_by(user_id=user_id).first()
        if existing is None:
            counts["reminder_preferences"]["created"] += 1
        else:
            equal = (
                existing.enabled is False
                and existing.channel == record.channel
                and existing.local_time == record.local_time
                and existing.quiet_start == record.quiet_start
                and existing.quiet_end == record.quiet_end
            )
            counts["reminder_preferences"][_classify_existing(equal)] += 1

    for record in document.sections.job_tracks:
        mapping = _lookup_import_map(session, user_id, backup_id, "job_tracks", record.backup_ref)
        if mapping:
            counts["job_tracks"]["skipped"] += 1
            continue
        existing = session.query(JobTrack).filter_by(user_id=user_id, url=record.url).first()
        if existing is None:
            counts["job_tracks"]["created"] += 1
        else:
            fields = (
                "url", "company", "title", "ats_group", "search_bucket", "resume_match_score",
                "status", "opened_at", "applied_at", "follow_up_at", "notes", "session_id",
                "open_count", "last_opened_at", "created_at", "updated_at",
            )
            counts["job_tracks"][_classify_existing(_record_equal(existing, record, fields))] += 1

    # JSON v2.9 carries document metadata/checksums only. JG-044 owns the
    # byte bundle; without bytes, restore must never publish a ready file row.
    for record in document.sections.document_versions:
        counts["document_versions"]["skipped"] += 1
    for record in document.sections.application_documents:
        counts["application_documents"]["skipped"] += 1

    for record in document.sections.application_evidence:
        mapping = _lookup_import_map(
            session, user_id, backup_id, "application_evidence", record.backup_ref
        )
        counts["application_evidence"]["skipped" if mapping else "created"] += 1

    for record in document.sections.evidence_recovery:
        mapping = _lookup_import_map(
            session, user_id, backup_id, "evidence_recovery", record.backup_ref
        )
        if mapping:
            counts["evidence_recovery"]["skipped"] += 1
            continue
        purge_at = _parse_backup_datetime(record.body_purge_at)
        if purge_at is None or purge_at <= datetime.utcnow():
            counts["evidence_recovery"]["skipped"] += 1
        else:
            counts["evidence_recovery"]["created"] += 1

    for record in document.sections.company_aliases:
        mapping = _lookup_import_map(
            session, user_id, backup_id, "company_aliases", record.backup_ref
        )
        if mapping:
            counts["company_aliases"]["skipped"] += 1
            continue
        existing = session.query(CompanyAlias).filter_by(
            user_id=user_id, alias_key=record.alias_key
        ).first()
        if existing is None:
            counts["company_aliases"]["created"] += 1
        else:
            fields = ("alias_key", "display_name", "company_key", "created_at")
            counts["company_aliases"][
                _classify_existing(_record_equal(existing, record, fields))
            ] += 1

    for record in document.sections.work_items:
        mapping = _lookup_import_map(session, user_id, backup_id, "work_items", record.backup_ref)
        if mapping:
            counts["work_items"]["skipped"] += 1
            continue
        existing = None
        if record.origin_key is not None:
            if record.origin_key.startswith("view:"):
                view_id = _mapped_ref_target(
                    session, user_id, backup_id, "saved_views", record.source_view_ref
                )
                row_id = _mapped_ref_target(
                    session, user_id, backup_id, "csv_rows", record.row_ref
                )
                destination_origin = (
                    f"view:{view_id}:row:{row_id}"
                    if view_id is not None and row_id is not None
                    else None
                )
            else:
                destination_origin = record.origin_key
            if destination_origin is not None:
                existing = session.query(WorkItem).filter_by(
                    user_id=user_id, origin_key=destination_origin
                ).first()
        counts["work_items"]["conflicts" if existing is not None else "created"] += 1

    for record in document.sections.work_item_overrides:
        if record.kind == "manual":
            target_id = _mapped_ref_target(
                session, user_id, backup_id, "work_items", record.work_item_ref
            )
            action_key = manual_action_key(target_id) if target_id is not None else None
        else:
            target_id = _mapped_ref_target(
                session, user_id, backup_id, "job_tracks", record.track_ref
            )
            if target_id is None:
                action_key = None
            else:
                due_at = datetime.fromisoformat(record.follow_up_due_at.replace("Z", "+00:00"))
                action_key = followup_action_key(target_id, due_at)
        existing = (
            session.query(WorkItemOverride).filter_by(user_id=user_id, action_key=action_key).first()
            if action_key is not None
            else None
        )
        if existing is None:
            counts["work_item_overrides"]["created"] += 1
        else:
            equal = (
                _portable_equal(existing.snoozed_until, record.snoozed_until)
                and existing.version == record.version
            )
            counts["work_item_overrides"][_classify_existing(equal)] += 1

    for record in document.sections.reminder_deliveries:
        mapping = _lookup_import_map(
            session, user_id, backup_id,
            "reminder_deliveries", record.backup_ref,
        )
        counts["reminder_deliveries"]["skipped" if mapping else "created"] += 1

    for record in document.sections.lifecycle_events:
        mapping = _lookup_import_map(session, user_id, backup_id, "lifecycle_events", record.backup_ref)
        if mapping:
            counts["lifecycle_events"]["skipped"] += 1
            continue
        existing = session.query(JobLifecycleEvent).filter_by(
            user_id=user_id, event_key=record.event_key
        ).first()
        if existing is None:
            counts["lifecycle_events"]["created"] += 1
        else:
            expected_payload = dict(record.payload)
            if record.evidence_ref is not None:
                evidence_id = _mapped_ref_target(
                    session, user_id, backup_id,
                    "application_evidence", record.evidence_ref,
                )
                if evidence_id is not None:
                    expected_payload["evidence_id"] = evidence_id
            if record.correction_of_ref is not None:
                correction_id = _mapped_ref_target(
                    session, user_id, backup_id,
                    "lifecycle_events", record.correction_of_ref,
                )
                if correction_id is not None:
                    expected_payload["correction_of"] = correction_id
            fields = (
                "event_key", "job_url", "kind", "occurred_at",
                "recorded_at", "source",
            )
            equal = (
                _record_equal(existing, record, fields)
                and existing.payload == expected_payload
            )
            counts["lifecycle_events"][_classify_existing(equal)] += 1

    for section, records in (
        ("applypilot_batches", document.sections.applypilot_batches),
        ("audit_events", document.sections.audit_events),
    ):
        for record in records:
            mapping = _lookup_import_map(session, user_id, backup_id, section, record.backup_ref)
            counts[section]["skipped" if mapping else "created"] += 1

    return counts


def _target_id(
    refs: dict[str, dict[str, int]],
    section: str,
    backup_ref: str | None,
    source_section: str,
    source_ref: str,
) -> int | None:
    if backup_ref is None:
        return None
    try:
        return refs[section][backup_ref]
    except KeyError as exc:
        raise BackupContractError(
            "conflicting_reference_graph",
            409,
            "Validated backup reference could not be resolved during restore.",
            section=source_section,
            backup_ref=source_ref,
        ) from exc


def _restore_v2_transaction(session: Session, user_id: int, document: BackupDocumentV2) -> dict[str, Any]:
    if (
        document.identity_rule_version is not None
        and document.identity_rule_version != CANONICALIZATION_VERSION
    ):
        raise BackupContractError(
            "unsupported_identity_rule_version",
            409,
            "Backup identity rule version is not supported by this release.",
        )
    counts = _empty_restore_counts()
    warnings: list[dict[str, str]] = []
    refs: dict[str, dict[str, int]] = {section: {} for section in BACKUP_V2_SECTIONS}
    backup_id = document.backup_id

    session.query(User).filter(User.id == user_id).with_for_update().one()

    for record in document.sections.sessions:
        mapped = _mapped_target(session, user_id, backup_id, "sessions", record.backup_ref, SearchSession)
        if mapped is not None:
            refs["sessions"][record.backup_ref] = mapped.id
            counts["sessions"]["skipped"] += 1
            continue
        item = SearchSession(
            user_id=user_id,
            name=record.name,
            started_at=_parse_backup_datetime(record.started_at),
            ended_at=_parse_backup_datetime(record.ended_at),
            notes=record.notes,
        )
        session.add(item)
        session.flush()
        refs["sessions"][record.backup_ref] = item.id
        _persist_import_map(session, user_id, backup_id, "sessions", record.backup_ref, item.id)
        counts["sessions"]["created"] += 1

    created_rows: dict[str, CsvRow] = {}
    for record in document.sections.csv_rows:
        mapped = _mapped_target(session, user_id, backup_id, "csv_rows", record.backup_ref, CsvRow)
        if mapped is not None:
            apply_persisted_job_identity(mapped)
            refs["csv_rows"][record.backup_ref] = mapped.id
            counts["csv_rows"]["skipped"] += 1
            continue
        existing = session.query(CsvRow).filter_by(user_id=user_id, url=record.url).first()
        if existing is not None:
            apply_persisted_job_identity(existing)
            fields = ("upload_batch_id", "created_at", "clicked", "clicked_at", "archived", "archived_at", "is_duplicate", *CSV_ROW_TEXT_FIELDS)
            outcome = _classify_existing(_record_equal(existing, record, fields))
            refs["csv_rows"][record.backup_ref] = existing.id
            _persist_import_map(session, user_id, backup_id, "csv_rows", record.backup_ref, existing.id)
            counts["csv_rows"][outcome] += 1
            if outcome == "conflicts":
                warnings.append(_restore_warning("destination_record_preserved", section="csv_rows", backup_ref=record.backup_ref))
            continue
        values = {name: getattr(record, name) for name in CSV_ROW_TEXT_FIELDS}
        item = CsvRow(
            user_id=user_id,
            upload_batch_id=record.upload_batch_id,
            created_at=_parse_backup_datetime(record.created_at),
            clicked=record.clicked,
            clicked_at=_parse_backup_datetime(record.clicked_at),
            archived=record.archived,
            archived_at=_parse_backup_datetime(record.archived_at),
            is_duplicate=record.is_duplicate,
            duplicate_of_id=None,
            **values,
        )
        apply_persisted_job_identity(item)
        session.add(item)
        session.flush()
        created_rows[record.backup_ref] = item
        refs["csv_rows"][record.backup_ref] = item.id
        _persist_import_map(session, user_id, backup_id, "csv_rows", record.backup_ref, item.id)
        counts["csv_rows"]["created"] += 1

    for record in document.sections.csv_rows:
        item = created_rows.get(record.backup_ref)
        if item is not None and record.duplicate_of_ref is not None:
            item.duplicate_of_id = _target_id(
                refs, "csv_rows", record.duplicate_of_ref, "csv_rows", record.backup_ref
            )

    for record in document.sections.url_history:
        mapped = _mapped_target(session, user_id, backup_id, "url_history", record.backup_ref, UrlHistory)
        if mapped is not None:
            refs["url_history"][record.backup_ref] = mapped.id
            counts["url_history"]["skipped"] += 1
            continue
        existing = session.query(UrlHistory).filter_by(user_id=user_id, url=record.url).first()
        if existing is not None:
            outcome = _classify_existing(_record_equal(existing, record, ("url", "first_seen_at")))
            refs["url_history"][record.backup_ref] = existing.id
            _persist_import_map(session, user_id, backup_id, "url_history", record.backup_ref, existing.id)
            counts["url_history"][outcome] += 1
            if outcome == "conflicts":
                warnings.append(_restore_warning("destination_record_preserved", section="url_history", backup_ref=record.backup_ref))
            continue
        item = UrlHistory(user_id=user_id, url=record.url, first_seen_at=_parse_backup_datetime(record.first_seen_at))
        session.add(item)
        session.flush()
        refs["url_history"][record.backup_ref] = item.id
        _persist_import_map(session, user_id, backup_id, "url_history", record.backup_ref, item.id)
        counts["url_history"]["created"] += 1

    for record in document.sections.saved_views:
        mapped = _mapped_target(session, user_id, backup_id, "saved_views", record.backup_ref, SavedView)
        if mapped is not None:
            refs["saved_views"][record.backup_ref] = mapped.id
            counts["saved_views"]["skipped"] += 1
            continue
        existing = session.query(SavedView).filter_by(user_id=user_id, name=record.name, view_type=record.view_type).first()
        if existing is not None:
            fields = ("name", "view_type", "filters", "is_pinned", "created_at")
            outcome = _classify_existing(_record_equal(existing, record, fields))
            refs["saved_views"][record.backup_ref] = existing.id
            _persist_import_map(session, user_id, backup_id, "saved_views", record.backup_ref, existing.id)
            counts["saved_views"][outcome] += 1
            if outcome == "conflicts":
                warnings.append(_restore_warning("destination_record_preserved", section="saved_views", backup_ref=record.backup_ref))
            continue
        item = SavedView(
            user_id=user_id,
            name=record.name,
            view_type=record.view_type,
            filters=record.filters,
            is_pinned=record.is_pinned,
            created_at=_parse_backup_datetime(record.created_at),
        )
        session.add(item)
        session.flush()
        refs["saved_views"][record.backup_ref] = item.id
        _persist_import_map(session, user_id, backup_id, "saved_views", record.backup_ref, item.id)
        counts["saved_views"]["created"] += 1

    for record in document.sections.column_preferences:
        mapping = _lookup_import_map(session, user_id, backup_id, "column_preferences", record.backup_ref)
        if mapping is not None:
            refs["column_preferences"][record.backup_ref] = mapping.target_id
            counts["column_preferences"]["skipped"] += 1
            continue
        existing = session.query(ColumnPreference).filter_by(user_id=user_id).first()
        if existing is not None:
            outcome = _classify_existing(_record_equal(existing, record, ("hidden_columns", "column_order")))
            refs["column_preferences"][record.backup_ref] = user_id
            _persist_import_map(session, user_id, backup_id, "column_preferences", record.backup_ref, user_id)
            counts["column_preferences"][outcome] += 1
            if outcome == "conflicts":
                warnings.append(_restore_warning("destination_record_preserved", section="column_preferences", backup_ref=record.backup_ref))
            continue
        item = ColumnPreference(user_id=user_id, hidden_columns=record.hidden_columns, column_order=record.column_order)
        session.add(item)
        session.flush()
        refs["column_preferences"][record.backup_ref] = user_id
        _persist_import_map(session, user_id, backup_id, "column_preferences", record.backup_ref, user_id)
        counts["column_preferences"]["created"] += 1

    for record in document.sections.user_goal:
        mapping = _lookup_import_map(session, user_id, backup_id, "user_goal", record.backup_ref)
        if mapping is not None:
            refs["user_goal"][record.backup_ref] = mapping.target_id
            counts["user_goal"]["skipped"] += 1
            continue
        existing = session.query(UserGoal).filter_by(user_id=user_id).first()
        if existing is not None:
            fields = ("open_per_day", "apply_per_day", "followup_per_day", "applypilot_per_day")
            outcome = _classify_existing(_record_equal(existing, record, fields))
            refs["user_goal"][record.backup_ref] = user_id
            _persist_import_map(session, user_id, backup_id, "user_goal", record.backup_ref, user_id)
            counts["user_goal"][outcome] += 1
            if outcome == "conflicts":
                warnings.append(_restore_warning("destination_record_preserved", section="user_goal", backup_ref=record.backup_ref))
            continue
        item = UserGoal(
            user_id=user_id,
            open_per_day=record.open_per_day,
            apply_per_day=record.apply_per_day,
            followup_per_day=record.followup_per_day,
            applypilot_per_day=record.applypilot_per_day,
        )
        session.add(item)
        session.flush()
        refs["user_goal"][record.backup_ref] = user_id
        _persist_import_map(session, user_id, backup_id, "user_goal", record.backup_ref, user_id)
        counts["user_goal"]["created"] += 1

    for record in document.sections.user_profile:
        mapping = _lookup_import_map(
            session, user_id, backup_id, "user_profile", record.backup_ref
        )
        if mapping is not None:
            if mapping.target_id != user_id:
                raise BackupContractError(
                    "restore_mapping_conflict",
                    409,
                    "User-profile backup reference maps to a different account.",
                    section="user_profile",
                    backup_ref=record.backup_ref,
                )
            refs["user_profile"][record.backup_ref] = user_id
            counts["user_profile"]["skipped"] += 1
            continue

        owner = session.query(User).filter(User.id == user_id).one()
        owner.timezone = record.timezone
        owner.retention_days = record.retention_days
        refs["user_profile"][record.backup_ref] = user_id
        _persist_import_map(
            session,
            user_id,
            backup_id,
            "user_profile",
            record.backup_ref,
            user_id,
        )
        counts["user_profile"]["created"] += 1

    for record in document.sections.reminder_preferences:
        mapping = _lookup_import_map(
            session, user_id, backup_id,
            "reminder_preferences", record.backup_ref,
        )
        if mapping is not None:
            if mapping.target_id != user_id:
                raise BackupContractError(
                    "restore_mapping_conflict",
                    409,
                    "Reminder preference maps to a different account.",
                    section="reminder_preferences",
                    backup_ref=record.backup_ref,
                )
            refs["reminder_preferences"][record.backup_ref] = user_id
            counts["reminder_preferences"]["skipped"] += 1
            continue

        existing = session.query(ReminderPreference).filter_by(user_id=user_id).first()
        if existing is not None:
            equal = (
                existing.enabled is False
                and existing.channel == record.channel
                and existing.local_time == record.local_time
                and existing.quiet_start == record.quiet_start
                and existing.quiet_end == record.quiet_end
            )
            outcome = _classify_existing(equal)
            refs["reminder_preferences"][record.backup_ref] = user_id
            _persist_import_map(
                session, user_id, backup_id,
                "reminder_preferences", record.backup_ref, user_id,
            )
            counts["reminder_preferences"][outcome] += 1
            if outcome == "conflicts":
                warnings.append(_restore_warning(
                    "destination_record_preserved",
                    section="reminder_preferences",
                    backup_ref=record.backup_ref,
                ))
            continue

        item = ReminderPreference(
            user_id=user_id,
            enabled=False,
            channel=record.channel,
            local_time=record.local_time,
            quiet_start=record.quiet_start,
            quiet_end=record.quiet_end,
        )
        session.add(item)
        session.flush()
        refs["reminder_preferences"][record.backup_ref] = user_id
        _persist_import_map(
            session, user_id, backup_id,
            "reminder_preferences", record.backup_ref, user_id,
        )
        counts["reminder_preferences"]["created"] += 1
        if record.enabled:
            warnings.append(_restore_warning(
                "reminder_preference_restored_disabled",
                section="reminder_preferences",
                backup_ref=record.backup_ref,
            ))

    for record in document.sections.job_tracks:
        mapped = _mapped_target(session, user_id, backup_id, "job_tracks", record.backup_ref, JobTrack)
        if mapped is not None:
            apply_persisted_job_identity(mapped)
            refs["job_tracks"][record.backup_ref] = mapped.id
            counts["job_tracks"]["skipped"] += 1
            continue
        existing = session.query(JobTrack).filter_by(user_id=user_id, url=record.url).first()
        if existing is not None:
            apply_persisted_job_identity(existing)
            fields = (
                "url", "company", "title", "ats_group", "search_bucket", "resume_match_score",
                "status", "opened_at", "applied_at", "follow_up_at", "notes", "session_id",
                "open_count", "last_opened_at", "created_at", "updated_at",
            )
            outcome = _classify_existing(_record_equal(existing, record, fields))
            refs["job_tracks"][record.backup_ref] = existing.id
            _persist_import_map(session, user_id, backup_id, "job_tracks", record.backup_ref, existing.id)
            counts["job_tracks"][outcome] += 1
            if outcome == "conflicts":
                warnings.append(_restore_warning("destination_record_preserved", section="job_tracks", backup_ref=record.backup_ref))
            continue
        item = JobTrack(
            user_id=user_id,
            csv_row_id=_target_id(refs, "csv_rows", record.csv_row_ref, "job_tracks", record.backup_ref),
            url=record.url,
            company=record.company,
            title=record.title,
            ats_group=record.ats_group,
            search_bucket=record.search_bucket,
            resume_match_score=record.resume_match_score,
            status=record.status,
            opened_at=_parse_backup_datetime(record.opened_at),
            applied_at=_parse_backup_datetime(record.applied_at),
            follow_up_at=_parse_backup_datetime(record.follow_up_at),
            notes=record.notes,
            session_id=record.session_id,
            open_count=record.open_count,
            last_opened_at=_parse_backup_datetime(record.last_opened_at),
            created_at=_parse_backup_datetime(record.created_at),
            updated_at=_parse_backup_datetime(record.updated_at),
        )
        apply_persisted_job_identity(item)
        session.add(item)
        session.flush()
        refs["job_tracks"][record.backup_ref] = item.id
        _persist_import_map(session, user_id, backup_id, "job_tracks", record.backup_ref, item.id)
        counts["job_tracks"]["created"] += 1
        if record.session_ref is not None:
            warnings.append(_restore_warning("job_track_session_ref_detached", section="job_tracks", backup_ref=record.backup_ref))

    for record in document.sections.reminder_deliveries:
        mapped = _mapped_target(
            session, user_id, backup_id,
            "reminder_deliveries", record.backup_ref, ReminderDelivery,
        )
        if mapped is not None:
            refs["reminder_deliveries"][record.backup_ref] = mapped.id
            counts["reminder_deliveries"]["skipped"] += 1
            continue

        track_id = _target_id(
            refs, "job_tracks", record.track_ref,
            "reminder_deliveries", record.backup_ref,
        )
        occurrence_key = (
            remap_reminder_occurrence_key(record.occurrence_key, track_id=track_id)
            if track_id is not None
            else record.occurrence_key
        )
        restored_status = (
            "pending"
            if record.status == "pending"
            else "unknown"
            if record.status == "sending"
            else record.status
        )
        restored_error = (
            "restored_paused"
            if record.status == "pending"
            else "restored_inflight_unknown"
            if record.status == "sending"
            else record.last_error_code
        )
        existing = session.query(ReminderDelivery).filter_by(
            user_id=user_id,
            occurrence_key=occurrence_key,
            channel=record.channel,
        ).first()
        if existing is not None:
            equal = (
                existing.track_id == track_id
                and existing.status == restored_status
                and _portable_equal(existing.scheduled_at, record.scheduled_at)
                and existing.attempt_count == record.attempt_count
                and existing.next_attempt_at is None
                and _portable_equal(existing.sent_at, record.sent_at)
                and _portable_equal(existing.read_at, record.read_at)
                and existing.last_error_code == restored_error
                and existing.version == record.version
                and existing.lease_until is None
            )
            outcome = _classify_existing(equal)
            refs["reminder_deliveries"][record.backup_ref] = existing.id
            _persist_import_map(
                session, user_id, backup_id,
                "reminder_deliveries", record.backup_ref, existing.id,
            )
            counts["reminder_deliveries"][outcome] += 1
            if outcome == "conflicts":
                warnings.append(_restore_warning(
                    "destination_record_preserved",
                    section="reminder_deliveries",
                    backup_ref=record.backup_ref,
                ))
            continue

        item = ReminderDelivery(
            user_id=user_id,
            track_id=track_id,
            occurrence_key=occurrence_key,
            channel=record.channel,
            status=restored_status,
            scheduled_at=_parse_backup_datetime(record.scheduled_at),
            lease_until=None,
            attempt_count=record.attempt_count,
            next_attempt_at=None,
            sent_at=_parse_backup_datetime(record.sent_at),
            read_at=_parse_backup_datetime(record.read_at),
            last_error_code=restored_error,
            version=record.version,
        )
        session.add(item)
        session.flush()
        refs["reminder_deliveries"][record.backup_ref] = item.id
        _persist_import_map(
            session, user_id, backup_id,
            "reminder_deliveries", record.backup_ref, item.id,
        )
        counts["reminder_deliveries"]["created"] += 1
        if record.status == "pending":
            warnings.append(_restore_warning(
                "reminder_delivery_restored_paused",
                section="reminder_deliveries",
                backup_ref=record.backup_ref,
            ))
        elif record.status == "sending":
            warnings.append(_restore_warning(
                "reminder_delivery_restored_unknown",
                section="reminder_deliveries",
                backup_ref=record.backup_ref,
            ))

    if document.sections.document_versions or document.sections.application_documents:
        for _record in document.sections.document_versions:
            counts["document_versions"]["skipped"] += 1
        for _record in document.sections.application_documents:
            counts["application_documents"]["skipped"] += 1
        warnings.append(_restore_warning("document_bytes_excluded"))

    for record in document.sections.application_evidence:
        mapped = _mapped_target(
            session, user_id, backup_id,
            "application_evidence", record.backup_ref, ApplicationEvidence,
        )
        if mapped is not None:
            refs["application_evidence"][record.backup_ref] = mapped.id
            counts["application_evidence"]["skipped"] += 1
            continue

        track_id = _target_id(
            refs, "job_tracks", record.track_ref,
            "application_evidence", record.backup_ref,
        )
        item = ApplicationEvidence(
            user_id=user_id,
            track_id=track_id,
            kind=record.kind,
            body=record.body,
            occurred_at=_parse_backup_datetime(record.occurred_at),
            created_at=_parse_backup_datetime(record.created_at),
            updated_at=_parse_backup_datetime(record.updated_at),
            version=record.version,
            is_deleted=record.is_deleted,
        )
        session.add(item)
        session.flush()
        refs["application_evidence"][record.backup_ref] = item.id
        _persist_import_map(
            session, user_id, backup_id,
            "application_evidence", record.backup_ref, item.id,
        )
        counts["application_evidence"]["created"] += 1

    for record in document.sections.evidence_recovery:
        mapped = _mapped_target(
            session, user_id, backup_id,
            "evidence_recovery", record.backup_ref, ApplicationEvidence,
        )
        if mapped is not None:
            refs["evidence_recovery"][record.backup_ref] = mapped.id
            counts["evidence_recovery"]["skipped"] += 1
            continue

        evidence_id = _target_id(
            refs, "application_evidence", record.evidence_ref,
            "evidence_recovery", record.backup_ref,
        )
        evidence = session.query(ApplicationEvidence).filter(
            ApplicationEvidence.id == evidence_id,
            ApplicationEvidence.user_id == user_id,
        ).one()
        purge_at = _parse_backup_datetime(record.body_purge_at)
        if purge_at is not None and purge_at > datetime.utcnow():
            if not evidence.is_deleted:
                raise BackupContractError(
                    "conflicting_reference_graph",
                    409,
                    "Recovery body may target only soft-deleted evidence.",
                    section="evidence_recovery",
                    backup_ref=record.backup_ref,
                )
            deleted_at = evidence.updated_at
            session.execute(
                update(ApplicationEvidence)
                .where(ApplicationEvidence.id == evidence.id)
                .values(body=record.body, updated_at=deleted_at)
                .execution_options(synchronize_session=False)
            )
            # Restoring recovery content must not extend the original deadline.
            session.expire(evidence)
            counts["evidence_recovery"]["created"] += 1
        else:
            counts["evidence_recovery"]["skipped"] += 1
        refs["evidence_recovery"][record.backup_ref] = evidence.id
        _persist_import_map(
            session, user_id, backup_id,
            "evidence_recovery", record.backup_ref, evidence.id,
        )

    for record in document.sections.company_aliases:
        mapped = _mapped_target(
            session,
            user_id,
            backup_id,
            "company_aliases",
            record.backup_ref,
            CompanyAlias,
        )
        if mapped is not None:
            refs["company_aliases"][record.backup_ref] = mapped.id
            counts["company_aliases"]["skipped"] += 1
            continue

        existing = session.query(CompanyAlias).filter_by(
            user_id=user_id, alias_key=record.alias_key
        ).first()
        if existing is not None:
            fields = ("alias_key", "display_name", "company_key", "created_at")
            outcome = _classify_existing(_record_equal(existing, record, fields))
            refs["company_aliases"][record.backup_ref] = existing.id
            _persist_import_map(
                session,
                user_id,
                backup_id,
                "company_aliases",
                record.backup_ref,
                existing.id,
            )
            counts["company_aliases"][outcome] += 1
            if outcome == "conflicts":
                warnings.append(_restore_warning(
                    "destination_record_preserved",
                    section="company_aliases",
                    backup_ref=record.backup_ref,
                ))
            continue

        item = CompanyAlias(
            user_id=user_id,
            alias_key=record.alias_key,
            display_name=record.display_name,
            company_key=record.company_key,
            created_at=_parse_backup_datetime(record.created_at),
        )
        session.add(item)
        session.flush()
        refs["company_aliases"][record.backup_ref] = item.id
        _persist_import_map(
            session,
            user_id,
            backup_id,
            "company_aliases",
            record.backup_ref,
            item.id,
        )
        counts["company_aliases"]["created"] += 1

    for record in document.sections.work_items:
        mapped = _mapped_target(
            session, user_id, backup_id, "work_items", record.backup_ref, WorkItem
        )
        if mapped is not None:
            refs["work_items"][record.backup_ref] = mapped.id
            counts["work_items"]["skipped"] += 1
            continue

        origin_key = _restored_origin_key(record, refs)
        track_id = _target_id(
            refs, "job_tracks", record.track_ref, "work_items", record.backup_ref
        )
        row_id = _target_id(
            refs, "csv_rows", record.row_ref, "work_items", record.backup_ref
        )
        source_view_id = _target_id(
            refs, "saved_views", record.source_view_ref, "work_items", record.backup_ref
        )
        existing = (
            session.query(WorkItem).filter_by(user_id=user_id, origin_key=origin_key).first()
            if origin_key is not None
            else None
        )
        if existing is not None:
            fields = (
                "description", "due_at", "priority", "state", "version",
                "created_at", "updated_at", "completed_at",
            )
            equal = (
                _record_equal(existing, record, fields)
                and existing.track_id == track_id
                and existing.row_id == row_id
                and existing.source_view_id == source_view_id
            )
            outcome = _classify_existing(equal)
            refs["work_items"][record.backup_ref] = existing.id
            _persist_import_map(
                session, user_id, backup_id, "work_items", record.backup_ref, existing.id
            )
            counts["work_items"][outcome] += 1
            if outcome == "conflicts":
                warnings.append(_restore_warning(
                    "destination_record_preserved",
                    section="work_items",
                    backup_ref=record.backup_ref,
                ))
            continue

        item = WorkItem(
            user_id=user_id,
            track_id=track_id,
            row_id=row_id,
            source_view_id=source_view_id,
            origin_key=origin_key,
            description=record.description,
            due_at=datetime.fromisoformat(record.due_at.replace("Z", "+00:00"))
            if record.due_at is not None else None,
            priority=record.priority,
            state=record.state,
            version=record.version,
            created_at=datetime.fromisoformat(record.created_at.replace("Z", "+00:00")),
            updated_at=datetime.fromisoformat(record.updated_at.replace("Z", "+00:00")),
            completed_at=datetime.fromisoformat(record.completed_at.replace("Z", "+00:00"))
            if record.completed_at is not None else None,
        )
        session.add(item)
        session.flush()
        refs["work_items"][record.backup_ref] = item.id
        _persist_import_map(
            session, user_id, backup_id, "work_items", record.backup_ref, item.id
        )
        counts["work_items"]["created"] += 1

    for record in document.sections.work_item_overrides:
        action_key = _override_action_key_from_refs(record, refs)
        existing = session.query(WorkItemOverride).filter_by(
            user_id=user_id, action_key=action_key
        ).first()
        if existing is not None:
            equal = (
                _portable_equal(existing.snoozed_until, record.snoozed_until)
                and existing.version == record.version
            )
            outcome = _classify_existing(equal)
            counts["work_item_overrides"][outcome] += 1
            if outcome == "conflicts":
                warnings.append(_restore_warning(
                    "destination_record_preserved",
                    section="work_item_overrides",
                    backup_ref=record.backup_ref,
                ))
            continue
        session.add(WorkItemOverride(
            user_id=user_id,
            action_key=action_key,
            snoozed_until=datetime.fromisoformat(record.snoozed_until.replace("Z", "+00:00")),
            version=record.version,
        ))
        session.flush()
        counts["work_item_overrides"]["created"] += 1

    for record in document.sections.lifecycle_events:
        mapped = _mapped_target(
            session, user_id, backup_id,
            "lifecycle_events", record.backup_ref, JobLifecycleEvent,
        )
        if mapped is not None:
            refs["lifecycle_events"][record.backup_ref] = mapped.id
            counts["lifecycle_events"]["skipped"] += 1
            continue

        csv_row_id = _target_id(
            refs, "csv_rows", record.csv_row_ref,
            "lifecycle_events", record.backup_ref,
        )
        job_track_id = _target_id(
            refs, "job_tracks", record.job_track_ref,
            "lifecycle_events", record.backup_ref,
        )
        payload = dict(record.payload)
        if record.evidence_ref is not None:
            payload["evidence_id"] = _target_id(
                refs, "application_evidence", record.evidence_ref,
                "lifecycle_events", record.backup_ref,
            )
        if record.correction_of_ref is not None:
            payload["correction_of"] = _target_id(
                refs, "lifecycle_events", record.correction_of_ref,
                "lifecycle_events", record.backup_ref,
            )
        existing = session.query(JobLifecycleEvent).filter_by(
            user_id=user_id, event_key=record.event_key
        ).first()
        if existing is not None:
            portable_fields = (
                "event_key", "job_url", "kind", "occurred_at",
                "recorded_at", "source",
            )
            equal = (
                _record_equal(existing, record, portable_fields)
                and existing.payload == payload
                and existing.csv_row_id == csv_row_id
                and existing.job_track_id == job_track_id
            )
            outcome = _classify_existing(equal)
            refs["lifecycle_events"][record.backup_ref] = existing.id
            _persist_import_map(
                session, user_id, backup_id,
                "lifecycle_events", record.backup_ref, existing.id,
            )
            counts["lifecycle_events"][outcome] += 1
            if outcome == "conflicts":
                warnings.append(_restore_warning(
                    "destination_record_preserved",
                    section="lifecycle_events",
                    backup_ref=record.backup_ref,
                ))
            continue

        item = JobLifecycleEvent(
            user_id=user_id,
            event_key=record.event_key,
            job_url=record.job_url,
            csv_row_id=csv_row_id,
            job_track_id=job_track_id,
            kind=record.kind,
            occurred_at=_parse_backup_datetime(record.occurred_at),
            recorded_at=_parse_backup_datetime(record.recorded_at),
            source=record.source,
            payload=payload,
        )
        # Restore inserts the historical ledger record directly. It must not call
        # lifecycle.write_event(), because restoring rows/tracks is not a new visit
        # or application action.
        session.add(item)
        session.flush()
        refs["lifecycle_events"][record.backup_ref] = item.id
        _persist_import_map(
            session, user_id, backup_id,
            "lifecycle_events", record.backup_ref, item.id,
        )
        counts["lifecycle_events"]["created"] += 1

    for record in document.sections.applypilot_batches:
        mapped = _mapped_target(session, user_id, backup_id, "applypilot_batches", record.backup_ref, ApplyPilotBatch)
        if mapped is not None:
            refs["applypilot_batches"][record.backup_ref] = mapped.id
            counts["applypilot_batches"]["skipped"] += 1
            continue
        item = ApplyPilotBatch(
            user_id=user_id,
            session_id=_target_id(refs, "sessions", record.session_ref, "applypilot_batches", record.backup_ref),
            name=record.name,
            payload_json=record.payload_json,
            status=record.status,
            job_count=record.job_count,
            created_at=_parse_backup_datetime(record.created_at),
            updated_at=_parse_backup_datetime(record.updated_at),
        )
        session.add(item)
        session.flush()
        refs["applypilot_batches"][record.backup_ref] = item.id
        _persist_import_map(session, user_id, backup_id, "applypilot_batches", record.backup_ref, item.id)
        counts["applypilot_batches"]["created"] += 1

    for record in document.sections.audit_events:
        mapped = _mapped_target(session, user_id, backup_id, "audit_events", record.backup_ref, AuditEvent)
        if mapped is not None:
            refs["audit_events"][record.backup_ref] = mapped.id
            counts["audit_events"]["skipped"] += 1
            continue
        entity_id = None
        if record.entity_ref is not None:
            target_section = AUDIT_ENTITY_SECTION.get(record.entity_type)
            if target_section is None:
                raise BackupContractError(
                    "conflicting_reference_graph",
                    409,
                    "Audit event references an unsupported active entity type.",
                    section="audit_events",
                    backup_ref=record.backup_ref,
                )
            entity_id = _target_id(refs, target_section, record.entity_ref, "audit_events", record.backup_ref)
        metadata = dict(record.metadata_json or {})
        if record.entity_ref is None and record.legacy_entity_id is not None:
            metadata.setdefault("_backup_legacy_entity_id", record.legacy_entity_id)
            warnings.append(_restore_warning("legacy_entity_detached", section="audit_events", backup_ref=record.backup_ref))
        item = AuditEvent(
            user_id=user_id,
            session_id=_target_id(refs, "sessions", record.session_ref, "audit_events", record.backup_ref),
            event_type=record.event_type,
            entity_type=record.entity_type,
            entity_id=entity_id,
            metadata_json=metadata,
            created_at=_parse_backup_datetime(record.created_at),
        )
        session.add(item)
        session.flush()
        refs["audit_events"][record.backup_ref] = item.id
        _persist_import_map(session, user_id, backup_id, "audit_events", record.backup_ref, item.id)
        counts["audit_events"]["created"] += 1

    return {"counts": counts, "warnings": warnings}


def restore_backup_v2(db: Session, user_id: int, document: BackupDocumentV2, mode: str) -> dict[str, Any]:
    if mode not in {RESTORE_MODE_MERGE, RESTORE_MODE_VERIFY}:
        raise BackupContractError("invalid_restore_mode", 400, "Unsupported restore mode.")

    bind = db.get_bind()
    engine = getattr(bind, "engine", bind)
    restore_session = Session(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        if mode == RESTORE_MODE_VERIFY:
            with restore_session.begin():
                counts = _preflight_v2(restore_session, user_id, document)
            return {
                "backup_id": document.backup_id,
                "mode": mode,
                "counts": counts,
                "warnings": [],
                "verified": True,
            }

        with restore_session.begin():
            result = _restore_v2_transaction(restore_session, user_id, document)
        return {
            "backup_id": document.backup_id,
            "mode": mode,
            "counts": result["counts"],
            "warnings": result["warnings"],
            "verified": True,
        }
    except BackupContractError:
        restore_session.rollback()
        raise
    except Exception:
        restore_session.rollback()
        raise
    finally:
        restore_session.close()


def _legacy_backup_id(payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return str(uuid5(LEGACY_NAMESPACE, digest))


def _legacy_ref(backup_id: str, section: str, index: int) -> str:
    return str(uuid5(UUID(backup_id), f"legacy:{section}:{index}"))


def restore_backup_v1(db: Session, user_id: int, payload: dict[str, Any], mode: str) -> dict[str, Any]:
    legacy = adapt_v1_backup(payload)
    backup_id = _legacy_backup_id(payload)
    counts = _empty_restore_counts()
    warnings = [_restore_warning(code) for code in legacy.warnings]
    for section in sorted(legacy.absent_sections):
        warnings.append(_restore_warning("legacy_section_absent", section=section))

    bind = db.get_bind()
    engine = getattr(bind, "engine", bind)
    restore_session = Session(bind=engine, autoflush=False, expire_on_commit=False)

    def classify_or_apply(write: bool) -> None:
        restore_session.query(User).filter(User.id == user_id).with_for_update().one()
        refs: dict[str, dict[str, int]] = {section: {} for section in BACKUP_V2_SECTIONS}

        for index, legacy_record in enumerate(legacy.sections["sessions"]):
            data = legacy_record.data
            ref = _legacy_ref(backup_id, "sessions", index)
            mapping = _lookup_import_map(restore_session, user_id, backup_id, "sessions", ref)
            if mapping is not None:
                refs["sessions"][ref] = mapping.target_id
                counts["sessions"]["skipped"] += 1
                continue
            started_at = _parse_backup_datetime(data.get("started_at"))
            name = data.get("name")
            if not isinstance(name, str) or not name or started_at is None:
                counts["sessions"]["skipped"] += 1
                warnings.append(_restore_warning("legacy_record_not_restored", section="sessions", backup_ref=ref))
                continue
            counts["sessions"]["created"] += 1
            if write:
                item = SearchSession(
                    user_id=user_id,
                    name=name,
                    started_at=started_at,
                    ended_at=_parse_backup_datetime(data.get("ended_at")),
                    notes=data.get("notes"),
                )
                restore_session.add(item)
                restore_session.flush()
                refs["sessions"][ref] = item.id
                _persist_import_map(restore_session, user_id, backup_id, "sessions", ref, item.id)
            if legacy_record.missing_fields:
                warnings.append(_restore_warning("legacy_record_incomplete", section="sessions", backup_ref=ref))

        for index, legacy_record in enumerate(legacy.sections["csv_rows"]):
            data = legacy_record.data
            url = data.get("url")
            if not isinstance(url, str) or not url:
                raise BackupContractError("invalid_legacy_schema", 400, "Legacy CSV row requires a URL.", section="csv_rows")
            ref = _legacy_ref(backup_id, "csv_rows", index)
            mapping = _lookup_import_map(restore_session, user_id, backup_id, "csv_rows", ref)
            existing = restore_session.query(CsvRow).filter_by(user_id=user_id, url=url).first()
            if mapping is not None:
                refs["csv_rows"][ref] = mapping.target_id
                counts["csv_rows"]["skipped"] += 1
            elif existing is not None:
                refs["csv_rows"][ref] = existing.id
                counts["csv_rows"]["conflicts"] += 1
                if write:
                    _persist_import_map(restore_session, user_id, backup_id, "csv_rows", ref, existing.id)
            else:
                counts["csv_rows"]["created"] += 1
                if write:
                    values = {name: data.get(name) for name in CSV_ROW_TEXT_FIELDS if name in data}
                    item = CsvRow(
                        user_id=user_id,
                        upload_batch_id=f"legacy-{backup_id[:8]}",
                        created_at=_parse_backup_datetime(data.get("created_at")),
                        **values,
                    )
                    apply_persisted_job_identity(item)
                    restore_session.add(item)
                    restore_session.flush()
                    refs["csv_rows"][ref] = item.id
                    _persist_import_map(restore_session, user_id, backup_id, "csv_rows", ref, item.id)
            if legacy_record.missing_fields:
                warnings.append(_restore_warning("legacy_record_incomplete", section="csv_rows", backup_ref=ref))

        for index, legacy_record in enumerate(legacy.sections["job_tracks"]):
            data = legacy_record.data
            url = data.get("url")
            if not isinstance(url, str) or not url:
                raise BackupContractError("invalid_legacy_schema", 400, "Legacy application requires a URL.", section="job_tracks")
            ref = _legacy_ref(backup_id, "job_tracks", index)
            mapping = _lookup_import_map(restore_session, user_id, backup_id, "job_tracks", ref)
            existing = restore_session.query(JobTrack).filter_by(user_id=user_id, url=url).first()
            if mapping is not None:
                counts["job_tracks"]["skipped"] += 1
            elif existing is not None:
                counts["job_tracks"]["conflicts"] += 1
                if write:
                    _persist_import_map(restore_session, user_id, backup_id, "job_tracks", ref, existing.id)
            else:
                counts["job_tracks"]["created"] += 1
                if write:
                    status = data.get("status")
                    if not isinstance(status, str) or not status:
                        raise BackupContractError("invalid_legacy_schema", 400, "Legacy application requires status.", section="job_tracks")
                    created_at = _parse_backup_datetime(data.get("created_at"))
                    if created_at is None:
                        raise BackupContractError(
                            "invalid_legacy_schema",
                            400,
                            "Legacy application is missing created_at; restore will not fabricate history.",
                            section="job_tracks",
                            backup_ref=ref,
                        )
                    item = JobTrack(
                        user_id=user_id,
                        url=url,
                        company=data.get("company"),
                        title=data.get("title"),
                        status=status,
                        applied_at=_parse_backup_datetime(data.get("applied_at")),
                        follow_up_at=_parse_backup_datetime(data.get("follow_up_at")),
                        notes=data.get("notes"),
                        created_at=created_at,
                        updated_at=created_at,
                    )
                    apply_persisted_job_identity(item)
                    restore_session.add(item)
                    restore_session.flush()
                    _persist_import_map(restore_session, user_id, backup_id, "job_tracks", ref, item.id)
            if legacy_record.missing_fields:
                warnings.append(_restore_warning("legacy_record_incomplete", section="job_tracks", backup_ref=ref))

        for index, legacy_record in enumerate(legacy.sections["saved_views"]):
            data = legacy_record.data
            name = data.get("name")
            view_type = data.get("view_type")
            if not isinstance(name, str) or not isinstance(view_type, str) or not name or not view_type:
                raise BackupContractError("invalid_legacy_schema", 400, "Legacy saved view requires name and view_type.", section="saved_views")
            ref = _legacy_ref(backup_id, "saved_views", index)
            mapping = _lookup_import_map(restore_session, user_id, backup_id, "saved_views", ref)
            existing = restore_session.query(SavedView).filter_by(user_id=user_id, name=name, view_type=view_type).first()
            if mapping is not None:
                counts["saved_views"]["skipped"] += 1
            elif existing is not None:
                counts["saved_views"]["conflicts"] += 1
                if write:
                    _persist_import_map(restore_session, user_id, backup_id, "saved_views", ref, existing.id)
            else:
                counts["saved_views"]["created"] += 1
                if write:
                    item = SavedView(
                        user_id=user_id,
                        name=name,
                        view_type=view_type,
                        filters=data.get("filters") or {},
                        is_pinned=bool(data.get("is_pinned", False)),
                    )
                    restore_session.add(item)
                    restore_session.flush()
                    _persist_import_map(restore_session, user_id, backup_id, "saved_views", ref, item.id)

        for index, legacy_record in enumerate(legacy.sections["applypilot_batches"]):
            data = legacy_record.data
            ref = _legacy_ref(backup_id, "applypilot_batches", index)
            mapping = _lookup_import_map(restore_session, user_id, backup_id, "applypilot_batches", ref)
            if mapping is not None:
                counts["applypilot_batches"]["skipped"] += 1
                continue
            created_at = _parse_backup_datetime(data.get("created_at"))
            if created_at is None or "payload_json" not in data or not isinstance(data.get("status"), str):
                counts["applypilot_batches"]["skipped"] += 1
                warnings.append(_restore_warning("legacy_record_not_restored", section="applypilot_batches", backup_ref=ref))
                continue
            counts["applypilot_batches"]["created"] += 1
            if write:
                item = ApplyPilotBatch(
                    user_id=user_id,
                    session_id=None,
                    name=data.get("name"),
                    payload_json=data.get("payload_json"),
                    status=data.get("status"),
                    job_count=data.get("job_count") or 0,
                    created_at=created_at,
                    updated_at=None,
                )
                restore_session.add(item)
                restore_session.flush()
                _persist_import_map(restore_session, user_id, backup_id, "applypilot_batches", ref, item.id)
            warnings.append(_restore_warning("legacy_relationships_detached", section="applypilot_batches", backup_ref=ref))

        for index, legacy_record in enumerate(legacy.sections["audit_events"]):
            data = legacy_record.data
            ref = _legacy_ref(backup_id, "audit_events", index)
            mapping = _lookup_import_map(restore_session, user_id, backup_id, "audit_events", ref)
            if mapping is not None:
                counts["audit_events"]["skipped"] += 1
                continue
            created_at = _parse_backup_datetime(data.get("created_at"))
            event_type = data.get("event_type")
            entity_type = data.get("entity_type")
            if created_at is None or not isinstance(event_type, str) or not isinstance(entity_type, str):
                counts["audit_events"]["skipped"] += 1
                warnings.append(_restore_warning("legacy_record_not_restored", section="audit_events", backup_ref=ref))
                continue
            counts["audit_events"]["created"] += 1
            if write:
                metadata = dict(data.get("metadata_json") or {})
                if data.get("entity_id") is not None:
                    metadata.setdefault("_backup_legacy_entity_id", data.get("entity_id"))
                item = AuditEvent(
                    user_id=user_id,
                    session_id=None,
                    event_type=event_type,
                    entity_type=entity_type,
                    entity_id=None,
                    metadata_json=metadata,
                    created_at=created_at,
                )
                restore_session.add(item)
                restore_session.flush()
                _persist_import_map(restore_session, user_id, backup_id, "audit_events", ref, item.id)
            warnings.append(_restore_warning("legacy_relationships_detached", section="audit_events", backup_ref=ref))

    try:
        if mode == RESTORE_MODE_VERIFY:
            with restore_session.begin():
                classify_or_apply(False)
        elif mode == RESTORE_MODE_MERGE:
            with restore_session.begin():
                classify_or_apply(True)
        else:
            raise BackupContractError("invalid_restore_mode", 400, "Unsupported restore mode.")
        return {
            "backup_id": backup_id,
            "mode": mode,
            "counts": counts,
            "warnings": warnings,
            "verified": True,
        }
    except BackupContractError:
        restore_session.rollback()
        raise
    except Exception:
        restore_session.rollback()
        raise
    finally:
        restore_session.close()


def restore_backup_payload(db: Session, user_id: int, raw: bytes, mode: str) -> dict[str, Any]:
    """Parse once for version routing, fully validate, then preflight or restore."""
    payload = parse_backup_json(raw)
    if not isinstance(payload, dict):
        raise BackupContractError("invalid_schema", 400, "Backup root must be a JSON object.")
    version = str(payload.get("version", ""))
    if version == "2.0":
        document = validate_backup_v2(payload)
        return restore_backup_v2(db, user_id, document, mode)
    if version in {"1", "1.0"}:
        return restore_backup_v1(db, user_id, payload, mode)
    raise BackupContractError("unsupported_backup_version", 400, "Unsupported backup version.")
