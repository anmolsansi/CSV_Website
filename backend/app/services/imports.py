from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
from datetime import datetime, timedelta
from pathlib import PurePath
from typing import Any
from uuid import uuid4

from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from ..import_models import ImportPreview
from ..import_schemas import (
    IMPORT_COMMITTED_RESULT_DAYS,
    IMPORT_PREVIEW_TTL_HOURS,
    MAX_IMPORT_PREVIEW_ROWS,
    MAX_IMPORT_RECORDS,
    MAX_IMPORT_UPLOAD_BYTES,
    ImportCommitRequest,
    ImportContractError,
    canonical_json_bytes,
    header_fingerprint,
    sha256_json,
    validate_mapping,
)
from ..models import CSV_COLUMNS, CsvRow, UrlHistory
from .job_identity import JobIdentityError, canonicalize_job_url, persisted_identity_values
from .validation import ValidationContractError, validate_job_url


logger = logging.getLogger(__name__)
_IMPORT_LOCK_NAMESPACE = 0x4A47000000000000


def _safe_filename(filename: str | None) -> str:
    name = PurePath(filename or "import.csv").name or "import.csv"
    return name[:255]


def _strict_json_loads(value: str) -> Any:
    def reject_constant(token: str):
        raise ValueError(f"Unsupported JSON numeric constant: {token}")

    return json.loads(value, parse_constant=reject_constant)


def _decode_upload(raw: bytes) -> str:
    if len(raw) > MAX_IMPORT_UPLOAD_BYTES:
        raise ImportContractError(
            "import_too_large",
            "Import upload exceeds the 10 MiB limit.",
            status_code=413,
            field="file",
        )
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportContractError(
            "unsupported_encoding",
            "Import files must use UTF-8 or UTF-8 with BOM.",
            status_code=415,
            field="file",
        ) from exc
    if "\x00" in decoded:
        raise ImportContractError(
            "unsupported_encoding",
            "Import files must not contain NUL bytes.",
            status_code=415,
            field="file",
        )
    return decoded


def _scalar_json_value(value: Any, *, row_number: int, column: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    raise ImportContractError(
        "unsupported_json_value",
        "JSON import values must be strings, numbers, booleans, or null.",
        field=f"row[{row_number}].{column}",
    )


def _parse_json_rows(text_value: str) -> tuple[list[str], list[tuple[int, list[str | None]]]]:
    try:
        payload = _strict_json_loads(text_value)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ImportContractError(
            "invalid_json",
            "JSON import must be valid UTF-8 JSON.",
            field="file",
        ) from exc
    if not isinstance(payload, list):
        raise ImportContractError(
            "invalid_json_shape",
            "JSON import must be an array of objects.",
            field="file",
        )
    if len(payload) > MAX_IMPORT_RECORDS:
        raise ImportContractError(
            "too_many_records",
            f"Import contains more than {MAX_IMPORT_RECORDS} records.",
            status_code=413,
            field="file",
        )

    headers: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise ImportContractError(
                "invalid_json_shape",
                "Every JSON import record must be an object.",
                field=f"row[{index}]",
            )
        for key in item:
            if not isinstance(key, str):
                raise ImportContractError(
                    "invalid_json_header",
                    "JSON object keys must be strings.",
                    field=f"row[{index}]",
                )
            if key not in seen:
                seen.add(key)
                headers.append(key)

    if not headers:
        raise ImportContractError(
            "empty_import",
            "Import must contain at least one named column and one record.",
            field="file",
        )

    rows: list[tuple[int, list[str | None]]] = []
    for index, item in enumerate(payload, start=1):
        rows.append(
            (
                index,
                [
                    _scalar_json_value(item.get(header), row_number=index, column=header)
                    for header in headers
                ],
            )
        )
    return headers, rows


def _parse_csv_rows(text_value: str) -> tuple[list[str], list[tuple[int, list[str | None]]]]:
    sample = text_value[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","

    reader = csv.reader(io.StringIO(text_value, newline=""), delimiter=delimiter)
    try:
        headers = next(reader)
    except StopIteration as exc:
        raise ImportContractError(
            "empty_import",
            "CSV import must contain a header row and at least one data row.",
            field="file",
        ) from exc
    if not headers or all(header == "" for header in headers):
        raise ImportContractError(
            "empty_headers",
            "CSV import must contain at least one named column.",
            field="file",
        )

    rows: list[tuple[int, list[str | None]]] = []
    for source_row, values in enumerate(reader, start=2):
        if len(rows) >= MAX_IMPORT_RECORDS:
            raise ImportContractError(
                "too_many_records",
                f"Import contains more than {MAX_IMPORT_RECORDS} records.",
                status_code=413,
                field="file",
            )
        rows.append((source_row, list(values)))
    if not rows:
        raise ImportContractError(
            "empty_import",
            "CSV import must contain at least one data row.",
            field="file",
        )
    return headers, rows


def parse_import_source(
    raw: bytes,
    *,
    filename: str | None,
    content_type: str | None = None,
) -> tuple[list[str], list[tuple[int, list[str | None]]]]:
    text_value = _decode_upload(raw)
    lower_name = (filename or "").lower()
    is_json = lower_name.endswith(".json") or content_type == "application/json"
    if is_json:
        return _parse_json_rows(text_value)
    return _parse_csv_rows(text_value)


def _normalize_match_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.strip().casefold().split())
    return normalized or None


def destination_fingerprint(db: Session, *, user_id: int) -> str:
    """Hash the owner's current import destination state conservatively.

    F9 prefers a false-positive re-preview over silently applying a stale plan.
    Including every owner row also protects update-selected fields that are not
    part of duplicate identity.
    """
    digest = hashlib.sha256()
    query = (
        db.query(CsvRow)
        .filter(CsvRow.user_id == user_id)
        .order_by(CsvRow.id.asc())
        .yield_per(500)
    )
    for row in query:
        snapshot = [row.id, row.canonical_url, row.canonical_url_hash]
        snapshot.extend(getattr(row, field) for field in CSV_COLUMNS)
        digest.update(canonical_json_bytes(snapshot))
        digest.update(b"\n")
    return digest.hexdigest()


def _existing_identity_indexes(db: Session, *, user_id: int):
    rows = db.query(CsvRow).filter(CsvRow.user_id == user_id).order_by(CsvRow.id.asc()).all()
    exact: dict[str, CsvRow] = {}
    canonical: dict[str, CsvRow] = {}
    company_title: dict[tuple[str, str], CsvRow] = {}
    for row in rows:
        exact.setdefault(row.url, row)
        if row.canonical_url_hash:
            canonical.setdefault(row.canonical_url_hash, row)
        company = _normalize_match_text(row.company_guess)
        title = _normalize_match_text(row.title)
        if company and title:
            company_title.setdefault((company, title), row)
    return exact, canonical, company_title


def _mapped_values(
    values: list[str | None],
    mapping: dict[str, str],
) -> dict[str, str | None]:
    return {target: values[int(source_index)] for source_index, target in mapping.items()}


def _error_entry(source_row: int, column: str, code: str) -> dict[str, Any]:
    return {"row": source_row, "column": column, "code": code}


def build_import_plan(
    db: Session,
    *,
    user_id: int,
    headers: list[str],
    rows: list[tuple[int, list[str | None]]],
    mapping: dict[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int], list[dict[str, Any]]]:
    exact_index, canonical_index, company_title_index = _existing_identity_indexes(db, user_id=user_id)
    url_source_index = next(int(index) for index, target in mapping.items() if target == "url")
    url_column = headers[url_source_index]

    plan: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    counts = {"create": 0, "exact_duplicate": 0, "possible_duplicate": 0, "invalid": 0}

    seen_urls: dict[str, int] = {}
    seen_canonical: dict[str, int] = {}
    seen_company_title: dict[tuple[str, str], int] = {}

    for source_row, original_values in rows:
        if len(original_values) != len(headers):
            code = "column_count_mismatch"
            counts["invalid"] += 1
            error = _error_entry(source_row, "__row__", code)
            errors.append(error)
            rejected.append({"source_row": source_row, "error_code": code, "values": original_values})
            plan.append({
                "source_row": source_row,
                "values": {},
                "classification": "invalid",
                "reason": code,
                "existing_row_id": None,
                "errors": [error],
            })
            continue

        mapped = _mapped_values(original_values, mapping)
        raw_url = mapped.get("url")
        try:
            url = validate_job_url(raw_url, field=url_column)
            identity = canonicalize_job_url(url)
        except (ValidationContractError, JobIdentityError) as exc:
            code = getattr(exc, "code", "invalid_url")
            counts["invalid"] += 1
            error = _error_entry(source_row, url_column, code)
            errors.append(error)
            rejected.append({"source_row": source_row, "error_code": code, "values": original_values})
            plan.append({
                "source_row": source_row,
                "values": mapped,
                "classification": "invalid",
                "reason": code,
                "existing_row_id": None,
                "errors": [error],
            })
            continue

        mapped["url"] = url
        existing = exact_index.get(url)
        classification = "create"
        reason = "new_url"
        existing_row_id: int | None = None

        if existing is not None:
            classification = "exact_duplicate"
            reason = "same_original_url"
            existing_row_id = existing.id
        elif url in seen_urls:
            classification = "exact_duplicate"
            reason = "duplicate_in_upload"
        else:
            canonical_existing = canonical_index.get(identity.canonical_url_hash)
            if canonical_existing is not None:
                classification = "possible_duplicate"
                reason = "same_canonical_url"
                existing_row_id = canonical_existing.id
            elif identity.canonical_url_hash in seen_canonical:
                classification = "possible_duplicate"
                reason = "canonical_duplicate_in_upload"
            else:
                company = _normalize_match_text(mapped.get("company_guess"))
                title = _normalize_match_text(mapped.get("title"))
                company_key = (company, title) if company and title else None
                possible = company_title_index.get(company_key) if company_key else None
                if possible is not None:
                    classification = "possible_duplicate"
                    reason = "company_title_only"
                    existing_row_id = possible.id
                elif company_key and company_key in seen_company_title:
                    classification = "possible_duplicate"
                    reason = "company_title_duplicate_in_upload"

        counts[classification] += 1
        plan.append({
            "source_row": source_row,
            "values": mapped,
            "classification": classification,
            "reason": reason,
            "existing_row_id": existing_row_id,
            "errors": [],
        })

        seen_urls.setdefault(url, source_row)
        seen_canonical.setdefault(identity.canonical_url_hash, source_row)
        company = _normalize_match_text(mapped.get("company_guess"))
        title = _normalize_match_text(mapped.get("title"))
        if company and title:
            seen_company_title.setdefault((company, title), source_row)

    return plan, rejected, counts, errors


def create_import_preview(
    db: Session,
    *,
    user_id: int,
    raw: bytes,
    filename: str | None,
    content_type: str | None,
    mapping_value: Any,
    options: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> ImportPreview:
    now = now or datetime.utcnow()
    if len(raw) > MAX_IMPORT_UPLOAD_BYTES:
        raise ImportContractError(
            "import_too_large",
            "Import upload exceeds the 10 MiB limit.",
            status_code=413,
            field="file",
        )
    headers, source_rows = parse_import_source(raw, filename=filename, content_type=content_type)
    mapping = validate_mapping(mapping_value, column_count=len(headers))
    plan, rejected, counts, errors = build_import_plan(
        db,
        user_id=user_id,
        headers=headers,
        rows=source_rows,
        mapping=mapping,
    )
    source_hash = hashlib.sha256(raw).hexdigest()
    destination_hash = destination_fingerprint(db, user_id=user_id)
    plan_checksum = sha256_json(
        {
            "source_sha256": source_hash,
            "headers": headers,
            "mapping": mapping,
            "rows": plan,
        }
    )
    sample = [
        {
            "row": item["source_row"],
            "classification": item["classification"],
            "reason": item["reason"],
            "values": item["values"],
        }
        for item in plan[:MAX_IMPORT_PREVIEW_ROWS]
    ]
    summary = {
        "record_count": len(source_rows),
        "counts": counts,
        "errors": errors[:MAX_IMPORT_PREVIEW_ROWS],
        "sample_rows": sample,
        "plan_checksum": plan_checksum,
        "options": options or {},
    }
    preview = ImportPreview(
        user_id=user_id,
        source_filename=_safe_filename(filename),
        source_sha256=source_hash,
        headers_json=headers,
        header_fingerprint=header_fingerprint(headers),
        mapping_json=mapping,
        normalized_rows_json=plan,
        rejected_rows_json=rejected or None,
        summary_json=summary,
        destination_fingerprint=destination_hash,
        created_at=now,
        expires_at=now + timedelta(hours=IMPORT_PREVIEW_TTL_HOURS),
        status="ready",
        version=1,
    )
    db.add(preview)
    db.flush()
    return preview


def serialize_import_preview(preview: ImportPreview) -> dict[str, Any]:
    summary = preview.summary_json or {}
    headers = list(preview.headers_json or [])
    mapping = preview.mapping_json or {}
    return {
        "preview_id": preview.id,
        "expires_at": preview.expires_at.isoformat() + "Z",
        "version": preview.version,
        "header_fingerprint": preview.header_fingerprint,
        "columns": [
            {
                "index": index,
                "label": label,
                "mapped_to": mapping.get(str(index)),
            }
            for index, label in enumerate(headers)
        ],
        "rows": summary.get("sample_rows", []),
        "counts": summary.get(
            "counts",
            {"create": 0, "exact_duplicate": 0, "possible_duplicate": 0, "invalid": 0},
        ),
        "errors": summary.get("errors", []),
    }


def _owned_preview_for_update(db: Session, *, user_id: int, preview_id: str) -> ImportPreview:
    query = db.query(ImportPreview).filter(
        ImportPreview.id == preview_id,
        ImportPreview.user_id == user_id,
    )
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        query = query.with_for_update()
    preview = query.first()
    if preview is None:
        raise ImportContractError(
            "import_preview_not_found",
            "Import preview was not found.",
            status_code=404,
        )
    return preview


def get_owned_import_preview(db: Session, *, user_id: int, preview_id: str) -> ImportPreview:
    preview = db.query(ImportPreview).filter(
        ImportPreview.id == preview_id,
        ImportPreview.user_id == user_id,
    ).first()
    if preview is None:
        raise ImportContractError(
            "import_preview_not_found",
            "Import preview was not found.",
            status_code=404,
        )
    return preview


def _acquire_account_import_lock(db: Session, *, user_id: int) -> None:
    if db.bind is None:
        return
    dialect_name = db.bind.dialect.name
    if dialect_name == "postgresql":
        lock_key = _IMPORT_LOCK_NAMESPACE + int(user_id)
        db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})
        return
    if dialect_name == "sqlite":
        # SQLite has no row-level FOR UPDATE/advisory lock. A no-op write against
        # the authenticated owner row acquires the database write lock inside
        # the current transaction before preview state is read or reconciled.
        db.execute(
            text("UPDATE users SET id = id WHERE id = :user_id"),
            {"user_id": int(user_id)},
        )


def _commit_payload_hash(payload: ImportCommitRequest) -> str:
    return sha256_json(payload.model_dump(mode="json"))


def _verify_plan_checksum(preview: ImportPreview) -> None:
    expected = (preview.summary_json or {}).get("plan_checksum")
    current = sha256_json(
        {
            "source_sha256": preview.source_sha256,
            "headers": preview.headers_json,
            "mapping": preview.mapping_json,
            "rows": preview.normalized_rows_json,
        }
    )
    if not expected or expected != current:
        raise ImportContractError(
            "preview_changed",
            "Stored import preview no longer matches its validated checksum. Create a new preview.",
            status_code=409,
        )


def _history_exists(db: Session, *, user_id: int, url: str) -> bool:
    return db.query(UrlHistory.id).filter(
        UrlHistory.user_id == user_id,
        UrlHistory.url == url,
    ).first() is not None


def _create_csv_row(
    db: Session,
    *,
    user_id: int,
    batch_id: str,
    values: dict[str, Any],
) -> CsvRow:
    url = values["url"]
    row_values = {field: values.get(field) for field in CSV_COLUMNS if field in values}
    row = CsvRow(
        user_id=user_id,
        upload_batch_id=batch_id,
        **row_values,
    )
    identity = persisted_identity_values(url)
    if identity:
        row.canonical_url = identity["canonical_url"]
        row.canonical_url_hash = identity["canonical_url_hash"]
    db.add(row)
    if not _history_exists(db, user_id=user_id, url=url):
        db.add(UrlHistory(user_id=user_id, url=url))
    return row


def _apply_selected_update(
    row: CsvRow,
    *,
    values: dict[str, Any],
    update_fields: list[str],
    replace_empty: bool,
) -> bool:
    changed = False
    for field in update_fields:
        if field not in values:
            continue
        incoming = values[field]
        if incoming in (None, "") and not replace_empty:
            continue
        if getattr(row, field) != incoming:
            setattr(row, field, incoming)
            changed = True
    return changed


def commit_import_preview(
    db: Session,
    *,
    user_id: int,
    preview_id: str,
    payload: ImportCommitRequest,
    now: datetime | None = None,
) -> tuple[dict[str, Any], bool]:
    now = now or datetime.utcnow()
    _acquire_account_import_lock(db, user_id=user_id)
    preview = _owned_preview_for_update(db, user_id=user_id, preview_id=preview_id)
    payload_hash = _commit_payload_hash(payload)

    if preview.status == "committed":
        if preview.committed_at and preview.committed_at < now - timedelta(days=IMPORT_COMMITTED_RESULT_DAYS):
            raise ImportContractError(
                "commit_result_expired",
                "Committed import replay result has expired.",
                status_code=410,
            )
        if preview.commit_key != payload.idempotency_key or preview.commit_payload_hash != payload_hash:
            raise ImportContractError(
                "idempotency_conflict",
                "This preview was already committed with different commit input.",
                status_code=409,
            )
        return dict(preview.result_json or {}), True

    if preview.expires_at <= now:
        raise ImportContractError(
            "import_preview_expired",
            "Import preview has expired. Create a new preview.",
            status_code=410,
        )
    if preview.status != "ready":
        raise ImportContractError(
            "import_preview_unavailable",
            "Import preview is not available for commit.",
            status_code=409,
        )
    if preview.version != payload.version:
        raise ImportContractError(
            "version_conflict",
            "Import preview changed. Reload or create a new preview.",
            status_code=409,
        )

    _verify_plan_checksum(preview)
    current_destination = destination_fingerprint(db, user_id=user_id)
    if current_destination != preview.destination_fingerprint:
        raise ImportContractError(
            "destination_changed",
            "Import destination changed after preview. Create a new preview.",
            status_code=409,
        )

    summary = preview.summary_json or {}
    invalid_count = int((summary.get("counts") or {}).get("invalid", 0))
    if invalid_count and payload.invalid_policy == "reject":
        raise ImportContractError(
            "invalid_rows_present",
            "Preview contains invalid rows. Use skip only after reviewing the rejected-row report.",
            status_code=422,
        )

    rows = list(preview.normalized_rows_json or [])
    if len(rows) > MAX_IMPORT_RECORDS:
        raise ImportContractError(
            "preview_record_limit_exceeded",
            "Stored preview exceeds the import record limit.",
            status_code=409,
        )

    preview.status = "committing"
    preview.commit_key = payload.idempotency_key
    preview.commit_payload_hash = payload_hash
    db.flush()

    counts = {"created": 0, "updated": 0, "skipped": 0, "invalid": 0}
    row_results: list[dict[str, Any]] = []
    batch_id = str(uuid4())

    for item in rows:
        source_row = int(item["source_row"])
        classification = item["classification"]
        reason = item["reason"]
        values = dict(item.get("values") or {})
        existing_row_id = item.get("existing_row_id")

        if classification == "invalid":
            counts["invalid"] += 1
            row_results.append({"row": source_row, "action": "invalid", "reason": reason})
            continue

        if classification == "create" or (
            classification == "possible_duplicate" and payload.possible_duplicate_policy == "create"
        ):
            _create_csv_row(
                db,
                user_id=user_id,
                batch_id=batch_id,
                values=values,
            )
            counts["created"] += 1
            row_results.append({"row": source_row, "action": "created", "reason": reason})
            continue

        if classification == "exact_duplicate" and payload.mode == "update_selected" and existing_row_id:
            existing = db.query(CsvRow).filter(
                CsvRow.id == int(existing_row_id),
                CsvRow.user_id == user_id,
                CsvRow.url == values.get("url"),
            ).first()
            if existing is None:
                raise ImportContractError(
                    "destination_changed",
                    "Exact duplicate target changed after preview. Create a new preview.",
                    status_code=409,
                )
            if _apply_selected_update(
                existing,
                values=values,
                update_fields=payload.update_fields,
                replace_empty=payload.replace_empty,
            ):
                counts["updated"] += 1
                row_results.append({"row": source_row, "action": "updated", "reason": reason})
            else:
                counts["skipped"] += 1
                row_results.append({"row": source_row, "action": "skipped", "reason": "no_selected_change"})
            continue

        counts["skipped"] += 1
        row_results.append({"row": source_row, "action": "skipped", "reason": reason})

    db.flush()
    result = {
        "preview_id": preview.id,
        "counts": counts,
        "rows": row_results,
        "replayed": False,
    }
    preview.status = "committed"
    preview.result_json = result
    preview.committed_at = now
    preview.normalized_rows_json = None
    preview.version += 1
    db.flush()
    return result, False


def cleanup_import_previews(
    db: Session,
    *,
    now: datetime | None = None,
    limit: int = 200,
) -> dict[str, int]:
    """Bounded F9 cleanup: expire raw previews, rejected rows, and old results."""
    now = now or datetime.utcnow()
    if limit < 1 or limit > 500:
        raise ValueError("limit must be between 1 and 500")
    result_cutoff = now - timedelta(days=IMPORT_COMMITTED_RESULT_DAYS)
    candidates = (
        db.query(ImportPreview)
        .filter(
            or_(
                ImportPreview.expires_at <= now,
                ImportPreview.committed_at <= result_cutoff,
            )
        )
        .order_by(ImportPreview.created_at.asc())
        .limit(limit)
        .all()
    )
    deleted = 0
    scrubbed = 0
    for preview in candidates:
        if preview.status == "committed":
            if preview.committed_at is not None and preview.committed_at <= result_cutoff:
                db.delete(preview)
                deleted += 1
            elif preview.expires_at <= now and preview.rejected_rows_json is not None:
                preview.rejected_rows_json = None
                scrubbed += 1
        elif preview.expires_at <= now:
            db.delete(preview)
            deleted += 1
    db.flush()
    return {"deleted": deleted, "scrubbed": scrubbed}
