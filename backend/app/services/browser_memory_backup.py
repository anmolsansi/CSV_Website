"""Compose private browser visits into the existing portable backup pipeline.

Visit evidence is separate from CSV import/click/application state and is
owned by the authenticated destination user after restore. No receipts,
cookie state, extension settings, or rate counters are exported.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy.orm import Session

from ..backup_schemas import BackupContractError, MAX_BACKUP_JSON_BYTES, canonical_json_bytes, parse_backup_json
from ..browser_memory_backup_schemas import (
    VISIT_BACKUP_KEY, MAX_PORTABLE_VISITS, build_visit_extension,
    validate_visit_extension,
)
from ..models import JobVisit
from .backup_sessions import atomic_restore, snapshot_export
from .import_backups import (
    _check_record_limit, export_backup_v2_with_import_mappings,
    restore_backup_payload_with_import_mappings,
)


def _utc_z(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@snapshot_export
def export_backup_v2_with_browser_visits(db: Session, user_id: int) -> dict[str, Any]:
    """Append optional checksummed visits from the SAME owner snapshot as v2."""
    payload = export_backup_v2_with_import_mappings(db, user_id)
    visits = (
        db.query(JobVisit)
        .filter(JobVisit.user_id == user_id)
        .order_by(JobVisit.canonical_url_hash, JobVisit.id)
        .all()
    )
    if len(visits) > MAX_PORTABLE_VISITS:
        raise BackupContractError(
            "too_many_visits", 413,
            "Account has more than 10,000 visits and cannot be exported.",
            section=VISIT_BACKUP_KEY,
        )
    if visits:
        backup_id = UUID(payload["backup_id"])
        payload[VISIT_BACKUP_KEY] = build_visit_extension([
            {
                "backup_ref": str(uuid5(backup_id, f"job_visits:{visit.id}")),
                "canonical_url": visit.canonical_url,
                "canonical_url_hash": visit.canonical_url_hash,
                "first_visited_at": _utc_z(visit.first_visited_at),
            }
            for visit in visits
        ])
    _check_record_limit(payload)
    if len(canonical_json_bytes(payload)) > MAX_BACKUP_JSON_BYTES:
        raise BackupContractError(
            "backup_too_large", 413,
            "Portable metadata exceeds the 20 MiB JSON limit.",
        )
    return payload


def _parse_utc_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)


@atomic_restore
def restore_backup_payload_with_browser_visits(
    db: Session, user_id: int, raw: bytes, mode: str,
    *, _base_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Preflight visit extension before core writes, then commit with core graph."""
    payload = parse_backup_json(raw)
    if not isinstance(payload, dict):
        raise BackupContractError("invalid_backup", 400, "Backup must be a JSON object.")
    extension = payload.pop(VISIT_BACKUP_KEY, None)
    if extension is not None and payload.get("version") != "2.0":
        raise BackupContractError(
            "unsupported_visit_backup_version", 400,
            "Browser visits require the portable v2 backup reader.",
            section=VISIT_BACKUP_KEY,
        )
    records = validate_visit_extension(extension) if extension is not None else []
    _check_record_limit({**payload, **({VISIT_BACKUP_KEY: extension} if extension is not None else {})})

    # The @atomic_restore wrapper holds the destination owner lock, so the
    # existing/added union is calculated inside the shared restore transaction.
    existing = {
        item.canonical_url_hash: item
        for item in db.query(JobVisit).filter(JobVisit.user_id == user_id).all()
    }
    incoming = {record["canonical_url_hash"]: record for record in records}
    for digest, record in incoming.items():
        found = existing.get(digest)
        if found is not None and found.canonical_url != record["canonical_url"]:
            raise BackupContractError(
                "visit_identity_conflict", 409,
                "A destination visit has a conflicting canonical identity.",
                section=VISIT_BACKUP_KEY,
            )
    new_count = sum(1 for digest in incoming if digest not in existing)
    if len(existing) + new_count > MAX_PORTABLE_VISITS:
        raise BackupContractError(
            "too_many_visits", 413,
            "Restored and existing visits together exceed the 10,000-record limit.",
            section=VISIT_BACKUP_KEY,
        )

    base_raw = canonical_json_bytes(payload)
    result = restore_backup_payload_with_import_mappings(
        db, user_id, base_raw, mode, _base_result=_base_result,
    )

    # Missing optional extension does not create fictional historical visits.
    if extension is None:
        return result
    result["counts"]["job_visits"] = {
        "created": new_count,
        "existing": len(records) - new_count,
    }
    if mode == "verify_only":
        return result

    for digest, record in incoming.items():
        observed = _parse_utc_timestamp(record["first_visited_at"])
        found = existing.get(digest)
        if found is None:
            db.add(JobVisit(
                user_id=user_id,
                canonical_url=record["canonical_url"],
                canonical_url_hash=digest,
                first_visited_at=observed,
            ))
        else:
            old = found.first_visited_at
            if old.tzinfo is not None:
                old = old.astimezone(timezone.utc).replace(tzinfo=None)
            if observed < old:
                found.first_visited_at = observed
    db.flush()
    return result
