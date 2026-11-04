"""Strict, optional portable visit metadata contract (EXT-22).

This extension is independent from v2 base sections. Existing v2 readers
reject unknown fields rather than silently discard private visit history.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from .backup_schemas import BackupContractError, canonical_json_bytes
from .browser_memory_schemas import parse_browser_memory_payload
from .services.job_identity import JobIdentityError, canonicalize_job_url

VISIT_BACKUP_KEY = "job_visits_v1"
VISIT_SCHEMA_REVISION = 1
MAX_PORTABLE_VISITS = 10_000
_REQUIRED_KEYS = {"schema_revision", "visits", "checksum_sha256"}
_VISIT_FIELDS = {
    "backup_ref", "canonical_url", "canonical_url_hash", "first_visited_at",
}
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$")


def _invalid(message: str, *, status: int = 400) -> BackupContractError:
    return BackupContractError("invalid_job_visits_backup", status, message, section=VISIT_BACKUP_KEY)


def visit_extension_checksum(unsigned: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(unsigned)).hexdigest()


def build_visit_extension(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Sign a validated extension; callers must supply portable records only."""
    result = {"schema_revision": VISIT_SCHEMA_REVISION, "visits": records}
    result["checksum_sha256"] = visit_extension_checksum(result)
    validate_visit_extension(result)
    return result


def validate_visit_extension(value: Any) -> list[dict[str, Any]]:
    """Validate complete extension before any user data is changed."""
    if type(value) is not dict or set(value) != _REQUIRED_KEYS:
        raise _invalid("Visit extension must have exactly the required fields.")
    if type(value["schema_revision"]) is not int or value["schema_revision"] != VISIT_SCHEMA_REVISION:
        raise BackupContractError(
            "unsupported_visit_backup_version", 400,
            "Visit backup schema_revision must be integer 1.",
            section=VISIT_BACKUP_KEY,
        )
    visits = value["visits"]
    if type(visits) is not list:
        raise _invalid("Visit extension records must be a list.")
    if len(visits) > MAX_PORTABLE_VISITS:
        raise BackupContractError(
            "too_many_visits", 413, "Visit backup exceeds the 10,000-record account limit.",
            section=VISIT_BACKUP_KEY,
        )
    checksum = value["checksum_sha256"]
    if type(checksum) is not str or not _SHA_RE.fullmatch(checksum):
        raise _invalid("Visit extension checksum must be a lowercase SHA-256 digest.")
    unsigned = {"schema_revision": value["schema_revision"], "visits": visits}
    if visit_extension_checksum(unsigned) != checksum:
        raise _invalid("Visit extension checksum does not match its records.")

    seen_refs: set[str] = set()
    seen_hashes: dict[str, str] = {}
    for item in visits:
        if type(item) is not dict or set(item) != _VISIT_FIELDS:
            raise _invalid("Visit record has missing or unexpected fields.")
        ref = item["backup_ref"]
        if type(ref) is not str:
            raise _invalid("Visit backup_ref must be a UUID string.")
        try:
            if str(UUID(ref)) != ref:
                raise ValueError("not canonical UUID text")
        except (ValueError, AttributeError) as exc:
            raise _invalid("Visit backup_ref must be a canonical UUID.") from exc
        if ref in seen_refs:
            raise _invalid("Duplicate visit backup_ref.", status=409)
        seen_refs.add(ref)

        raw_url = item["canonical_url"]
        digest = item["canonical_url_hash"]
        if type(raw_url) is not str or type(digest) is not str or not _SHA_RE.fullmatch(digest):
            raise _invalid("Visit canonical URL or hash is invalid.")
        try:
            parse_browser_memory_payload("visit", {"url": raw_url})
            identity = canonicalize_job_url(raw_url)
        except (ValueError, JobIdentityError) as exc:
            raise _invalid("Visit canonical URL must be a safe public job URL.") from exc
        if identity.canonical_url != raw_url or identity.canonical_url_hash != digest:
            raise _invalid("Visit canonical URL/hash mismatch.")
        if digest in seen_hashes:
            raise _invalid("Duplicate visit canonical identity.", status=409)
        seen_hashes[digest] = raw_url

        timestamp = item["first_visited_at"]
        if type(timestamp) is not str or not _UTC_RE.fullmatch(timestamp):
            raise _invalid("Visit first_visited_at must be UTC ISO-8601 with Z.")
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError as exc:
            raise _invalid("Visit first_visited_at is not a real UTC timestamp.") from exc
        if parsed.tzinfo != timezone.utc:
            raise _invalid("Visit timestamp must have UTC timezone.")
    return visits
