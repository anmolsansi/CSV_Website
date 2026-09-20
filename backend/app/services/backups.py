from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4, uuid5

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
    ApplyPilotBatch,
    AuditEvent,
    BackupImportMap,
    ColumnPreference,
    CsvRow,
    JobTrack,
    JobLifecycleEvent,
    SavedView,
    SearchSession,
    UrlHistory,
    User,
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
        "lifecycle_events": session.query(JobLifecycleEvent).filter(JobLifecycleEvent.user_id == user_id).order_by(JobLifecycleEvent.id.asc()).all(),
        "saved_views": session.query(SavedView).filter(SavedView.user_id == user_id).order_by(SavedView.id.asc()).all(),
        "sessions": session.query(SearchSession).filter(SearchSession.user_id == user_id).order_by(SearchSession.id.asc()).all(),
        "audit_events": session.query(AuditEvent).filter(AuditEvent.user_id == user_id).order_by(AuditEvent.id.asc()).all(),
        "applypilot_batches": session.query(ApplyPilotBatch).filter(ApplyPilotBatch.user_id == user_id).order_by(ApplyPilotBatch.id.asc()).all(),
        "column_preferences": session.query(ColumnPreference).filter(ColumnPreference.user_id == user_id).all(),
        "user_goal": session.query(UserGoal).filter(UserGoal.user_id == user_id).all(),
        "user_profile": session.query(User).filter(User.id == user_id).all(),
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

    for item in snapshot["lifecycle_events"]:
        backup_ref = refs["lifecycle_events"][item.id]
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
            "kind": item.kind,
            "occurred_at": _utc_iso(item.occurred_at),
            "recorded_at": _utc_iso(item.recorded_at),
            "source": item.source,
            "payload": item.payload,
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
        return actual == _parse_backup_datetime(expected)
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


def _preflight_v2(session: Session, user_id: int, document: BackupDocumentV2) -> dict[str, dict[str, int]]:
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
            user_id=user_id,
            name=record.name,
            view_type=record.view_type,
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
        mapping = _lookup_import_map(
            session, user_id, backup_id, "user_profile", record.backup_ref
        )
        if mapping:
            counts["user_profile"]["skipped"] += 1
            continue
        # A first restore creates the portable profile mapping even when the
        # destination already has the same default timezone. Replays are skipped
        # through BackupImportMap, matching every other portable section.
        counts["user_profile"]["created"] += 1

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

    for record in document.sections.lifecycle_events:
        mapping = _lookup_import_map(
            session, user_id, backup_id, "lifecycle_events", record.backup_ref
        )
        if mapping:
            counts["lifecycle_events"]["skipped"] += 1
            continue
        existing = session.query(JobLifecycleEvent).filter_by(
            user_id=user_id, event_key=record.event_key
        ).first()
        if existing is None:
            counts["lifecycle_events"]["created"] += 1
        else:
            fields = (
                "event_key", "job_url", "kind", "occurred_at",
                "recorded_at", "source", "payload",
            )
            counts["lifecycle_events"][
                _classify_existing(_record_equal(existing, record, fields))
            ] += 1

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
            refs["csv_rows"][record.backup_ref] = mapped.id
            counts["csv_rows"]["skipped"] += 1
            continue
        existing = session.query(CsvRow).filter_by(user_id=user_id, url=record.url).first()
        if existing is not None:
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

    for record in document.sections.job_tracks:
        mapped = _mapped_target(session, user_id, backup_id, "job_tracks", record.backup_ref, JobTrack)
        if mapped is not None:
            refs["job_tracks"][record.backup_ref] = mapped.id
            counts["job_tracks"]["skipped"] += 1
            continue
        existing = session.query(JobTrack).filter_by(user_id=user_id, url=record.url).first()
        if existing is not None:
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
        session.add(item)
        session.flush()
        refs["job_tracks"][record.backup_ref] = item.id
        _persist_import_map(session, user_id, backup_id, "job_tracks", record.backup_ref, item.id)
        counts["job_tracks"]["created"] += 1
        if record.session_ref is not None:
            warnings.append(_restore_warning("job_track_session_ref_detached", section="job_tracks", backup_ref=record.backup_ref))

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
        existing = session.query(JobLifecycleEvent).filter_by(
            user_id=user_id, event_key=record.event_key
        ).first()
        if existing is not None:
            portable_fields = (
                "event_key", "job_url", "kind", "occurred_at",
                "recorded_at", "source", "payload",
            )
            equal = (
                _record_equal(existing, record, portable_fields)
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
            payload=record.payload,
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
