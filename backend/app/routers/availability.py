from __future__ import annotations

import logging
from time import perf_counter
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..availability_schemas import AvailabilityContractError
from ..config import settings
from ..database import get_db
from ..models import JobAvailability, User
from ..services.availability import (
    AvailabilityServiceError,
    enqueue_job_check,
    get_job_availability,
    owned_row_job_url,
    owned_track_job_url,
    process_job_check_request,
    serialize_job_availability,
    update_manual_availability,
)
from ..services.reminders import sync_availability_reminders


router = APIRouter(prefix="/crm", tags=["availability"])
logger = logging.getLogger(__name__)


class AvailabilityPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: StrictInt = Field(gt=0)
    deadline_at: str | None = None
    state: Literal["closed", "unknown"] | None = None
    confirm_state_change: StrictBool = False

    @model_validator(mode="after")
    def require_change(self):
        if not ({"deadline_at", "state"} & self.model_fields_set):
            raise ValueError("At least one availability field must change.")
        if self.state is not None and not self.confirm_state_change:
            raise ValueError("confirm_state_change=true is required for close or reopen.")
        if self.state is None and self.confirm_state_change:
            raise ValueError("confirm_state_change is only valid with a state change.")
        return self


def _request_id() -> str:
    return str(uuid4())


def _log(
    *,
    action: str,
    request_id: str,
    outcome: str,
    affected: int,
    started: float,
) -> None:
    logger.info(
        "availability_operation action=%s request_id=%s outcome=%s affected=%s elapsed_ms=%s",
        action,
        request_id,
        outcome,
        affected,
        int((perf_counter() - started) * 1000),
    )


def _raise_safe(
    exc: Exception,
    *,
    db: Session,
    action: str,
    request_id: str,
    started: float,
):
    db.rollback()
    if isinstance(exc, AvailabilityServiceError):
        _log(
            action=action,
            request_id=request_id,
            outcome=exc.code,
            affected=0,
            started=started,
        )
        headers = (
            {"Retry-After": str(exc.retry_after)}
            if exc.retry_after is not None
            else None
        )
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.as_detail(),
            headers=headers,
        ) from exc
    if isinstance(exc, AvailabilityContractError):
        _log(
            action=action,
            request_id=request_id,
            outcome=exc.code,
            affected=0,
            started=started,
        )
        raise HTTPException(
            status_code=422,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    if isinstance(exc, IntegrityError):
        _log(
            action=action,
            request_id=request_id,
            outcome="stale_version",
            affected=0,
            started=started,
        )
        raise HTTPException(
            status_code=409,
            detail={
                "code": "stale_version",
                "message": "Availability changed. Reload and retry.",
            },
        ) from exc
    logger.exception(
        "availability_operation action=%s request_id=%s outcome=internal_error affected=0 elapsed_ms=%s",
        action,
        request_id,
        int((perf_counter() - started) * 1000),
    )
    raise HTTPException(
        status_code=500,
        detail={
            "code": "internal_error",
            "message": "The availability request could not be completed.",
        },
    ) from exc


def _get_for_url(
    db: Session,
    *,
    user: User,
    job_url: str,
) -> dict:
    availability = get_job_availability(
        db,
        user_id=user.id,
        job_url=job_url,
    )
    return serialize_job_availability(
        db,
        user=user,
        job_url=job_url,
        availability=availability,
    )


def _patch_for_url(
    db: Session,
    *,
    user: User,
    job_url: str,
    payload: AvailabilityPatchRequest,
) -> dict:
    kwargs = {}
    if "deadline_at" in payload.model_fields_set:
        kwargs["deadline_input"] = payload.deadline_at
    availability = update_manual_availability(
        db,
        user_id=user.id,
        job_url=job_url,
        timezone_name=user.timezone,
        version=payload.version,
        state=payload.state,
        confirm_state_change=payload.confirm_state_change,
        **kwargs,
    )
    sync_availability_reminders(
        db,
        user_id=user.id,
        job_url=job_url,
    )
    db.commit()
    db.refresh(availability)
    return serialize_job_availability(
        db,
        user=user,
        job_url=job_url,
        availability=availability,
    )


def _enqueue_for_url(
    db: Session,
    *,
    user: User,
    job_url: str,
    background_tasks: BackgroundTasks,
) -> dict:
    if not settings.JOB_URL_CHECKS_ENABLED:
        raise AvailabilityServiceError(
            "job_url_checks_disabled",
            503,
            "Automatic link checks are disabled. Manual freshness controls remain available.",
        )

    availability = get_job_availability(
        db,
        user_id=user.id,
        job_url=job_url,
        for_update=True,
    )
    if availability is None:
        availability = JobAvailability(
            user_id=user.id,
            job_url=job_url,
            state="unknown",
            version=1,
        )
        db.add(availability)
        db.flush()

    request = enqueue_job_check(
        db,
        user_id=user.id,
        availability=availability,
    )
    request_id = request.id
    db.commit()
    background_tasks.add_task(process_job_check_request, request_id)
    return {
        "request_id": request_id,
        "status": "pending",
        "availability": serialize_job_availability(
            db,
            user=user,
            job_url=job_url,
            availability=availability,
        ),
    }


@router.get("/jobs/{row_id}/availability")
def get_row_availability(
    row_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    request_id = _request_id()
    started = perf_counter()
    try:
        job_url = owned_row_job_url(db, user_id=user.id, row_id=row_id)
        result = _get_for_url(db, user=user, job_url=job_url)
        _log(
            action="row_availability_get",
            request_id=request_id,
            outcome="success",
            affected=1,
            started=started,
        )
        return result
    except Exception as exc:
        _raise_safe(
            exc,
            db=db,
            action="row_availability_get",
            request_id=request_id,
            started=started,
        )


@router.patch("/jobs/{row_id}/availability")
def patch_row_availability(
    row_id: int,
    payload: AvailabilityPatchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    request_id = _request_id()
    started = perf_counter()
    try:
        job_url = owned_row_job_url(db, user_id=user.id, row_id=row_id)
        result = _patch_for_url(
            db,
            user=user,
            job_url=job_url,
            payload=payload,
        )
        _log(
            action="row_availability_patch",
            request_id=request_id,
            outcome="success",
            affected=1,
            started=started,
        )
        return result
    except Exception as exc:
        _raise_safe(
            exc,
            db=db,
            action="row_availability_patch",
            request_id=request_id,
            started=started,
        )


@router.post(
    "/jobs/{row_id}/availability/check",
    status_code=status.HTTP_202_ACCEPTED,
)
def check_row_availability(
    row_id: int,
    background_tasks: BackgroundTasks,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    del response
    request_id = _request_id()
    started = perf_counter()
    try:
        job_url = owned_row_job_url(db, user_id=user.id, row_id=row_id)
        result = _enqueue_for_url(
            db,
            user=user,
            job_url=job_url,
            background_tasks=background_tasks,
        )
        _log(
            action="row_availability_check",
            request_id=request_id,
            outcome="accepted",
            affected=1,
            started=started,
        )
        return result
    except Exception as exc:
        _raise_safe(
            exc,
            db=db,
            action="row_availability_check",
            request_id=request_id,
            started=started,
        )


@router.get("/tracks/{track_id}/availability")
def get_track_availability(
    track_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    request_id = _request_id()
    started = perf_counter()
    try:
        job_url = owned_track_job_url(db, user_id=user.id, track_id=track_id)
        result = _get_for_url(db, user=user, job_url=job_url)
        _log(
            action="track_availability_get",
            request_id=request_id,
            outcome="success",
            affected=1,
            started=started,
        )
        return result
    except Exception as exc:
        _raise_safe(
            exc,
            db=db,
            action="track_availability_get",
            request_id=request_id,
            started=started,
        )


@router.patch("/tracks/{track_id}/availability")
def patch_track_availability(
    track_id: int,
    payload: AvailabilityPatchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    request_id = _request_id()
    started = perf_counter()
    try:
        job_url = owned_track_job_url(db, user_id=user.id, track_id=track_id)
        result = _patch_for_url(
            db,
            user=user,
            job_url=job_url,
            payload=payload,
        )
        _log(
            action="track_availability_patch",
            request_id=request_id,
            outcome="success",
            affected=1,
            started=started,
        )
        return result
    except Exception as exc:
        _raise_safe(
            exc,
            db=db,
            action="track_availability_patch",
            request_id=request_id,
            started=started,
        )


@router.post(
    "/tracks/{track_id}/availability/check",
    status_code=status.HTTP_202_ACCEPTED,
)
def check_track_availability(
    track_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    request_id = _request_id()
    started = perf_counter()
    try:
        job_url = owned_track_job_url(db, user_id=user.id, track_id=track_id)
        result = _enqueue_for_url(
            db,
            user=user,
            job_url=job_url,
            background_tasks=background_tasks,
        )
        _log(
            action="track_availability_check",
            request_id=request_id,
            outcome="accepted",
            affected=1,
            started=started,
        )
        return result
    except Exception as exc:
        _raise_safe(
            exc,
            db=db,
            action="track_availability_check",
            request_id=request_id,
            started=started,
        )
