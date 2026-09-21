from __future__ import annotations

import logging
from datetime import datetime, timezone
from time import perf_counter
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import settings
from ..database import get_db
from ..models import User
from ..today_schemas import (
    SnoozeRequest,
    TodayContractError,
    WorkItemCreate,
    canonical_utc_timestamp,
)
from ..services.lifecycle import (
    LifecycleEventError,
    coerce_operation_id,
)
from ..services.today import (
    TodayServiceError,
    build_today_queue,
    create_from_view,
    create_work_item,
    resolve_followup,
    serialize_work_item,
    snooze_action,
    update_work_item,
)

router = APIRouter(prefix="/crm", tags=["today"])
logger = logging.getLogger(__name__)


class StrictTodayRequest(BaseModel):
    # JSON timestamps arrive as strings, so transport parsing cannot use model-wide strict mode.
    # Numeric concurrency/source identifiers remain StrictInt below.
    model_config = ConfigDict(extra="forbid")


class WorkItemCreateRequest(StrictTodayRequest):
    description: str = Field(min_length=1, max_length=500)
    due_at: datetime | None = None
    priority: StrictInt = Field(default=1, ge=0, le=3)
    track_id: StrictInt | None = Field(default=None, gt=0)
    row_id: StrictInt | None = Field(default=None, gt=0)
    source_view_id: StrictInt | None = Field(default=None, gt=0)

    @field_validator("description", mode="before")
    @classmethod
    def trim_create_description(cls, value):
        if not isinstance(value, str):
            return value
        trimmed = value.strip()
        if not trimmed:
            raise ValueError(
                "description must contain at least one non-whitespace character."
            )
        return trimmed

    @field_validator("due_at")
    @classmethod
    def normalize_create_due_at(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("due_at must include a timezone offset.")
        return value.astimezone(timezone.utc)


class SnoozeRequestBody(StrictTodayRequest):
    action_key: str = Field(min_length=1, max_length=255)
    until: datetime
    version: StrictInt = Field(gt=0)

    @field_validator("until")
    @classmethod
    def normalize_snooze_until(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("until must include a timezone offset.")
        return value.astimezone(timezone.utc)


class WorkItemPatch(StrictTodayRequest):
    version: StrictInt = Field(gt=0)
    description: str | None = Field(
        default=None,
        min_length=1,
        max_length=500,
    )
    due_at: datetime | None = None
    priority: StrictInt | None = Field(default=None, ge=0, le=3)
    state: Literal["pending", "done"] | None = None

    @field_validator("description", mode="before")
    @classmethod
    def trim_description(cls, value):
        if value is None or not isinstance(value, str):
            return value
        trimmed = value.strip()
        if not trimmed:
            raise ValueError(
                "description must contain at least one non-whitespace character."
            )
        return trimmed

    @field_validator("due_at")
    @classmethod
    def normalize_due_at(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("due_at must include a timezone offset.")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def require_change(self):
        changed = self.model_fields_set - {"version"}
        if not changed:
            raise ValueError(
                "At least one work-item field must change."
            )
        return self


class FollowUpResolveRequest(StrictTodayRequest):
    action_key: str = Field(min_length=1, max_length=255)
    resolution: Literal["clear", "reschedule"]
    follow_up_at: datetime | None = None

    @field_validator("follow_up_at")
    @classmethod
    def normalize_follow_up_at(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "follow_up_at must include a timezone offset."
            )
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_resolution(self):
        if (
            self.resolution == "reschedule"
            and self.follow_up_at is None
        ):
            raise ValueError(
                "follow_up_at is required when rescheduling."
            )
        if (
            self.resolution == "clear"
            and self.follow_up_at is not None
        ):
            raise ValueError(
                "follow_up_at must be omitted when clearing a follow-up."
            )
        return self


class FromViewRequest(StrictTodayRequest):
    view_id: StrictInt = Field(gt=0)
    limit: StrictInt = Field(default=20, ge=1, le=20)
    request_id: str = Field(min_length=36, max_length=36)

    @field_validator("request_id")
    @classmethod
    def validate_request_id(cls, value: str) -> str:
        try:
            return str(coerce_operation_id(value))
        except LifecycleEventError as exc:
            raise ValueError(exc.message) from exc


def _log_outcome(
    *,
    action: str,
    request_id: str,
    outcome: str,
    affected: int,
    started: float,
) -> None:
    logger.info(
        (
            "today_operation action=%s request_id=%s outcome=%s "
            "affected=%s elapsed_ms=%s"
        ),
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
    if isinstance(exc, (TodayServiceError, TodayContractError)):
        _log_outcome(
            action=action,
            request_id=request_id,
            outcome=exc.code,
            affected=0,
            started=started,
        )
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.as_detail(),
        ) from exc
    if isinstance(exc, LifecycleEventError):
        status_code = (
            404
            if exc.code
            in {
                "inaccessible_job_track",
                "inaccessible_csv_row",
            }
            else 400
        )
        _log_outcome(
            action=action,
            request_id=request_id,
            outcome=exc.code,
            affected=0,
            started=started,
        )
        raise HTTPException(
            status_code=status_code,
            detail={
                "code": exc.code,
                "message": exc.message,
            },
        ) from exc
    if isinstance(exc, IntegrityError):
        _log_outcome(
            action=action,
            request_id=request_id,
            outcome="conflict",
            affected=0,
            started=started,
        )
        raise HTTPException(
            status_code=409,
            detail={
                "code": "conflict",
                "message": (
                    "The Today action changed. Reload and retry."
                ),
            },
        ) from exc
    logger.exception(
        (
            "today_operation action=%s request_id=%s "
            "outcome=internal_error affected=0 elapsed_ms=%s"
        ),
        action,
        request_id,
        int((perf_counter() - started) * 1000),
    )
    raise HTTPException(
        status_code=500,
        detail={
            "code": "internal_error",
            "message": "The request could not be completed.",
        },
    ) from exc


@router.get("/today")
def get_today(
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    include_snoozed: bool = Query(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    request_id = str(coerce_operation_id())
    started = perf_counter()
    try:
        result = build_today_queue(
            db,
            user_id=user.id,
            timezone_name=user.timezone,
            secret_key=settings.SECRET_KEY,
            cursor=cursor,
            limit=limit,
            include_snoozed=include_snoozed,
        )
        _log_outcome(
            action="today_list",
            request_id=request_id,
            outcome="success",
            affected=len(result["items"]),
            started=started,
        )
        return result
    except Exception as exc:
        _raise_safe(
            exc,
            db=db,
            action="today_list",
            request_id=request_id,
            started=started,
        )


@router.post(
    "/work-items",
    status_code=status.HTTP_201_CREATED,
)
def post_work_item(
    payload: WorkItemCreateRequest,
    x_operation_id: str | None = Header(
        None,
        alias="X-Operation-ID",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        operation_id = coerce_operation_id(x_operation_id)
    except LifecycleEventError as exc:
        raise HTTPException(
            400,
            detail={
                "code": exc.code,
                "message": exc.message,
            },
        ) from exc
    request_id = str(operation_id)
    started = perf_counter()
    try:
        contract = WorkItemCreate.model_validate(payload.model_dump())
        item = create_work_item(
            db,
            user_id=user.id,
            payload=contract,
        )
        db.commit()
        db.refresh(item)
        result = serialize_work_item(item)
        _log_outcome(
            action="work_item_create",
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
            action="work_item_create",
            request_id=request_id,
            started=started,
        )


@router.patch("/work-items/{item_id}")
def patch_work_item(
    item_id: int,
    payload: WorkItemPatch,
    x_operation_id: str | None = Header(
        None,
        alias="X-Operation-ID",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        operation_id = coerce_operation_id(x_operation_id)
    except LifecycleEventError as exc:
        raise HTTPException(
            400,
            detail={
                "code": exc.code,
                "message": exc.message,
            },
        ) from exc
    request_id = str(operation_id)
    started = perf_counter()
    try:
        changes = payload.model_dump(
            exclude={"version"},
            exclude_unset=True,
        )
        item = update_work_item(
            db,
            user_id=user.id,
            item_id=item_id,
            version=payload.version,
            changes=changes,
        )
        db.commit()
        db.refresh(item)
        result = serialize_work_item(item)
        _log_outcome(
            action="work_item_patch",
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
            action="work_item_patch",
            request_id=request_id,
            started=started,
        )


@router.post("/today/snooze")
def post_snooze(
    payload: SnoozeRequestBody,
    x_operation_id: str | None = Header(
        None,
        alias="X-Operation-ID",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        operation_id = coerce_operation_id(x_operation_id)
    except LifecycleEventError as exc:
        raise HTTPException(
            400,
            detail={
                "code": exc.code,
                "message": exc.message,
            },
        ) from exc
    request_id = str(operation_id)
    started = perf_counter()
    try:
        contract = SnoozeRequest.model_validate(payload.model_dump())
        row = snooze_action(
            db,
            user_id=user.id,
            action_key=contract.action_key,
            until=contract.until,
            version=contract.version,
        )
        db.commit()
        result = {
            "action_key": row.action_key,
            "snoozed_until": canonical_utc_timestamp(
                row.snoozed_until
            ),
            "version": row.version,
        }
        _log_outcome(
            action="today_snooze",
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
            action="today_snooze",
            request_id=request_id,
            started=started,
        )


@router.post("/today/follow-up")
def post_follow_up_resolution(
    payload: FollowUpResolveRequest,
    x_operation_id: str | None = Header(
        None,
        alias="X-Operation-ID",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        operation_id = coerce_operation_id(x_operation_id)
    except LifecycleEventError as exc:
        raise HTTPException(
            400,
            detail={
                "code": exc.code,
                "message": exc.message,
            },
        ) from exc
    request_id = str(operation_id)
    started = perf_counter()
    try:
        track = resolve_followup(
            db,
            user_id=user.id,
            action_key=payload.action_key,
            resolution=payload.resolution,
            follow_up_at=payload.follow_up_at,
            operation_id=operation_id,
        )
        db.commit()
        db.refresh(track)
        result = {
            "track_id": track.id,
            "follow_up_at": (
                canonical_utc_timestamp(track.follow_up_at)
                if track.follow_up_at
                else None
            ),
            "status": track.status,
        }
        _log_outcome(
            action="today_followup_resolve",
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
            action="today_followup_resolve",
            request_id=request_id,
            started=started,
        )


@router.post("/today/from-view")
def post_from_view(
    payload: FromViewRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    request_id = payload.request_id
    started = perf_counter()
    try:
        result = create_from_view(
            db,
            user_id=user.id,
            view_id=payload.view_id,
            limit=payload.limit,
            request_id=coerce_operation_id(
                payload.request_id
            ),
        )
        db.commit()
        for item in result["items"]:
            db.refresh(item)
        response = {
            **{
                key: value
                for key, value in result.items()
                if key != "items"
            },
            "items": [
                serialize_work_item(item)
                for item in result["items"]
            ],
        }
        _log_outcome(
            action="today_from_view",
            request_id=request_id,
            outcome="success",
            affected=response["created"],
            started=started,
        )
        return response
    except Exception as exc:
        _raise_safe(
            exc,
            db=db,
            action="today_from_view",
            request_id=request_id,
            started=started,
        )
