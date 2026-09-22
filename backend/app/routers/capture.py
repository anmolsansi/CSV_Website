from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Response
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..capture_schemas import CaptureRequestIn
from ..database import get_db
from ..models import User
from ..services.capture import (
    CaptureServiceError,
    capture_job,
    increment_capture_window,
)


router = APIRouter(prefix="/crm", tags=["crm"])
logger = logging.getLogger(__name__)


def _detail(exc: CaptureServiceError) -> dict[str, Any]:
    detail: dict[str, Any] = {"code": exc.code, "message": str(exc)}
    if exc.field is not None:
        detail["field"] = exc.field
    return detail


@router.post("/jobs/capture")
def capture_job_route(
    response: Response,
    payload: dict[str, Any] = Body(...),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Save one owned job without recording a visit or application."""
    started = perf_counter()
    try:
        # This commit is intentionally isolated so rejected authenticated attempts
        # still count across app processes and capture rollback cannot reset abuse state.
        increment_capture_window(db, user_id=user.id)

        try:
            request = CaptureRequestIn.model_validate(payload)
        except ValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "invalid_capture_payload",
                    "message": "Capture payload does not match the required contract.",
                    "errors": [
                        {
                            "field": ".".join(str(part) for part in item["loc"]),
                            "message": item["msg"],
                        }
                        for item in exc.errors()
                    ],
                },
            ) from exc

        if idempotency_key is None:
            raise CaptureServiceError(
                "missing_idempotency_key",
                "Idempotency-Key header is required.",
                status_code=422,
                field="Idempotency-Key",
            )

        try:
            result = capture_job(
                db,
                user_id=user.id,
                payload=request,
                request_key=idempotency_key,
            )
            db.commit()
        except IntegrityError:
            # A concurrent exact-URL request can win the unique(user_id,url)
            # race between lookup and flush. Roll back and replay once under the
            # same account lock so both requests resolve to the single row.
            db.rollback()
            result = capture_job(
                db,
                user_id=user.id,
                payload=request,
                request_key=idempotency_key,
            )
            db.commit()

        response.status_code = 201 if result.created else 200
        logger.info(
            "job_capture outcome=%s created=%s replayed=%s elapsed_ms=%s",
            "success",
            result.created,
            result.replayed,
            int((perf_counter() - started) * 1000),
        )
        return {
            "row_id": result.row.id,
            "created": result.created,
            "replayed": result.replayed,
            "matches": result.matches,
            "company_history_count": result.company_history_count,
        }
    except CaptureServiceError as exc:
        db.rollback()
        headers = (
            {"Retry-After": str(exc.retry_after)}
            if exc.retry_after is not None
            else None
        )
        logger.warning(
            "job_capture outcome=%s elapsed_ms=%s",
            exc.code,
            int((perf_counter() - started) * 1000),
        )
        raise HTTPException(
            status_code=exc.status_code,
            detail=_detail(exc),
            headers=headers,
        ) from exc
    except HTTPException:
        db.rollback()
        raise
