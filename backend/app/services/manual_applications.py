"""AL-13–AL-17: explicit, dated manual submission with one transaction.

This service never visits a job URL, submits an ATS form, or creates a CSV row.
The caller owns commit/rollback. Operational receipts are not lifecycle facts.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..browser_memory_schemas import validate_public_job_url
from ..models import JobTrack, ManualApplicationReceipt, User
from .job_identity import (
    JobIdentityError,
    apply_persisted_job_identity,
    canonicalize_job_url,
    find_applied_matches,
)
from .lifecycle import apply_job_track_changes
from .validation import ValidationContractError, parse_timestamp

RECEIPT_DAYS = 30
MAX_RECEIPTS_PER_USER = 10_000


class ManualApplicationError(ValueError):
    def __init__(
        self, code: str, message: str, *, status_code: int = 422,
        field: str = "__root__", matches: list[dict] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.field = field
        self.matches = matches

    def detail(self) -> dict:
        result = {
            "code": self.code,
            "fields": [{"field": self.field, "message": str(self)}],
        }
        if self.matches is not None:
            result["matches"] = self.matches
        return result


class ManualApplicationIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    url: str = Field(min_length=1, max_length=2048)
    company: str = Field(min_length=1, max_length=300)
    title: str = Field(min_length=1, max_length=300)
    applied_at: str = Field(min_length=1, max_length=40)
    confirmed: bool
    notes: str | None = Field(default=None, max_length=20000)
    follow_up_at: str | None = Field(default=None, max_length=40)
    acknowledge_possible_match: bool = False

    @field_validator("url")
    @classmethod
    def safe_url(cls, url: str) -> str:
        return validate_public_job_url(url)

    @field_validator("company", "title")
    @classmethod
    def required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be blank.")
        return value

    @field_validator("confirmed")
    @classmethod
    def literal_confirmation(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("Explicit submission confirmation is required.")
        return value


def validate_manual_request(payload: Any) -> tuple[ManualApplicationIn, datetime, datetime | None]:
    try:
        request = ManualApplicationIn.model_validate(payload)
    except ValidationError as exc:
        first = exc.errors()[0]
        field = str(first["loc"][0]) if first["loc"] else "__root__"
        raise ManualApplicationError(
            "invalid_manual_application", "Check the highlighted application details.",
            field=field,
        ) from exc

    for field, value in (
        ("applied_at", request.applied_at),
        ("follow_up_at", request.follow_up_at),
    ):
        if value is not None and ("T" not in value and "t" not in value):
            raise ManualApplicationError(
                "invalid_manual_application",
                "Use a date and time with a timezone offset.",
                field=field,
            )
    try:
        applied = parse_timestamp(request.applied_at, field="applied_at", allow_clear=False)
        follow_up = (
            parse_timestamp(request.follow_up_at, field="follow_up_at", allow_clear=False)
            if request.follow_up_at is not None else None
        )
    except ValidationContractError as exc:
        raise ManualApplicationError(
            "invalid_manual_application", exc.message, field=exc.field,
        ) from exc

    if applied > datetime.utcnow() + timedelta(minutes=5):
        raise ManualApplicationError(
            "invalid_manual_application", "Submission date cannot be in the future.",
            field="applied_at",
        )
    return request, applied, follow_up


def validate_manual_key(value: str | None) -> str:
    if value is None:
        raise ManualApplicationError(
            "missing_idempotency_key", "A UUID Idempotency-Key is required.",
            status_code=400, field="Idempotency-Key",
        )
    try:
        key = UUID(value)
    except (TypeError, ValueError, AttributeError) as exc:
        raise ManualApplicationError(
            "invalid_idempotency_key", "Idempotency-Key must be a canonical UUID.",
            status_code=400, field="Idempotency-Key",
        ) from exc
    if len(value) != 36 or str(key) != value:
        raise ManualApplicationError(
            "invalid_idempotency_key", "Idempotency-Key must be a canonical UUID.",
            status_code=400, field="Idempotency-Key",
        )
    return value


def _request_digest(request: ManualApplicationIn) -> str:
    body = request.model_dump()
    body["notes"] = body["notes"] or None
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _safe_matches(matches: list[dict]) -> list[dict]:
    # Return only explicitly owner-scoped prior application summary data.
    return [
        {
            "track_id": row["track_id"],
            "confidence": row["confidence"],
            "company": row["company"],
            "title": row["title"],
            "status": row["status"],
        }
        for row in matches[:20]
    ]


def record_manual_application(
    session: Session,
    *,
    user_id: int,
    payload: Any,
    request_key: str | None,
) -> tuple[dict, bool]:
    """Record submission or replay prior receipt; returns response and is_new.

    All writes, including the receipt, join the caller's single transaction.
    """
    request, applied_at, follow_up_at = validate_manual_request(payload)
    key = validate_manual_key(request_key)
    digest = _request_digest(request)
    if session.get_bind().dialect.name == "sqlite":
        connection = session.connection()
        if not connection.connection.driver_connection.in_transaction:
            connection.exec_driver_sql("BEGIN IMMEDIATE")

    owner = (
        session.query(User).filter(User.id == user_id).with_for_update().one_or_none()
    )
    if owner is None:
        raise ManualApplicationError(
            "account_unavailable", "The signed-in account is unavailable.",
            status_code=404,
        )
    now = datetime.utcnow()
    session.query(ManualApplicationReceipt).filter(
        ManualApplicationReceipt.user_id == user_id,
        ManualApplicationReceipt.created_at < now - timedelta(days=RECEIPT_DAYS),
    ).delete(synchronize_session=False)

    receipt = session.query(ManualApplicationReceipt).filter_by(
        user_id=user_id, request_key=key,
    ).one_or_none()
    if receipt is not None:
        if receipt.payload_hash != digest:
            raise ManualApplicationError(
                "idempotency_conflict",
                "This request key was already used with different application details.",
                status_code=409,
            )
        saved = dict(receipt.response_json)
        if not session.query(JobTrack.id).filter_by(
            id=saved["application_id"], user_id=user_id,
        ).first():
            raise ManualApplicationError(
                "application_deleted",
                "This application no longer exists. Review your history before recording again.",
                status_code=409,
            )
        return {**saved, "replayed": True}, False

    total = session.query(func.count(ManualApplicationReceipt.id)).filter_by(
        user_id=user_id,
    ).scalar()
    if total >= MAX_RECEIPTS_PER_USER:
        raise ManualApplicationError(
            "receipt_limit_reached", "Too many recent application confirmations.",
            status_code=429,
        )

    identity = canonicalize_job_url(request.url)
    exact = (
        session.query(JobTrack)
        .filter_by(user_id=user_id, url=request.url)
        .with_for_update()
        .one_or_none()
    )
    if exact is not None and exact.applied_at is not None:
        raise ManualApplicationError(
            "already_applied",
            "This job is already in your application history. Review it instead of creating a duplicate.",
            status_code=409,
            matches=[{
                "track_id": exact.id, "confidence": "exact",
                "company": exact.company, "title": exact.title, "status": exact.status,
            }],
        )

    canonical = (
        session.query(JobTrack)
        .filter(
            JobTrack.user_id == user_id,
            JobTrack.canonical_url_hash == identity.canonical_url_hash,
            JobTrack.canonical_url == identity.canonical_url,
            JobTrack.url != request.url,
        )
        .order_by(JobTrack.id.desc())
        .first()
    )
    if canonical is not None:
        raise ManualApplicationError(
            "canonical_duplicate",
            "A tracking-parameter variant of this job already exists. Review it first.",
            status_code=409,
            matches=[{
                "track_id": canonical.id, "confidence": "canonical",
                "company": canonical.company, "title": canonical.title,
                "status": canonical.status,
            }],
        )

    matches = find_applied_matches(
        session, user_id=user_id, url=request.url,
        company=request.company, title=request.title,
    )
    possible = [item for item in matches["matches"] if item["confidence"] == "possible"]
    if possible and not request.acknowledge_possible_match:
        raise ManualApplicationError(
            "possible_duplicate",
            "A similar submitted job already exists. Review it and confirm this is a separate application.",
            status_code=409, matches=_safe_matches(possible),
        )

    created = exact is None
    if created:
        track = JobTrack(
            user_id=user_id, url=request.url, company=request.company,
            title=request.title, status="opened", opened_at=None,
            last_opened_at=None, open_count=0, csv_row_id=None,
        )
        apply_persisted_job_identity(track)
        session.add(track)
        session.flush()
    else:
        track = exact
        if not track.company or not track.company.strip():
            track.company = request.company
        if not track.title or not track.title.strip():
            track.title = request.title
        apply_persisted_job_identity(track)

    if request.notes and not (track.notes or "").strip():
        track.notes = request.notes

    lifecycle_args = {
        "applied_at": applied_at,
        "infer_applied_at_from_status": False,
    }
    if created or track.status == "opened":
        lifecycle_args["status"] = "applied"
    if follow_up_at is not None and track.follow_up_at is None:
        lifecycle_args["follow_up_at"] = follow_up_at
    apply_job_track_changes(
        session, user_id=user_id, item=track, source="manual_application",
        operation_id=key, now=now, **lifecycle_args,
    )
    session.flush()
    result = {
        "application_id": track.id,
        "created": created,
        "replayed": False,
        "applied_at": track.applied_at.isoformat() + "Z",
        "status": track.status,
    }
    session.add(ManualApplicationReceipt(
        user_id=user_id, request_key=key, payload_hash=digest,
        response_json=result, created_at=now,
    ))
    session.flush()
    return result, created
