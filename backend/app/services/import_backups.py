from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from ..backup_schemas import BackupContractError, parse_backup_json
from ..import_models import ImportMapping
from ..undo_models import BulkAction
from .contact_backups import (
    export_backup_v2_with_contacts,
    restore_backup_payload_with_contacts,
)
from .undo_foundation import serialize_bulk_action_metadata_for_backup


F9_BACKUP_SCHEMA_REVISION = "1.0.0"
F9_BACKUP_KEY = "f9_import_mappings"
F10_BACKUP_SCHEMA_REVISION = "1.0.0"
F10_BACKUP_KEY = "f10_bulk_action_metadata"


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _checksum(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def export_backup_v2_with_import_mappings(db: Session, user_id: int) -> dict[str, Any]:
    """Extend portable v2 backup with mappings and non-actionable F10 metadata.

    Transient uploaded previews, rejected rows, and F10 before-images are never
    exported. Restored F10 records are audit metadata only and cannot be undone.
    """
    payload = export_backup_v2_with_contacts(db, user_id)
    mappings = (
        db.query(ImportMapping)
        .filter(ImportMapping.user_id == user_id)
        .order_by(ImportMapping.id.asc())
        .all()
    )
    if mappings:
        extension = {
            "schema_revision": F9_BACKUP_SCHEMA_REVISION,
            "mappings": [
                {
                    "name": item.name,
                    "header_fingerprint": item.header_fingerprint,
                    "mapping_json": item.mapping_json,
                    "version": item.version,
                }
                for item in mappings
            ],
        }
        extension["checksum_sha256"] = _checksum(extension)
        payload[F9_BACKUP_KEY] = extension

    action_metadata = serialize_bulk_action_metadata_for_backup(
        db,
        user_id=user_id,
    )
    if action_metadata:
        undo_extension = {
            "schema_revision": F10_BACKUP_SCHEMA_REVISION,
            "actions": action_metadata,
        }
        undo_extension["checksum_sha256"] = _checksum(undo_extension)
        payload[F10_BACKUP_KEY] = undo_extension
    return payload


def _validate_extension(extension: Any) -> list[dict[str, Any]]:
    if not isinstance(extension, dict):
        raise BackupContractError(
            "invalid_f9_backup",
            400,
            "F9 import-mapping backup extension must be an object.",
        )
    if set(extension) != {"schema_revision", "mappings", "checksum_sha256"}:
        raise BackupContractError(
            "invalid_f9_backup",
            400,
            "F9 import-mapping backup extension has unknown fields.",
        )
    if extension.get("schema_revision") != F9_BACKUP_SCHEMA_REVISION:
        raise BackupContractError(
            "invalid_f9_backup",
            400,
            "F9 import-mapping backup extension has an unsupported schema revision.",
        )
    mappings = extension.get("mappings")
    if not isinstance(mappings, list):
        raise BackupContractError(
            "invalid_f9_backup",
            400,
            "F9 import mappings must be a list.",
        )
    signed = {
        "schema_revision": extension["schema_revision"],
        "mappings": mappings,
    }
    if extension.get("checksum_sha256") != _checksum(signed):
        raise BackupContractError(
            "checksum_mismatch",
            400,
            "F9 import-mapping backup checksum does not match its contents.",
        )

    seen_names: set[str] = set()
    for index, item in enumerate(mappings):
        if not isinstance(item, dict) or set(item) != {
            "name",
            "header_fingerprint",
            "mapping_json",
            "version",
        }:
            raise BackupContractError(
                "invalid_f9_backup",
                400,
                f"F9 mapping at index {index} has an invalid shape.",
            )
        name = item.get("name")
        fingerprint = item.get("header_fingerprint")
        mapping_json = item.get("mapping_json")
        version = item.get("version")
        if not isinstance(name, str) or not 1 <= len(name) <= 100 or name in seen_names:
            raise BackupContractError(
                "invalid_f9_backup",
                400,
                "F9 mapping names must be unique strings of at most 100 characters.",
            )
        if not isinstance(fingerprint, str) or len(fingerprint) != 64:
            raise BackupContractError(
                "invalid_f9_backup",
                400,
                "F9 mapping header fingerprint must be a 64-character SHA-256 value.",
            )
        if not isinstance(mapping_json, dict) or not mapping_json:
            raise BackupContractError(
                "invalid_f9_backup",
                400,
                "F9 mapping payload must be a non-empty object.",
            )
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise BackupContractError(
                "invalid_f9_backup",
                400,
                "F9 mapping version must be a positive integer.",
            )
        seen_names.add(name)
    return mappings


def _validate_f10_extension(extension: Any) -> list[dict[str, Any]]:
    if not isinstance(extension, dict) or set(extension) != {
        "schema_revision", "actions", "checksum_sha256"
    }:
        raise BackupContractError(
            "invalid_f10_backup",
            400,
            "F10 bulk-action metadata extension has an invalid shape.",
        )
    if extension.get("schema_revision") != F10_BACKUP_SCHEMA_REVISION:
        raise BackupContractError(
            "invalid_f10_backup",
            400,
            "F10 bulk-action metadata extension has an unsupported schema revision.",
        )
    actions = extension.get("actions")
    if not isinstance(actions, list):
        raise BackupContractError(
            "invalid_f10_backup",
            400,
            "F10 bulk-action metadata must be a list.",
        )
    signed = {
        "schema_revision": extension["schema_revision"],
        "actions": actions,
    }
    if extension.get("checksum_sha256") != _checksum(signed):
        raise BackupContractError(
            "checksum_mismatch",
            400,
            "F10 bulk-action metadata checksum does not match its contents.",
        )

    seen_keys: set[str] = set()
    expected = {
        "id", "kind", "request_key", "status", "created_at",
        "undo_expires_at", "result_json", "effect_count", "undo_available",
    }
    for index, item in enumerate(actions):
        if not isinstance(item, dict) or set(item) != expected:
            raise BackupContractError(
                "invalid_f10_backup",
                400,
                f"F10 action metadata at index {index} has an invalid shape.",
            )
        if item.get("undo_available") is not False:
            raise BackupContractError(
                "invalid_f10_backup",
                400,
                "Portable bulk-action metadata must never advertise Undo as actionable.",
            )
        request_key = item.get("request_key")
        if not isinstance(request_key, str) or len(request_key) != 36 or request_key in seen_keys:
            raise BackupContractError(
                "invalid_f10_backup",
                400,
                "F10 request keys must be unique canonical UUID strings.",
            )
        if item.get("kind") not in {"archive_rows", "update_rows", "update_tracks"}:
            raise BackupContractError("invalid_f10_backup", 400, "F10 action kind is invalid.")
        if not isinstance(item.get("result_json"), dict):
            raise BackupContractError("invalid_f10_backup", 400, "F10 result metadata must be an object.")
        try:
            datetime.fromisoformat(str(item.get("created_at")))
            datetime.fromisoformat(str(item.get("undo_expires_at")))
        except ValueError as exc:
            raise BackupContractError(
                "invalid_f10_backup",
                400,
                "F10 action timestamps must be ISO-8601 values.",
            ) from exc
        seen_keys.add(request_key)
    return actions


def restore_backup_payload_with_import_mappings(
    db: Session,
    user_id: int,
    raw: bytes,
    mode: str,
) -> dict[str, Any]:
    parsed = parse_backup_json(raw)
    if not isinstance(parsed, dict):
        raise BackupContractError("invalid_backup", 400, "Backup document must be an object.")
    extension = parsed.pop(F9_BACKUP_KEY, None)
    f10_extension = parsed.pop(F10_BACKUP_KEY, None)
    mappings = _validate_extension(extension) if extension is not None else []
    actions = _validate_f10_extension(f10_extension) if f10_extension is not None else []

    # Detect conflicts before delegating to the established portable restore.
    existing_by_name = {
        item.name: item
        for item in db.query(ImportMapping).filter(ImportMapping.user_id == user_id).all()
    }
    for record in mappings:
        existing = existing_by_name.get(record["name"])
        if existing is None:
            continue
        if (
            existing.header_fingerprint != record["header_fingerprint"]
            or existing.mapping_json != record["mapping_json"]
        ):
            raise BackupContractError(
                "restore_conflict",
                409,
                "A saved import mapping with the same name has different content.",
                section="import_mappings",
            )

    existing_actions = {
        item.request_key: item
        for item in db.query(BulkAction).filter(BulkAction.user_id == user_id).all()
    }
    for record in actions:
        existing = existing_actions.get(record["request_key"])
        if existing is not None and existing.kind != record["kind"]:
            raise BackupContractError(
                "restore_conflict",
                409,
                "A bulk-action metadata record with the same operation key has different content.",
                section="bulk_action_metadata",
            )

    base_raw = json.dumps(parsed, ensure_ascii=False, allow_nan=False).encode("utf-8")
    result = restore_backup_payload_with_contacts(db, user_id, base_raw, mode)

    if extension is not None:
        existing_count = sum(1 for record in mappings if record["name"] in existing_by_name)
        if mode == "verify_only":
            result["counts"]["import_mappings"] = {
                "created": 0,
                "existing": existing_count,
            }
        else:
            created = 0
            for record in mappings:
                if record["name"] in existing_by_name:
                    continue
                mapping = ImportMapping(
                    user_id=user_id,
                    name=record["name"],
                    header_fingerprint=record["header_fingerprint"],
                    mapping_json=record["mapping_json"],
                    version=max(int(record.get("version", 1)), 1),
                )
                db.add(mapping)
                created += 1
            result["counts"]["import_mappings"] = {
                "created": created,
                "existing": existing_count,
            }

    if f10_extension is not None:
        existing_count = sum(1 for record in actions if record["request_key"] in existing_actions)
        if mode == "verify_only":
            result["counts"]["bulk_action_metadata"] = {
                "created": 0,
                "existing": existing_count,
            }
        else:
            created = 0
            for record in actions:
                if record["request_key"] in existing_actions:
                    continue
                source_result = dict(record.get("result_json") or {})
                source_result.update({
                    "restored_non_actionable": True,
                    "source_effect_count": int(record.get("effect_count") or 0),
                })
                db.add(BulkAction(
                    user_id=user_id,
                    kind=record["kind"],
                    request_key=record["request_key"],
                    status="expired",
                    created_at=datetime.fromisoformat(record["created_at"]),
                    undo_expires_at=datetime.fromisoformat(record["undo_expires_at"]),
                    result_json=source_result,
                ))
                created += 1
            result["counts"]["bulk_action_metadata"] = {
                "created": created,
                "existing": existing_count,
            }

    if mode != "verify_only":
        db.commit()
    return result
