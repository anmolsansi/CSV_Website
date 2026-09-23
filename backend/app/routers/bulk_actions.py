from __future__ import annotations

import logging
from time import perf_counter
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import User
from ..services.bulk_actions import undo_action
from ..undo_schemas import UndoContractError


router = APIRouter(prefix="/crm/bulk-actions", tags=["bulk-actions"])
logger = logging.getLogger(__name__)


class UndoActionIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    mode: Literal["all_or_nothing", "restore_unchanged"] = "all_or_nothing"


def _raise_contract(exc: UndoContractError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


@router.post("/{action_id}/undo")
def undo_bulk_action(
    action_id: str,
    payload: UndoActionIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    started = perf_counter()
    try:
        result = undo_action(
            db,
            user_id=user.id,
            action_id=action_id,
            mode=payload.mode,
        )
        db.commit()
        logger.info(
            "bulk_undo operation_id=%s outcome=%s restored=%s conflicts=%s missing=%s elapsed_ms=%s",
            action_id,
            result.get("status"),
            result.get("restored", 0),
            result.get("conflicts", 0),
            result.get("missing", 0),
            int((perf_counter() - started) * 1000),
        )
        return result
    except UndoContractError as exc:
        # Conflict diagnostics are safe and useful to the owner. Persist the
        # per-effect conflict/missing states, but never any partial restore in
        # all_or_nothing mode.
        if exc.status_code == 409:
            db.commit()
        else:
            db.rollback()
        logger.warning(
            "bulk_undo operation_id=%s outcome=%s elapsed_ms=%s",
            action_id,
            exc.code,
            int((perf_counter() - started) * 1000),
        )
        _raise_contract(exc)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.exception(
            "bulk_undo operation_id=%s outcome=internal_error elapsed_ms=%s",
            action_id,
            int((perf_counter() - started) * 1000),
        )
        raise HTTPException(
            500,
            detail={
                "code": "internal_error",
                "fields": [{"field": "__root__", "message": "Undo could not be completed."}],
            },
        ) from exc
