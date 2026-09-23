from __future__ import annotations

import logging
from time import perf_counter

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..contact_schemas import (
    ApplicationContactCreateRequest,
    ContactContractError,
    ContactCreateRequest,
    ContactPatchRequest,
    InterviewCreateRequest,
    InterviewPatchRequest,
)
from ..database import get_db
from ..models import User
from ..services.calendar_export import build_interview_ics
from ..services.contacts import (
    ContactServiceError,
    _owned_interview,
    _owned_track,
    create_contact,
    create_interview,
    delete_contact,
    link_application_contact,
    list_application_contacts,
    list_contacts,
    list_interviews,
    patch_contact,
    patch_interview,
    serialize_contact,
    serialize_interview,
    unlink_application_contact,
)


router = APIRouter(prefix="/crm", tags=["contacts", "interviews"])
logger = logging.getLogger(__name__)


def _raise_safe(exc: Exception, db: Session, action: str, started: float):
    db.rollback()
    elapsed = int((perf_counter() - started) * 1000)
    if isinstance(exc, ContactServiceError):
        logger.info("f8_operation action=%s outcome=%s elapsed_ms=%s", action, exc.code, elapsed)
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc
    if isinstance(exc, ContactContractError):
        logger.info("f8_operation action=%s outcome=%s elapsed_ms=%s", action, exc.code, elapsed)
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": exc.message}) from exc
    if isinstance(exc, IntegrityError):
        logger.info("f8_operation action=%s outcome=conflict elapsed_ms=%s", action, elapsed)
        raise HTTPException(status_code=409, detail={"code": "conflict", "message": "The requested change conflicts with current data. Reload and retry."}) from exc
    logger.exception("f8_operation action=%s outcome=internal_error elapsed_ms=%s", action, elapsed)
    raise HTTPException(status_code=500, detail={"code": "internal_error", "message": "The request could not be completed."}) from exc


def _commit(db: Session, action: str, started: float) -> None:
    db.commit()
    logger.info("f8_operation action=%s outcome=success elapsed_ms=%s", action, int((perf_counter() - started) * 1000))


@router.get("/contacts")
def get_contacts(
    q: str = Query("", max_length=200),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return {"contacts": list_contacts(db, user_id=user.id, q=q, limit=limit)}


@router.post("/contacts", status_code=201)
def post_contact(
    payload: ContactCreateRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    started = perf_counter()
    try:
        contact, replayed = create_contact(db, user_id=user.id, operation_key=idempotency_key, payload=payload.model_dump())
        _commit(db, "contact_create", started)
        if replayed:
            response.status_code = 200
        return serialize_contact(contact)
    except Exception as exc:
        _raise_safe(exc, db, "contact_create", started)


@router.patch("/contacts/{contact_id}")
def update_contact(
    contact_id: int,
    payload: ContactPatchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    started = perf_counter()
    try:
        changes = payload.model_dump(exclude={"version"}, exclude_unset=True)
        contact = patch_contact(db, user_id=user.id, contact_id=contact_id, version=payload.version, changes=changes)
        _commit(db, "contact_patch", started)
        return serialize_contact(contact)
    except Exception as exc:
        _raise_safe(exc, db, "contact_patch", started)


@router.delete("/contacts/{contact_id}", status_code=204)
def remove_contact(
    contact_id: int,
    version: int = Query(..., gt=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    started = perf_counter()
    try:
        delete_contact(db, user_id=user.id, contact_id=contact_id, version=version)
        _commit(db, "contact_delete", started)
        return Response(status_code=204)
    except Exception as exc:
        _raise_safe(exc, db, "contact_delete", started)


@router.get("/tracks/{track_id}/contacts")
def get_track_contacts(
    track_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return {"contacts": list_application_contacts(db, user_id=user.id, track_id=track_id)}


@router.post("/tracks/{track_id}/contacts", status_code=201)
def post_track_contact(
    track_id: int,
    payload: ApplicationContactCreateRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    started = perf_counter()
    try:
        row, replayed = link_application_contact(db, user_id=user.id, track_id=track_id, operation_key=idempotency_key, payload=payload.model_dump())
        contact = list_application_contacts(db, user_id=user.id, track_id=track_id)
        result = next(item for item in contact if item["id"] == row.id)
        _commit(db, "application_contact_create", started)
        if replayed:
            response.status_code = 200
        return result
    except Exception as exc:
        _raise_safe(exc, db, "application_contact_create", started)


@router.delete("/tracks/{track_id}/contacts/{association_id}", status_code=204)
def delete_track_contact(
    track_id: int,
    association_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    started = perf_counter()
    try:
        unlink_application_contact(db, user_id=user.id, track_id=track_id, association_id=association_id)
        _commit(db, "application_contact_delete", started)
        return Response(status_code=204)
    except Exception as exc:
        _raise_safe(exc, db, "application_contact_delete", started)


@router.get("/tracks/{track_id}/interviews")
def get_track_interviews(
    track_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return {"interviews": list_interviews(db, user_id=user.id, track_id=track_id)}


@router.post("/tracks/{track_id}/interviews", status_code=201)
def post_track_interview(
    track_id: int,
    payload: InterviewCreateRequest,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    started = perf_counter()
    try:
        interview, replayed = create_interview(db, user_id=user.id, track_id=track_id, operation_key=idempotency_key, payload=payload.model_dump())
        result = serialize_interview(db, interview)
        _commit(db, "interview_create", started)
        if replayed:
            response.status_code = 200
        return result
    except Exception as exc:
        _raise_safe(exc, db, "interview_create", started)


@router.patch("/interviews/{interview_id}")
def update_interview(
    interview_id: int,
    payload: InterviewPatchRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    started = perf_counter()
    try:
        changes = payload.model_dump(exclude={"version"}, exclude_unset=True)
        interview = patch_interview(db, user_id=user.id, interview_id=interview_id, version=payload.version, changes=changes)
        result = serialize_interview(db, interview)
        _commit(db, "interview_patch", started)
        return result
    except Exception as exc:
        _raise_safe(exc, db, "interview_patch", started)


@router.get("/interviews/{interview_id}/calendar.ics")
def download_interview_calendar(
    interview_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Both lookups are owner-scoped. A foreign interview therefore has the same
    # 404 shape as a missing record and never becomes an ownership oracle.
    try:
        interview = _owned_interview(db, user.id, interview_id)
        track = _owned_track(db, user.id, interview.track_id)
    except ContactServiceError as exc:
        raise HTTPException(status_code=404, detail=exc.as_detail()) from exc
    content = build_interview_ics(interview, track)
    return StreamingResponse(
        iter([content]),
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="jobgrid_interview_{interview.id}.ics"'},
    )
