#!/usr/bin/env python3
"""C-09 read-only audit for JobGrid private document storage.

Run from the backend directory on the Render service instance:

    python scripts/c09_storage_audit.py

The command never prints document names, user IDs, storage paths, or file content.
It verifies every ready DocumentVersion against the configured private filesystem
and emits only aggregate counts, capacity, and an inventory digest suitable for
restart/redeploy/recovery evidence.
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

from app.config import validate_document_storage_path, settings
from app.database import SessionLocal
from app.models import DocumentVersion


CHUNK_BYTES = 64 * 1024


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_storage_key(root: Path, storage_key: str) -> Path:
    candidate = (root / storage_key).resolve(strict=False)
    if root != candidate and root not in candidate.parents:
        raise ValueError("invalid storage key")
    return candidate


def audit_storage() -> dict[str, object]:
    root = validate_document_storage_path(
        settings.DOCUMENT_STORAGE_DIR,
        environment=settings.ENVIRONMENT,
    )
    if not root.is_dir():
        raise RuntimeError("document storage root is unavailable")

    usage = shutil.disk_usage(root)
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
            except ValueError:
                counters["invalid_storage_key"] += 1
                continue

            if not path.is_file():
                counters["missing"] += 1
                continue

            counters["files_checked"] += 1
            actual_size = path.stat().st_size
            if actual_size != int(document.size_bytes):
                counters["size_mismatch"] += 1
                continue

            actual_hash = _sha256_file(path)
            if actual_hash != document.sha256:
                counters["hash_mismatch"] += 1
                continue

            # The digest is deterministic but does not expose any individual
            # document identifier or storage key in command output.
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

    return {
        "status": "PASS" if failed == 0 else "FAIL",
        "counts": counters,
        "inventory_sha256": inventory_digest,
        "disk": {
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
        },
    }


def main() -> int:
    try:
        result = audit_storage()
    except Exception as exc:
        # Keep operator output useful without printing paths, DSNs, or document data.
        print(json.dumps({"status": "FAIL", "error": type(exc).__name__}, sort_keys=True))
        return 1

    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
