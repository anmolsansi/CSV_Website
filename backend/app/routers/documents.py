from __future__ import annotations

import logging
from time import perf_counter
from typing import Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Response,
    UploadFile,
)
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..document_schemas import DocumentLinkIn, DocumentUploadMetadata
from ..models import User
from ..services.documents import (
    DocumentServiceError,
    create_document,
    delete_document,
    detach_document,
    download_target,
    link_document,
    list_document_applications,
    list_documents,
    list_track_documents,
    serialize_document,
    stage_upload,
)


router = APIRouter(prefix="/crm", tags=["documents"])
logger = logging.getLogger(__name__)


def _log(
    *,
    action: str,
    request_id: str,
    outcome: str,
    affected: int,
    started: float,
    warning: bool = False,
) -> None:
    emit = logger.warning if warning else logger.info
    emit(
        "document_api action=%s request_id=%s outcome=%s affected=%s elapsed_ms=%s",
        action,
        request_id,
        outcome,
        affected,
        int((perf_counter() - started) * 1000),
    )


def _detail(exc: DocumentServiceError, request_id: str) -> dict[str, Any]:
    detail: dict[str, Any] = {
        "code": exc.code,
        "fields": [{"field": exc.field, "message": exc.message}],
        "request_id": request_id,
    }
    detail.update(exc.context)
    return detail


def _raise_service_error(
    db: Session,
    exc: DocumentServiceError,
    *,
    action: str,
    request_id: str,
    started: float,
) -> None:
    if exc.code == "document_publish_failed":
        # Preserve explicit failed state when DB metadata exists but filesystem
        # publication failed. Other errors are rolled back completely.
        db.commit()
    else:
        db.rollback()
    _log(
        action=action,
        request_id=request_id,
        outcome=exc.code,
        affected=0,
        started=started,
        warning=True,
    )
    raise HTTPException(
        status_code=exc.status_code,
        detail=_detail(exc, request_id),
    ) from exc


def _request_id(value: str | None = None) -> str:
    try:
        return str(UUID(str(value))) if value else str(UUID(int=0))
    except (TypeError, ValueError, AttributeError):
        return "invalid"


@router.post("/documents")
def upload_document(
    kind: str = Form(...),
    label: str = Form(...),
    document_family_id: str | None = Form(default=None),
    file: UploadFile = File(...),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    started = perf_counter()
    request_id = _request_id(idempotency_key)
    if request_id == "invalid":
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_idempotency_key",
                "fields": [{
                    "field": "Idempotency-Key",
                    "message": "Idempotency-Key must be a valid UUID.",
                }],
            },
        )

    try:
        metadata = DocumentUploadMetadata(
            kind=kind,
            label=label,
            document_family_id=document_family_id or None,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_document_metadata",
                "fields": [
                    {
                        "field": ".".join(str(part) for part in error["loc"]),
                        "message": error["msg"],
                    }
                    for error in exc.errors()
                ],
            },
        ) from exc

    try:
        staged = stage_upload(
            file.file,
            original_filename=file.filename,
            claimed_media_type=file.content_type,
        )
        result = create_document(
            db,
            user_id=user.id,
            metadata=metadata,
            staged=staged,
            request_key=idempotency_key,
        )
        db.commit()
        db.refresh(result.document)
        status = 200 if result.replayed else 201
        _log(
            action="upload",
            request_id=request_id,
            outcome="replay" if result.replayed else "created",
            affected=0 if result.replayed else 1,
            started=started,
        )
        return JSONResponse(
            status_code=status,
            content=serialize_document(result.document),
        )
    except DocumentServiceError as exc:
        _raise_service_error(
            db,
            exc,
            action="upload",
            request_id=request_id,
            started=started,
        )
    except IntegrityError as exc:
        db.rollback()
        _log(
            action="upload",
            request_id=request_id,
            outcome="conflict",
            affected=0,
            started=started,
            warning=True,
        )
        raise HTTPException(
            status_code=409,
            detail={
                "code": "document_write_conflict",
                "fields": [{
                    "field": "__root__",
                    "message": "Document state changed concurrently. Retry with the same Idempotency-Key.",
                }],
                "request_id": request_id,
            },
        ) from exc
    finally:
        file.file.close()


@router.get("/documents")
def get_documents(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return list_documents(db, user_id=user.id)


@router.get("/documents/{document_id}/download")
def download_document(
    document_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    started = perf_counter()
    request_id = str(UUID(int=0))
    try:
        document, path = download_target(
            db, user_id=user.id, document_id=str(document_id)
        )
        _log(
            action="download",
            request_id=request_id,
            outcome="success",
            affected=1,
            started=started,
        )
        return FileResponse(
            path,
            media_type=document.media_type,
            filename=document.original_filename,
            headers={
                "Cache-Control": "private, no-store",
                "Pragma": "no-cache",
                "X-Content-Type-Options": "nosniff",
            },
        )
    except DocumentServiceError as exc:
        _raise_service_error(
            db,
            exc,
            action="download",
            request_id=request_id,
            started=started,
        )


@router.get("/documents/{document_id}/applications")
def document_applications(
    document_id: UUID,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return list_document_applications(
            db,
            user_id=user.id,
            document_id=str(document_id),
            page=page,
            limit=limit,
        )
    except DocumentServiceError as exc:
        _raise_service_error(
            db,
            exc,
            action="applications",
            request_id=str(UUID(int=0)),
            started=perf_counter(),
        )


@router.delete("/documents/{document_id}", status_code=204)
def remove_document(
    document_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    started = perf_counter()
    request_id = str(UUID(int=0))
    try:
        delete_document(db, user_id=user.id, document_id=str(document_id))
        db.commit()
        _log(
            action="delete",
            request_id=request_id,
            outcome="deleted",
            affected=1,
            started=started,
        )
        return Response(status_code=204)
    except DocumentServiceError as exc:
        _raise_service_error(
            db,
            exc,
            action="delete",
            request_id=request_id,
            started=started,
        )


@router.get("/tracks/{track_id}/documents")
def track_documents(
    track_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return {"items": list_track_documents(db, user_id=user.id, track_id=track_id)}
    except DocumentServiceError as exc:
        _raise_service_error(
            db,
            exc,
            action="track_list",
            request_id=str(UUID(int=0)),
            started=perf_counter(),
        )


@router.post("/tracks/{track_id}/documents")
def attach_document(
    track_id: int,
    payload: DocumentLinkIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    started = perf_counter()
    request_id = str(UUID(int=0))
    try:
        link = link_document(
            db,
            user_id=user.id,
            track_id=track_id,
            payload=payload,
        )
        db.commit()
        db.refresh(link)
        _log(
            action="attach",
            request_id=request_id,
            outcome="success",
            affected=1,
            started=started,
        )
        items = list_track_documents(db, user_id=user.id, track_id=track_id)
        return next(item for item in items if item["id"] == link.id)
    except DocumentServiceError as exc:
        _raise_service_error(
            db,
            exc,
            action="attach",
            request_id=request_id,
            started=started,
        )
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "document_link_conflict",
                "fields": [{
                    "field": "__root__",
                    "message": "Document attachment changed concurrently. Reload and retry.",
                }],
            },
        ) from exc


@router.delete("/tracks/{track_id}/documents/{document_id}", status_code=204)
def detach_application_document(
    track_id: int,
    document_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    started = perf_counter()
    request_id = str(UUID(int=0))
    try:
        changed = detach_document(
            db,
            user_id=user.id,
            track_id=track_id,
            document_id=str(document_id),
        )
        db.commit()
        _log(
            action="detach",
            request_id=request_id,
            outcome="detached" if changed else "already_detached",
            affected=1 if changed else 0,
            started=started,
        )
        return Response(status_code=204)
    except DocumentServiceError as exc:
        _raise_service_error(
            db,
            exc,
            action="detach",
            request_id=request_id,
            started=started,
        )
