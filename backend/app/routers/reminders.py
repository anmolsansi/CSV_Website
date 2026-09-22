from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from itsdangerous import BadSignature, URLSafeSerializer
from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import settings
from ..database import get_db
from ..models import AuditEvent, ReminderDelivery, ReminderPreference, User
from ..reminder_schemas import (
    ReminderPreferenceData,
    apply_delivery_transition,
    validate_preference_for_timezone,
)
from ..services.lifecycle import LifecycleEventError, coerce_operation_id
from ..services.reminders import email_delivery_availability, sync_user_reminders


router = APIRouter(prefix="/crm/reminders", tags=["reminders"])
CURSOR_SALT = "jobgrid-reminder-history-v1"


class StrictReminderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReminderPreferencePatch(StrictReminderRequest):
    version: str = Field(min_length=16, max_length=64)
    enabled: bool
    channel: Literal["in_app", "email"]
    local_time: str
    quiet_start: str
    quiet_end: str


class DeliveryVersionRequest(StrictReminderRequest):
    version: StrictInt = Field(gt=0)


class UnknownRetryRequest(DeliveryVersionRequest):
    confirm_possible_duplicate: bool


def _preference_values(pref: ReminderPreference | None) -> dict[str, object]:
    if pref is None:
        defaults = ReminderPreferenceData()
        return defaults.model_dump()
    return {
        "enabled": bool(pref.enabled),
        "channel": pref.channel,
        "local_time": pref.local_time,
        "quiet_start": pref.quiet_start,
        "quiet_end": pref.quiet_end,
    }


def _preference_version(pref: ReminderPreference | None) -> str:
    values = _preference_values(pref)
    canonical = "|".join(
        str(values[key])
        for key in ("enabled", "channel", "local_time", "quiet_start", "quiet_end")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def _preference_response(db: Session, user: User, pref: ReminderPreference | None) -> dict:
    values = _preference_values(pref)
    email_available, email_reason = email_delivery_availability(db, user=user)
    return {
        **values,
        "timezone": user.timezone,
        "version": _preference_version(pref),
        "email_available": email_available,
        "email_unavailable_reason": email_reason,
    }


def _cursor_serializer() -> URLSafeSerializer:
    return URLSafeSerializer(settings.SECRET_KEY, salt=CURSOR_SALT)


def _encode_cursor(delivery_id: int) -> str:
    return _cursor_serializer().dumps({"id": delivery_id})


def _decode_cursor(value: str) -> int:
    try:
        payload = _cursor_serializer().loads(value)
        delivery_id = payload["id"]
    except (BadSignature, KeyError, TypeError) as exc:
        raise HTTPException(
            422,
            detail={"code": "invalid_cursor", "message": "Invalid reminder cursor."},
        ) from exc
    if isinstance(delivery_id, bool) or not isinstance(delivery_id, int) or delivery_id <= 0:
        raise HTTPException(
            422,
            detail={"code": "invalid_cursor", "message": "Invalid reminder cursor."},
        )
    return delivery_id


def _delivery_summary(delivery: ReminderDelivery) -> dict:
    track = delivery.track
    unread = (
        delivery.channel == "in_app"
        and delivery.status == "sent"
        and delivery.read_at is None
    )
    return {
        "id": delivery.id,
        "track_id": delivery.track_id,
        "company": track.company if track is not None else None,
        "role": track.title if track is not None else None,
        "channel": delivery.channel,
        "status": delivery.status,
        "scheduled_at": delivery.scheduled_at,
        "sent_at": delivery.sent_at,
        "read_at": delivery.read_at,
        "unread": unread,
        "attempt_count": delivery.attempt_count,
        "last_error_code": delivery.last_error_code,
        "version": delivery.version,
        "possible_duplicate": delivery.status == "unknown",
    }


def _owned_delivery(db: Session, user_id: int, delivery_id: int) -> ReminderDelivery:
    delivery = (
        db.query(ReminderDelivery)
        .filter(
            ReminderDelivery.id == delivery_id,
            ReminderDelivery.user_id == user_id,
        )
        .first()
    )
    if delivery is None:
        raise HTTPException(
            404,
            detail={"code": "reminder_not_found", "message": "Reminder was not found."},
        )
    return delivery


def _operation_id(raw: str | None) -> UUID:
    try:
        return coerce_operation_id(raw)
    except LifecycleEventError as exc:
        raise HTTPException(
            400,
            detail={"code": exc.code, "message": exc.message},
        ) from exc


@router.get("/preferences")
def get_reminder_preferences(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    pref = (
        db.query(ReminderPreference)
        .filter(ReminderPreference.user_id == user.id)
        .first()
    )
    return _preference_response(db, user, pref)


@router.patch("/preferences")
def update_reminder_preferences(
    payload: ReminderPreferencePatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    pref = (
        db.query(ReminderPreference)
        .filter(ReminderPreference.user_id == user.id)
        .first()
    )
    if payload.version != _preference_version(pref):
        raise HTTPException(
            409,
            detail={
                "code": "preference_conflict",
                "message": "Reminder settings changed. Reload before saving.",
            },
        )

    try:
        data = ReminderPreferenceData(
            enabled=payload.enabled,
            channel=payload.channel,
            local_time=payload.local_time,
            quiet_start=payload.quiet_start,
            quiet_end=payload.quiet_end,
        )
        validate_preference_for_timezone(data, user.timezone)
    except (ValueError, ValidationError) as exc:
        raise HTTPException(
            422,
            detail={
                "code": getattr(exc, "code", "invalid_preferences"),
                "message": "Reminder times must use valid 24-hour HH:MM values.",
            },
        ) from exc

    if data.enabled and data.channel == "email":
        available, reason = email_delivery_availability(db, user=user)
        if not available:
            raise HTTPException(
                409,
                detail={
                    "code": "email_unavailable",
                    "message": "Email reminders are unavailable for this account.",
                    "reason": reason,
                },
            )

    if pref is None:
        pref = ReminderPreference(user_id=user.id)
        db.add(pref)
        db.flush()

    pref.enabled = data.enabled
    pref.channel = data.channel
    pref.local_time = data.local_time
    pref.quiet_start = data.quiet_start
    pref.quiet_end = data.quiet_end

    if not pref.enabled:
        rows = (
            db.query(ReminderDelivery)
            .filter(
                ReminderDelivery.user_id == user.id,
                ReminderDelivery.status.in_(("pending", "failed")),
            )
            .all()
        )
        for delivery in rows:
            apply_delivery_transition(delivery, "cancelled")
            delivery.lease_until = None
            delivery.next_attempt_at = None
            delivery.last_error_code = "opted_out"
    else:
        sync_user_reminders(
            db,
            user_id=user.id,
            now_utc=datetime.now(timezone.utc),
        )

    db.commit()
    db.refresh(pref)
    return _preference_response(db, user, pref)


@router.get("")
def list_reminders(
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = (
        db.query(ReminderDelivery)
        .filter(ReminderDelivery.user_id == user.id)
        .order_by(ReminderDelivery.id.desc())
    )
    if cursor:
        query = query.filter(ReminderDelivery.id < _decode_cursor(cursor))
    rows = query.limit(limit + 1).all()
    has_more = len(rows) > limit
    page = rows[:limit]
    return {
        "items": [_delivery_summary(item) for item in page],
        "next_cursor": _encode_cursor(page[-1].id) if has_more and page else None,
    }


@router.post("/{delivery_id}/retry")
def retry_unknown_reminder(
    delivery_id: int,
    payload: UnknownRetryRequest,
    x_operation_id: str | None = Header(None, alias="X-Operation-ID"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    operation_id = _operation_id(x_operation_id)
    delivery = _owned_delivery(db, user.id, delivery_id)
    if delivery.version != payload.version:
        raise HTTPException(
            409,
            detail={"code": "delivery_conflict", "message": "Reminder changed. Reload before retrying."},
        )
    if delivery.status != "unknown":
        raise HTTPException(
            409,
            detail={"code": "retry_not_allowed", "message": "Only uncertain reminders can be retried explicitly."},
        )
    if not payload.confirm_possible_duplicate:
        raise HTTPException(
            422,
            detail={
                "code": "duplicate_warning_required",
                "message": "Confirm that this retry may create a duplicate message.",
            },
        )

    apply_delivery_transition(
        delivery,
        "pending",
        explicit_unknown_retry=True,
    )
    delivery.lease_until = None
    delivery.next_attempt_at = None
    delivery.last_error_code = "explicit_unknown_retry"
    db.add(
        AuditEvent(
            user_id=user.id,
            event_type="reminder_unknown_retry",
            entity_type="reminder_delivery",
            entity_id=delivery.id,
            metadata_json={
                "operation_id": str(operation_id),
                "possible_duplicate_acknowledged": True,
            },
        )
    )
    db.commit()
    db.refresh(delivery)
    return _delivery_summary(delivery)


@router.post("/{delivery_id}/read")
def mark_in_app_reminder_read(
    delivery_id: int,
    payload: DeliveryVersionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    delivery = _owned_delivery(db, user.id, delivery_id)
    if delivery.version != payload.version:
        raise HTTPException(
            409,
            detail={"code": "delivery_conflict", "message": "Reminder changed. Reload before updating."},
        )
    if delivery.channel != "in_app" or delivery.status != "sent":
        raise HTTPException(
            409,
            detail={
                "code": "read_not_allowed",
                "message": "Only delivered in-app reminders can be marked read.",
            },
        )
    if delivery.read_at is None:
        delivery.read_at = datetime.now(timezone.utc)
        delivery.version = int(delivery.version or 0) + 1
        db.commit()
        db.refresh(delivery)
    return _delivery_summary(delivery)
