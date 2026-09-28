#!/usr/bin/env python3
"""C-09 read-only audit for JobGrid private document storage.

Run from the backend directory on the Render service instance:

    python scripts/c09_storage_audit.py

The command never prints document names, user IDs, object keys, endpoints, or file
content. It verifies every ready DocumentVersion against the active storage backend
and emits only aggregate counts, capacity information, and an inventory digest.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database import SessionLocal
from app.models import DocumentVersion
from app.services.document_storage import list_storage_objects, storage_backend_name
from app.services.documents import _resolve_storage_key, _storage_root


CHUNK_BYTES = 64 * 1024
SUPABASE_FREE_STORAGE_BYTES = 1_000_000_000
ZERO_COST_WARNING_BYTES = 900_000_000


def _sha256_file(path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def audit_storage() -> dict[str, object]:
    root = _storage_root(create=False)
    backend = storage_backend_name()
    counters = {
        "ready_records": 0,
        "files_checked": 0,
        "missing": 0,
        "size_mismatch": 0,
        "hash_mismatch": 0,
        "invalid_storage_key": 0,
    }
    inventory_rows: list[str] = []

    db = SessionLocal()
    try:
        documents = (
            db.query(DocumentVersion)
            .filter(DocumentVersion.state == "ready")
            .order_by(DocumentVersion.id.asc())
            .all()
        )
        counters["ready_records"] = len(documents)

        for document in documents:
            try:
                path = _resolve_storage_key(root, document.storage_key)
            except Exception:
                counters["invalid_storage_key"] += 1
                continue

            try:
                if not path.is_file():
                    counters["missing"] += 1
                    continue
                counters["files_checked"] += 1
                actual_size = path.stat().st_size
                if actual_size != int(document.size_bytes):
                    counters["size_mismatch"] += 1
                    continue
                actual_hash = _sha256_file(path)
            except OSError:
                counters["missing"] += 1
                continue

            if actual_hash != document.sha256:
                counters["hash_mismatch"] += 1
                continue

            # Deterministic aggregate evidence without disclosing identifiers.
            inventory_rows.append(
                f"{document.id}:{document.size_bytes}:{document.sha256}"
            )
    finally:
        db.close()

    inventory_digest = hashlib.sha256(
        "\n".join(inventory_rows).encode("utf-8")
    ).hexdigest()
    failed = sum(
        counters[key]
        for key in (
            "missing",
            "size_mismatch",
            "hash_mismatch",
            "invalid_storage_key",
        )
    )

    if backend == "s3":
        objects = list_storage_objects()
        object_bytes = sum(item.size_bytes for item in objects)
        capacity = {
            "backend": "s3",
            "object_count": len(objects),
            "object_bytes": object_bytes,
            "free_tier_quota_bytes": SUPABASE_FREE_STORAGE_BYTES,
            "zero_cost_warning_bytes": ZERO_COST_WARNING_BYTES,
            "within_zero_cost_headroom": object_bytes < ZERO_COST_WARNING_BYTES,
        }
    else:
        usage = shutil.disk_usage(root)
        capacity = {
            "backend": "filesystem",
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
        }

    return {
        "status": "PASS" if failed == 0 else "FAIL",
        "counts": counters,
        "inventory_sha256": inventory_digest,
        "capacity": capacity,
    }


def main() -> int:
    try:
        result = audit_storage()
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "error": type(exc).__name__}, sort_keys=True))
        return 1

    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
