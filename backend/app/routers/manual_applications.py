"""Session-authenticated manual application recording (AL Phase 3)."""
import logging
from time import perf_counter
from typing import Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import User
from ..services.job_identity import JobIdentityError
from ..services.lifecycle import LifecycleEventError
from ..services.manual_applications import (
    ManualApplicationError, record_manual_application,
)

router = APIRouter(prefix="/crm", tags=["crm"])
logger = logging.getLogger(__name__)


@router.post("/applications")
def create_manual_application(
    response: Response,
    payload: dict[str, Any] = Body(...),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Confirm a previously completed application, not submit it externally."""
    started = perf_counter()
    try:
        result, created = record_manual_application(
            db, user_id=user.id, payload=payload, request_key=idempotency_key,
        )
        db.commit()
        response.status_code = 201 if created else 200
        logger.info(
            "manual_application outcome=stored created=%s replayed=%s elapsed_ms=%s",
            created, result["replayed"], int((perf_counter() - started) * 1000),
        )
        return result
    except ManualApplicationError as exc:
        db.rollback()
        logger.info(
            "manual_application outcome=%s elapsed_ms=%s",
            exc.code, int((perf_counter() - started) * 1000),
        )
        raise HTTPException(exc.status_code, detail=exc.detail()) from exc
    except JobIdentityError as exc:
        db.rollback()
        raise HTTPException(
            422,
            detail={
                "code": "invalid_job_url",
                "fields": [{"field": "url", "message": "A valid HTTP(S) job URL is required."}],
            },
        ) from exc
    except LifecycleEventError as exc:
        db.rollback()
        code = 409 if exc.code == "event_key_conflict" else 422
        raise HTTPException(
            code,
            detail={
                "code": exc.code,
                "fields": [{"field": "__root__", "message": exc.message}],
            },
        ) from exc
    except IntegrityError as exc:
        db.rollback()
        logger.warning("manual_application outcome=concurrent_conflict")
        raise HTTPException(
            409,
            detail={
                "code": "concurrent_conflict",
                "fields": [{
                    "field": "__root__",
                    "message": "The application changed while saving. Reload and review your history.",
                }],
            },
        ) from exc
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("manual_application outcome=internal_error")
        raise HTTPException(
            500,
            detail={
                "code": "internal_error",
                "fields": [{
                    "field": "__root__",
                    "message": "Could not confirm the save. Check your history before retrying.",
                }],
            },
        ) from exc
