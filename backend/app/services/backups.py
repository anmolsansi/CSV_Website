from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4, uuid5

from sqlalchemy.orm import Session

from ..backup_schemas import (
    AUDIT_ENTITY_SECTION,
    BACKUP_SCHEMA_REVISION,
    BACKUP_V2_SECTIONS,
    CSV_ROW_TEXT_FIELDS,
    BackupContractError,
    compute_sections_checksum,
    validate_backup_v2,
)
from ..models import (
    ApplyPilotBatch,
    AuditEvent,
    ColumnPreference,
    CsvRow,
    JobTrack,
    SavedView,
    SearchSession,
    UrlHistory,
    UserGoal,
)


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
    return {
        "csv_rows": session.query(CsvRow).filter(CsvRow.user_id == user_id).order_by(CsvRow.id.asc()).all(),
        "url_history": session.query(UrlHistory).filter(UrlHistory.user_id == user_id).order_by(UrlHistory.id.asc()).all(),
        "job_tracks": session.query(JobTrack).filter(JobTrack.user_id == user_id).order_by(JobTrack.id.asc()).all(),
        "saved_views": session.query(SavedView).filter(SavedView.user_id == user_id).order_by(SavedView.id.asc()).all(),
        "sessions": session.query(SearchSession).filter(SearchSession.user_id == user_id).order_by(SearchSession.id.asc()).all(),
        "audit_events": session.query(AuditEvent).filter(AuditEvent.user_id == user_id).order_by(AuditEvent.id.asc()).all(),
        "applypilot_batches": session.query(ApplyPilotBatch).filter(ApplyPilotBatch.user_id == user_id).order_by(ApplyPilotBatch.id.asc()).all(),
        "column_preferences": session.query(ColumnPreference).filter(ColumnPreference.user_id == user_id).all(),
        "user_goal": session.query(UserGoal).filter(UserGoal.user_id == user_id).all(),
    }


def _ref_maps(snapshot: dict[str, list[Any]], backup_id: UUID) -> dict[str, dict[int, str]]:
    refs: dict[str, dict[int, str]] = {}
    for section in BACKUP_V2_SECTIONS:
        section_refs: dict[int, str] = {}
        for item in snapshot[section]:
            source_key = getattr(item, "id", getattr(item, "user_id", None))
            if source_key is None:
                raise BackupContractError(
                    "invalid_export_identity",
                    409,
                    "A record in the export snapshot has no stable source identity.",
                    section=section,
                )
            section_refs[int(source_key)] = _backup_ref(backup_id, section, source_key)
        refs[section] = section_refs
    return refs


def _serialize_sections(
    snapshot: dict[str, list[Any]],
    refs: dict[str, dict[int, str]],
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
