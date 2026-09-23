from __future__ import annotations

import csv
import io
import json
import logging
from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..import_schemas import MAX_IMPORT_UPLOAD_BYTES, ImportCommitRequest, ImportContractError
from ..models import User
from ..services.imports import (
    commit_import_preview,
    create_import_preview,
    get_owned_import_preview,
    serialize_import_preview,
)


router = APIRouter(prefix="/crm/imports", tags=["imports"])
logger = logging.getLogger(__name__)


def _parse_json_form(raw: str, *, field: str, default):
    if raw == "" and default is not None:
        return default
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ImportContractError(
            f"invalid_{field}",
            f"{field} must be valid JSON.",
            field=field,
        ) from exc
    return value


def _raise_import_error(exc: Exception, db: Session, *, action: str, operation_id: str, started: float):
    db.rollback()
    elapsed_ms = int((perf_counter() - started) * 1000)
    if isinstance(exc, ImportContractError):
        logger.info(
            "import_operation operation_id=%s action=%s outcome=%s elapsed_ms=%s",
            operation_id,
            action,
            exc.code,
            elapsed_ms,
        )
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc
    if isinstance(exc, IntegrityError):
        logger.info(
            "import_operation operation_id=%s action=%s outcome=destination_conflict elapsed_ms=%s",
            operation_id,
            action,
            elapsed_ms,
        )
        raise HTTPException(
            status_code=409,
            detail={
                "code": "destination_changed",
                "fields": [{"field": "__root__", "message": "Import destination changed. Create a new preview."}],
            },
        ) from exc
    logger.exception(
        "import_operation operation_id=%s action=%s outcome=internal_error elapsed_ms=%s",
        operation_id,
        action,
        elapsed_ms,
    )
    raise HTTPException(
        status_code=500,
        detail={
            "code": "internal_error",
            "fields": [{"field": "__root__", "message": "Import operation could not be completed."}],
        },
    ) from exc


def _spreadsheet_safe_csv_value(value):
    if not isinstance(value, str) or not value:
        return value
    stripped_control = value.lstrip("\t\r\n\v\f")
    if value[0] in "=+-@" or (
        stripped_control != value
        and stripped_control
        and stripped_control[0] in "=+-@"
    ):
        return "'" + value
    return value


@router.post("/preview", status_code=201)
async def post_import_preview(
    file: UploadFile = File(...),
    mapping: str = Form(...),
    options: str = Form("{}"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    operation_id = str(uuid4())
    started = perf_counter()
    try:
        raw = await file.read(MAX_IMPORT_UPLOAD_BYTES + 1)
        if len(raw) > MAX_IMPORT_UPLOAD_BYTES:
            raise ImportContractError(
                "import_too_large",
                "Import upload exceeds the 10 MiB limit.",
                status_code=413,
                field="file",
            )
        mapping_value = _parse_json_form(mapping, field="mapping", default=None)
        options_value = _parse_json_form(options, field="options", default={})
        if not isinstance(options_value, dict):
            raise ImportContractError(
                "invalid_options",
                "options must be a JSON object.",
                field="options",
            )
        preview = create_import_preview(
            db,
            user_id=user.id,
            raw=raw,
            filename=file.filename,
            content_type=file.content_type,
            mapping_value=mapping_value,
            options=options_value,
        )
        result = serialize_import_preview(preview)
        db.commit()
        logger.info(
            "import_operation operation_id=%s action=preview outcome=success records=%s invalid=%s elapsed_ms=%s",
            operation_id,
            result["counts"].get("create", 0)
            + result["counts"].get("exact_duplicate", 0)
            + result["counts"].get("possible_duplicate", 0)
            + result["counts"].get("invalid", 0),
            result["counts"].get("invalid", 0),
            int((perf_counter() - started) * 1000),
        )
        return result
    except Exception as exc:
        _raise_import_error(exc, db, action="preview", operation_id=operation_id, started=started)
    finally:
        await file.close()


@router.get("/{preview_id}")
def get_import_preview(
    preview_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        preview = get_owned_import_preview(db, user_id=user.id, preview_id=preview_id)
        if preview.status != "committed" and preview.expires_at.isoformat() <= __import__("datetime").datetime.utcnow().isoformat():
            raise ImportContractError(
                "import_preview_expired",
                "Import preview has expired. Create a new preview.",
                status_code=410,
            )
        return serialize_import_preview(preview)
    except ImportContractError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.post("/{preview_id}/commit")
def post_import_commit(
    preview_id: str,
    payload: ImportCommitRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    operation_id = str(uuid4())
    started = perf_counter()
    try:
        result, replayed = commit_import_preview(
            db,
            user_id=user.id,
            preview_id=preview_id,
            payload=payload,
        )
        db.commit()
        logger.info(
            "import_operation operation_id=%s action=commit outcome=%s created=%s updated=%s skipped=%s invalid=%s elapsed_ms=%s",
            operation_id,
            "replayed" if replayed else "success",
            result.get("counts", {}).get("created", 0),
            result.get("counts", {}).get("updated", 0),
            result.get("counts", {}).get("skipped", 0),
            result.get("counts", {}).get("invalid", 0),
            int((perf_counter() - started) * 1000),
        )
        return result
    except Exception as exc:
        _raise_import_error(exc, db, action="commit", operation_id=operation_id, started=started)


@router.get("/{preview_id}/rejected.csv")
def download_rejected_rows(
    preview_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from datetime import datetime

    try:
        preview = get_owned_import_preview(db, user_id=user.id, preview_id=preview_id)
        if preview.expires_at <= datetime.utcnow():
            raise ImportContractError(
                "rejected_rows_expired",
                "Rejected-row download has expired.",
                status_code=410,
            )
    except ImportContractError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc

    headers = list(preview.headers_json or [])
    rejected = list(preview.rejected_rows_json or [])
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(["_source_row", "_error_code", *headers])
    for item in rejected:
        original_values = [
            _spreadsheet_safe_csv_value(value)
            for value in list(item.get("values") or [])
        ]
        writer.writerow([
            item.get("source_row"),
            item.get("error_code"),
            *original_values,
        ])
    content = output.getvalue().encode("utf-8-sig")
    safe_stem = preview.source_filename.rsplit(".", 1)[0] or "import"
    return StreamingResponse(
        io.BytesIO(content),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_stem}_rejected.csv"',
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
        },
    )
