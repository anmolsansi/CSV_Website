from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy.orm import Session

from ..backup_schemas import BackupContractError, parse_backup_json
from ..import_models import ImportMapping
from .contact_backups import (
    export_backup_v2_with_contacts,
    restore_backup_payload_with_contacts,
)


F9_BACKUP_SCHEMA_REVISION = "1.0.0"
F9_BACKUP_KEY = "f9_import_mappings"


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
    """Extend portable v2 backup with durable mappings, never uploaded previews."""
    payload = export_backup_v2_with_contacts(db, user_id)
    mappings = (
        db.query(ImportMapping)
        .filter(ImportMapping.user_id == user_id)
        .order_by(ImportMapping.id.asc())
        .all()
    )
    if not mappings:
        return payload

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
    mappings = _validate_extension(extension) if extension is not None else []

    # Detect mapping conflicts before delegating to the existing base/F8 restore,
    # which preserves the established portable-backup compatibility path.
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

    base_raw = json.dumps(parsed, ensure_ascii=False, allow_nan=False).encode("utf-8")
    result = restore_backup_payload_with_contacts(db, user_id, base_raw, mode)
    if extension is None:
        return result

    existing_count = sum(1 for record in mappings if record["name"] in existing_by_name)
    if mode == "verify_only":
        result["counts"]["import_mappings"] = {
            "created": 0,
            "existing": existing_count,
        }
        return result

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
    db.commit()
    result["counts"]["import_mappings"] = {
        "created": created,
        "existing": existing_count,
    }
    return result
