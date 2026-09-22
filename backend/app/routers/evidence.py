from __future__ import annotations

import logging
from datetime import datetime
from time import perf_counter
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..evidence_schemas import EvidenceCreateData
from ..models import User
from ..services.evidence import (
    DEFAULT_TIMELINE_LIMIT,
    MAX_TIMELINE_LIMIT,
    EvidenceServiceError,
    correct_applied_date,
    correct_latest_status,
    create_evidence,
    delete_evidence,
    edit_evidence,
    get_timeline,
    serialize_evidence,
)
from ..services.lifecycle import LifecycleEventError, coerce_operation_id


router = APIRouter(prefix="/crm/tracks", tags=["evidence"])
logger = logging.getLogger(__name__)


class EvidenceEditIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    version: int = Field(ge=1)
    body: str | None = Field(default=None, max_length=20_000)
    occurred_at: datetime | None = None

    @model_validator(mode="after")
    def require_change(self):
        supplied = self.model_fields_set
        if not ({"body", "occurred_at"} & supplied):
            raise ValueError("At least one evidence field must be edited.")
        if "body" in supplied and self.body is None:
            raise ValueError("Evidence body cannot be null.")
        return self


class AppliedDateCorrectionIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    applied_at: datetime
    reason: str = Field(min_length=1, max_length=500)


class StatusCorrectionIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    expected_event_id: int = Field(gt=0)
    restore_status: str
    reason: str = Field(min_length=1, max_length=500)


def _operation_id(value: str | None) -> UUID:
    try:
        return coerce_operation_id(value)
    except LifecycleEventError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": exc.code,
                "fields": [{"field": "X-Operation-ID", "message": exc.message}],
            },
        ) from exc


def _log_outcome(
    *,
    action: str,
    request_id: UUID | str,
    outcome: str,
    affected: int,
    started: float,
    warning: bool = False,
) -> None:
    log = logger.warning if warning else logger.info
    log(
        "evidence_api action=%s request_id=%s outcome=%s affected=%s elapsed_ms=%s",
        action,
        request_id,
        outcome,
        affected,
        int((perf_counter() - started) * 1000),
    )


def _raise_service_error(
    db: Session,
    exc: EvidenceServiceError,
    *,
    action: str,
    request_id: UUID | str,
    started: float,
) -> None:
    db.rollback()
    _log_outcome(
        action=action,
        request_id=request_id,
        outcome=exc.code,
        affected=0,
        started=started,
        warning=True,
    )
    raise HTTPException(
        status_code=exc.status_code,
        detail={
            "code": exc.code,
            "fields": [{"field": "__root__", "message": exc.message}],
            "request_id": str(request_id),
        },
    ) from exc


def _raise_lifecycle_error(
    db: Session,
    exc: LifecycleEventError,
    *,
    action: str,
    request_id: UUID | str,
    started: float,
) -> None:
    db.rollback()
    if exc.code == "event_key_conflict":
        status_code = 409
    elif exc.code in {
        "inaccessible_csv_row",
        "inaccessible_job_track",
        "inaccessible_evidence",
    }:
        status_code = 404
    else:
        status_code = 422
    _log_outcome(
        action=action,
        request_id=request_id,
        outcome=exc.code,
        affected=0,
        started=started,
        warning=True,
    )
    raise HTTPException(
        status_code=status_code,
        detail={
            "code": exc.code,
            "fields": [{"field": "__root__", "message": exc.message}],
            "request_id": str(request_id),
        },
    ) from exc


def _raise_integrity_error(
    db: Session,
    *,
    action: str,
    request_id: UUID | str,
    started: float,
) -> None:
    db.rollback()
    _log_outcome(
        action=action,
        request_id=request_id,
        outcome="conflict",
        affected=0,
        started=started,
        warning=True,
    )
    raise HTTPException(
        status_code=409,
        detail={
            "code": "conflict",
            "fields": [
                {
                    "field": "__root__",
                    "message": "The evidence changed concurrently. Reload and retry.",
                }
            ],
            "request_id": str(request_id),
        },
    )


def _track_response(track) -> dict[str, Any]:
    return {
        "track_id": track.id,
        "status": track.status,
        "applied_at": (
            track.applied_at.isoformat() + "Z"
            if track.applied_at is not None
            else None
        ),
    }


@router.get("/{track_id}/timeline")
def track_timeline(
    track_id: int,
    before: str | None = Query(default=None, max_length=512),
    limit: int = Query(
        default=DEFAULT_TIMELINE_LIMIT,
        ge=1,
        le=MAX_TIMELINE_LIMIT,
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    started = perf_counter()
    request_id = coerce_operation_id()
    try:
        page = get_timeline(
            db,
            user_id=user.id,
            track_id=track_id,
            before=before,
            limit=limit,
        )
        _log_outcome(
            action="timeline_read",
            request_id=request_id,
            outcome="success",
            affected=len(page.items),
            started=started,
        )
        return {"items": page.items, "next_before": page.next_before}
    except EvidenceServiceError as exc:
        _raise_service_error(
            db,
            exc,
            action="timeline_read",
            request_id=request_id,
            started=started,
        )


@router.post("/{track_id}/evidence")
def add_evidence(
    track_id: int,
    payload: EvidenceCreateData,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    started = perf_counter()
    try:
        request_id = UUID(idempotency_key)
    except (ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_idempotency_key",
                "fields": [
                    {
                        "field": "Idempotency-Key",
                        "message": "Idempotency-Key must be a valid UUID.",
                    }
                ],
            },
        ) from exc

    try:
        result = create_evidence(
            db,
            user_id=user.id,
            track_id=track_id,
            data=payload,
            request_key=request_id,
            now=datetime.utcnow(),
        )
        db.commit()
        db.refresh(result.evidence)
        status_code = 200 if result.replayed else 201
        _log_outcome(
            action="evidence_create",
            request_id=request_id,
            outcome="replay" if result.replayed else "created",
            affected=0 if result.replayed else 1,
            started=started,
        )
        return JSONResponse(
            status_code=status_code,
            content=serialize_evidence(result.evidence),
        )
    except EvidenceServiceError as exc:
        _raise_service_error(
            db,
            exc,
            action="evidence_create",
            request_id=request_id,
            started=started,
        )
    except LifecycleEventError as exc:
        _raise_lifecycle_error(
            db,
            exc,
            action="evidence_create",
            request_id=request_id,
            started=started,
        )
    except IntegrityError:
        # A concurrent matching request can win the unique receipt race. Roll
        # back this attempt and resolve the now-durable receipt as a replay.
        db.rollback()
        try:
            result = create_evidence(
                db,
                user_id=user.id,
                track_id=track_id,
                data=payload,
                request_key=request_id,
                now=datetime.utcnow(),
            )
            if not result.replayed:
                db.rollback()
                _raise_integrity_error(
                    db,
                    action="evidence_create",
                    request_id=request_id,
                    started=started,
                )
            _log_outcome(
                action="evidence_create",
                request_id=request_id,
                outcome="replay",
                affected=0,
                started=started,
            )
            return JSONResponse(
                status_code=200,
                content=serialize_evidence(result.evidence),
            )
        except EvidenceServiceError as exc:
            _raise_service_error(
                db,
                exc,
                action="evidence_create",
                request_id=request_id,
                started=started,
            )


@router.patch("/{track_id}/evidence/{evidence_id}")
def patch_evidence(
    track_id: int,
    evidence_id: int,
    payload: EvidenceEditIn,
    x_operation_id: str | None = Header(None, alias="X-Operation-ID"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    operation_id = _operation_id(x_operation_id)
    started = perf_counter()
    supplied = payload.model_fields_set
    kwargs: dict[str, Any] = {}
    if "body" in supplied:
        kwargs["body"] = payload.body
    if "occurred_at" in supplied:
        kwargs["occurred_at"] = payload.occurred_at
    try:
        evidence = edit_evidence(
            db,
            user_id=user.id,
            track_id=track_id,
            evidence_id=evidence_id,
            version=payload.version,
            operation_id=operation_id,
            now=datetime.utcnow(),
            **kwargs,
        )
        db.commit()
        db.refresh(evidence)
        _log_outcome(
            action="evidence_edit",
            request_id=operation_id,
            outcome="success",
            affected=1,
            started=started,
        )
        return serialize_evidence(evidence)
    except EvidenceServiceError as exc:
        _raise_service_error(
            db,
            exc,
            action="evidence_edit",
            request_id=operation_id,
            started=started,
        )
    except LifecycleEventError as exc:
        _raise_lifecycle_error(
            db,
            exc,
            action="evidence_edit",
            request_id=operation_id,
            started=started,
        )
    except IntegrityError:
        _raise_integrity_error(
            db,
            action="evidence_edit",
            request_id=operation_id,
            started=started,
        )


@router.delete("/{track_id}/evidence/{evidence_id}", status_code=204)
def remove_evidence(
    track_id: int,
    evidence_id: int,
    x_operation_id: str | None = Header(None, alias="X-Operation-ID"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    operation_id = _operation_id(x_operation_id)
    started = perf_counter()
    try:
        result = delete_evidence(
            db,
            user_id=user.id,
            track_id=track_id,
            evidence_id=evidence_id,
            operation_id=operation_id,
            now=datetime.utcnow(),
        )
        db.commit()
        _log_outcome(
            action="evidence_delete",
            request_id=operation_id,
            outcome="deleted" if result.changed else "already_deleted",
            affected=1 if result.changed else 0,
            started=started,
        )
        return Response(status_code=204)
    except EvidenceServiceError as exc:
        _raise_service_error(
            db,
            exc,
            action="evidence_delete",
            request_id=operation_id,
            started=started,
        )
    except LifecycleEventError as exc:
        _raise_lifecycle_error(
            db,
            exc,
            action="evidence_delete",
            request_id=operation_id,
            started=started,
        )


@router.post("/{track_id}/applied-date-corrections")
def correct_track_applied_date(
    track_id: int,
    payload: AppliedDateCorrectionIn,
    x_operation_id: str | None = Header(None, alias="X-Operation-ID"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    operation_id = _operation_id(x_operation_id)
    started = perf_counter()
    try:
        track = correct_applied_date(
            db,
            user_id=user.id,
            track_id=track_id,
            applied_at=payload.applied_at,
            reason=payload.reason,
            operation_id=operation_id,
            now=datetime.utcnow(),
        )
        db.commit()
        db.refresh(track)
        _log_outcome(
            action="applied_date_correction",
            request_id=operation_id,
            outcome="success",
            affected=1,
            started=started,
        )
        return _track_response(track)
    except EvidenceServiceError as exc:
        _raise_service_error(
            db,
            exc,
            action="applied_date_correction",
            request_id=operation_id,
            started=started,
        )
    except LifecycleEventError as exc:
        _raise_lifecycle_error(
            db,
            exc,
            action="applied_date_correction",
            request_id=operation_id,
            started=started,
        )


@router.post("/{track_id}/status-corrections")
def correct_track_status(
    track_id: int,
    payload: StatusCorrectionIn,
    x_operation_id: str | None = Header(None, alias="X-Operation-ID"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    operation_id = _operation_id(x_operation_id)
    started = perf_counter()
    try:
        track = correct_latest_status(
            db,
            user_id=user.id,
            track_id=track_id,
            expected_event_id=payload.expected_event_id,
            restore_status=payload.restore_status,
            reason=payload.reason,
            operation_id=operation_id,
            now=datetime.utcnow(),
        )
        db.commit()
        db.refresh(track)
        _log_outcome(
            action="status_correction",
            request_id=operation_id,
            outcome="success",
            affected=1,
            started=started,
        )
        return _track_response(track)
    except EvidenceServiceError as exc:
        _raise_service_error(
            db,
            exc,
            action="status_correction",
            request_id=operation_id,
            started=started,
        )
    except LifecycleEventError as exc:
        _raise_lifecycle_error(
            db,
            exc,
            action="status_correction",
            request_id=operation_id,
            started=started,
        )
