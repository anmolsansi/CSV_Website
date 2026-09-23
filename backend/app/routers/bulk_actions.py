from __future__ import annotations

import logging
from datetime import datetime
from time import perf_counter
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import JobTrack, User
from ..schemas import BulkUpdateIn
from ..services.bulk_actions import undo_action
from ..services.lifecycle import LifecycleEventError
from ..services.undo_foundation import create_bulk_action_journal, snapshot_changed_fields
from ..services.validation import ValidationContractError, normalize_bulk_ids, require_owned_bulk_ids
from ..undo_models import BulkAction
from ..undo_schemas import UndoContractError
from . import crm


# This router is registered before the legacy CRM router. The application bulk
# path intentionally keeps its public URL and response fields while adding the
# F10 journal/undo contract.
router = APIRouter(tags=["bulk-actions"])
logger = logging.getLogger(__name__)


class UndoActionIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    mode: Literal["all_or_nothing", "restore_unchanged"] = "all_or_nothing"


def _raise_contract(exc: UndoContractError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


def _bulk_action_response(action: BulkAction, *, replayed: bool = False) -> dict:
    result = dict(action.result_json or {})
    result.update(
        {
            "operation_id": action.id,
            "undo_expires_at": action.undo_expires_at.isoformat(),
            "undo_status": action.status,
            "replayed": replayed,
        }
    )
    return result


def _semantic_track_changes(item: JobTrack, data: dict, now: datetime) -> dict:
    """Translate request patch semantics into the fields Undo must snapshot."""
    changes = {
        key: value
        for key, value in data.items()
        if key in {"company", "title", "notes", "status", "applied_at", "follow_up_at"}
    }
    if data.get("mark_applied"):
        changes["status"] = "applied"
        if item.applied_at is None:
            changes["applied_at"] = now
    return changes


@router.patch("/crm/applications/bulk")
def bulk_update_apps_with_undo(
    payload: BulkUpdateIn,
    x_operation_id: str | None = Header(None, alias="X-Operation-ID"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    operation_id = crm._request_operation_id(x_operation_id)
    request_key = str(operation_id)
    started = perf_counter()
    try:
        existing = (
            db.query(BulkAction)
            .filter(BulkAction.user_id == user.id, BulkAction.request_key == request_key)
            .first()
        )
        if existing is not None:
            if existing.kind != "update_tracks":
                raise UndoContractError(
                    "request_key_conflict",
                    "This operation ID was already used for a different bulk action.",
                    status_code=409,
                    field="X-Operation-ID",
                )
            return _bulk_action_response(existing, replayed=True)

        normalized = normalize_bulk_ids(payload.ids, field="ids")
        query = db.query(JobTrack).filter(
            JobTrack.id.in_(normalized.ids),
            JobTrack.user_id == user.id,
        )
        if db.get_bind().dialect.name == "postgresql":
            query = query.with_for_update()
        items = query.all()
        by_id = {item.id: item for item in items}
        require_owned_bulk_ids(normalized, by_id, field="ids")
        ordered_items = [by_id[item_id] for item_id in normalized.ids]

        prepared = [
            (item, crm._prepare_application_patch(payload.patch, user=user, item=item))
            for item in ordered_items
        ]
        now = datetime.utcnow()
        effects = []
        for item, data in prepared:
            before = snapshot_changed_fields(
                "job_track",
                item,
                _semantic_track_changes(item, data, now),
            )
            crm._apply_track_patch(
                db,
                user_id=user.id,
                item=item,
                data=data,
                source="bulk_patch",
                operation_id=operation_id,
                now=now,
            )
            db.flush()
            if before:
                effects.append(
                    {
                        "entity_type": "job_track",
                        "entity_id": item.id,
                        "before_json": before,
                        "after_version": int(item.version),
                    }
                )

        legacy_result = {"updated": len(ordered_items), "failed": []}
        if not effects:
            db.commit()
            return {
                **legacy_result,
                "operation_id": None,
                "undo_expires_at": None,
                "undo_status": "no_change",
                "replayed": False,
            }

        action, replayed = create_bulk_action_journal(
            db,
            user_id=user.id,
            kind="update_tracks",
            request_key=request_key,
            effects=effects,
            result=legacy_result,
        )
        db.commit()
        crm._log_lifecycle_outcome(
            action="bulk_patch",
            operation_id=operation_id,
            outcome="success",
            affected=len(ordered_items),
            started=started,
        )
        return _bulk_action_response(action, replayed=replayed)
    except UndoContractError as exc:
        db.rollback()
        _raise_contract(exc)
    except ValidationContractError as exc:
        crm._raise_validation_http(
            db, exc, action="bulk_patch", operation_id=operation_id, started=started
        )
    except LifecycleEventError as exc:
        crm._raise_lifecycle_http(
            db,
            exc,
            action="bulk_patch",
            operation_id=operation_id,
            affected=0,
            started=started,
        )
    except IntegrityError as exc:
        crm._raise_integrity_http(
            db, exc, action="bulk_patch", operation_id=operation_id, started=started
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        crm._raise_unexpected_http(
            db, exc, action="bulk_patch", operation_id=operation_id, started=started
        )


@router.post("/crm/bulk-actions/{action_id}/undo")
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
