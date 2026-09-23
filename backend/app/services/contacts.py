from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..contact_models import ApplicationContact, Contact, Interview, MutationReceipt
from ..contact_schemas import ContactContractError, validate_interview_window
from ..models import JobTrack


RECEIPT_RETENTION_DAYS = 30


class ContactServiceError(ValueError):
    def __init__(self, code: str, status_code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.message = message

    def as_detail(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


def _hash_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _key_text(operation_key: str) -> str:
    try:
        return str(UUID(str(operation_key)))
    except (ValueError, TypeError) as exc:
        raise ContactServiceError("invalid_idempotency_key", 422, "Idempotency-Key must be a UUID.") from exc


def _owned_track(db: Session, user_id: int, track_id: int) -> JobTrack:
    track = db.query(JobTrack).filter(JobTrack.id == track_id, JobTrack.user_id == user_id).first()
    if track is None:
        raise ContactServiceError("not_found", 404, "Application not found.")
    return track


def _owned_contact(db: Session, user_id: int, contact_id: int, *, include_deleted: bool = False) -> Contact:
    query = db.query(Contact).filter(Contact.id == contact_id, Contact.user_id == user_id)
    if not include_deleted:
        query = query.filter(Contact.is_deleted.is_(False))
    contact = query.first()
    if contact is None:
        raise ContactServiceError("not_found", 404, "Contact not found.")
    return contact


def _owned_interview(db: Session, user_id: int, interview_id: int) -> Interview:
    interview = db.query(Interview).filter(Interview.id == interview_id, Interview.user_id == user_id).first()
    if interview is None:
        raise ContactServiceError("not_found", 404, "Interview not found.")
    return interview


def _receipt(db: Session, user_id: int, scope: str, operation_key: str, payload: dict[str, Any]) -> MutationReceipt | None:
    key = _key_text(operation_key)
    payload_hash = _hash_payload(payload)
    existing = db.query(MutationReceipt).filter(
        MutationReceipt.user_id == user_id,
        MutationReceipt.scope == scope,
        MutationReceipt.operation_key == key,
    ).first()
    if existing is not None and existing.payload_hash != payload_hash:
        raise ContactServiceError("idempotency_conflict", 409, "This Idempotency-Key was already used with a different payload.")
    return existing


def _record_receipt(db: Session, *, user_id: int, scope: str, operation_key: str, payload: dict[str, Any], entity_type: str, entity_id: int) -> None:
    db.add(MutationReceipt(
        user_id=user_id,
        scope=scope,
        operation_key=_key_text(operation_key),
        payload_hash=_hash_payload(payload),
        result_entity_type=entity_type,
        result_entity_id=str(entity_id),
    ))


def prune_mutation_receipts(db: Session, *, reference: datetime | None = None) -> int:
    cutoff = (reference or datetime.utcnow()) - timedelta(days=RECEIPT_RETENTION_DAYS)
    return db.query(MutationReceipt).filter(MutationReceipt.created_at < cutoff).delete(synchronize_session=False)


def serialize_contact(contact: Contact, *, include_private: bool = True) -> dict[str, Any]:
    if contact.is_deleted:
        return {
            "id": contact.id,
            "name": "Deleted contact",
            "email": None,
            "profile_url": None,
            "company_display": None,
            "notes": None,
            "version": contact.version,
            "is_deleted": True,
            "created_at": contact.created_at,
            "updated_at": contact.updated_at,
        }
    return {
        "id": contact.id,
        "name": contact.name,
        "email": contact.email if include_private else None,
        "profile_url": contact.profile_url,
        "company_display": contact.company_display,
        "notes": contact.notes if include_private else None,
        "version": contact.version,
        "is_deleted": False,
        "created_at": contact.created_at,
        "updated_at": contact.updated_at,
    }


def list_contacts(db: Session, *, user_id: int, q: str = "", limit: int = 50) -> list[dict[str, Any]]:
    query = db.query(Contact).filter(Contact.user_id == user_id, Contact.is_deleted.is_(False))
    if q:
        pattern = f"%{q.strip()}%"
        query = query.filter(or_(Contact.name.ilike(pattern), Contact.email.ilike(pattern), Contact.company_display.ilike(pattern)))
    return [serialize_contact(item) for item in query.order_by(Contact.name.asc(), Contact.id.asc()).limit(limit).all()]


def create_contact(db: Session, *, user_id: int, operation_key: str, payload: dict[str, Any]) -> tuple[Contact, bool]:
    existing = _receipt(db, user_id, "contact:create", operation_key, payload)
    if existing:
        return _owned_contact(db, user_id, int(existing.result_entity_id), include_deleted=True), True
    contact = Contact(user_id=user_id, **payload)
    db.add(contact)
    db.flush()
    _record_receipt(db, user_id=user_id, scope="contact:create", operation_key=operation_key, payload=payload, entity_type="contact", entity_id=contact.id)
    return contact, False


def patch_contact(db: Session, *, user_id: int, contact_id: int, version: int, changes: dict[str, Any]) -> Contact:
    contact = _owned_contact(db, user_id, contact_id)
    if contact.version != version:
        raise ContactServiceError("stale_version", 409, "Contact changed. Reload and retry.")
    for key, value in changes.items():
        setattr(contact, key, value)
    contact.version += 1
    contact.updated_at = datetime.utcnow()
    db.flush()
    return contact


def delete_contact(db: Session, *, user_id: int, contact_id: int, version: int) -> Contact:
    contact = _owned_contact(db, user_id, contact_id)
    if contact.version != version:
        raise ContactServiceError("stale_version", 409, "Contact changed. Reload and retry.")
    contact.is_deleted = True
    contact.version += 1
    contact.updated_at = datetime.utcnow()
    db.flush()
    return contact


def list_application_contacts(db: Session, *, user_id: int, track_id: int) -> list[dict[str, Any]]:
    _owned_track(db, user_id, track_id)
    rows = db.query(ApplicationContact, Contact).join(Contact, Contact.id == ApplicationContact.contact_id).filter(
        ApplicationContact.user_id == user_id,
        ApplicationContact.track_id == track_id,
        Contact.user_id == user_id,
    ).order_by(ApplicationContact.id.asc()).all()
    return [{
        "id": link.id,
        "role": link.role,
        "referral_source": link.referral_source,
        "contact": serialize_contact(contact),
    } for link, contact in rows]


def link_application_contact(db: Session, *, user_id: int, track_id: int, operation_key: str, payload: dict[str, Any]) -> tuple[ApplicationContact, bool]:
    _owned_track(db, user_id, track_id)
    _owned_contact(db, user_id, int(payload["contact_id"]))
    scope = f"application-contact:create:{track_id}"
    replay = _receipt(db, user_id, scope, operation_key, payload)
    if replay:
        row = db.query(ApplicationContact).filter(ApplicationContact.id == int(replay.result_entity_id), ApplicationContact.user_id == user_id).first()
        if row:
            return row, True
    existing = db.query(ApplicationContact).filter(
        ApplicationContact.user_id == user_id,
        ApplicationContact.track_id == track_id,
        ApplicationContact.contact_id == int(payload["contact_id"]),
        ApplicationContact.role == payload["role"],
    ).first()
    if existing:
        return existing, True
    row = ApplicationContact(user_id=user_id, track_id=track_id, **payload)
    db.add(row)
    db.flush()
    _record_receipt(db, user_id=user_id, scope=scope, operation_key=operation_key, payload=payload, entity_type="application_contact", entity_id=row.id)
    return row, False


def unlink_application_contact(db: Session, *, user_id: int, track_id: int, association_id: int) -> None:
    _owned_track(db, user_id, track_id)
    row = db.query(ApplicationContact).filter(
        ApplicationContact.id == association_id,
        ApplicationContact.user_id == user_id,
        ApplicationContact.track_id == track_id,
    ).first()
    if row is None:
        raise ContactServiceError("not_found", 404, "Application contact link not found.")
    db.delete(row)
    db.flush()


def _overlap_ids(db: Session, *, user_id: int, starts_at: datetime, ends_at: datetime, exclude_id: int | None = None) -> list[int]:
    query = db.query(Interview.id).filter(
        Interview.user_id == user_id,
        Interview.status == "scheduled",
        Interview.starts_at < ends_at,
        Interview.ends_at > starts_at,
    )
    if exclude_id is not None:
        query = query.filter(Interview.id != exclude_id)
    return [row[0] for row in query.order_by(Interview.starts_at.asc()).all()]


def serialize_interview(db: Session, interview: Interview) -> dict[str, Any]:
    contact = None
    if interview.contact_id is not None:
        contact = db.query(Contact).filter(Contact.id == interview.contact_id, Contact.user_id == interview.user_id).first()
    return {
        "id": interview.id,
        "track_id": interview.track_id,
        "contact_id": interview.contact_id,
        "contact": serialize_contact(contact) if contact else None,
        "starts_at": interview.starts_at,
        "ends_at": interview.ends_at,
        "timezone": interview.timezone,
        "kind": interview.kind,
        "meeting_url": interview.meeting_url,
        "location": interview.location,
        "status": interview.status,
        "notes": interview.notes,
        "round_label": interview.round_label,
        "preparation_notes": interview.preparation_notes,
        "version": interview.version,
        "sequence": max(interview.version - 1, 0),
        "overlap_interview_ids": _overlap_ids(db, user_id=interview.user_id, starts_at=interview.starts_at, ends_at=interview.ends_at, exclude_id=interview.id) if interview.status == "scheduled" else [],
        "created_at": interview.created_at,
        "updated_at": interview.updated_at,
    }


def list_interviews(db: Session, *, user_id: int, track_id: int) -> list[dict[str, Any]]:
    _owned_track(db, user_id, track_id)
    rows = db.query(Interview).filter(Interview.user_id == user_id, Interview.track_id == track_id).order_by(Interview.starts_at.asc(), Interview.id.asc()).all()
    return [serialize_interview(db, row) for row in rows]


def create_interview(db: Session, *, user_id: int, track_id: int, operation_key: str, payload: dict[str, Any]) -> tuple[Interview, bool]:
    _owned_track(db, user_id, track_id)
    if payload.get("contact_id") is not None:
        _owned_contact(db, user_id, int(payload["contact_id"]))
    starts_at, ends_at = validate_interview_window(payload["starts_at"], payload["ends_at"])
    normalized = {**payload, "starts_at": starts_at, "ends_at": ends_at}
    scope = f"interview:create:{track_id}"
    replay = _receipt(db, user_id, scope, operation_key, normalized)
    if replay:
        return _owned_interview(db, user_id, int(replay.result_entity_id)), True
    interview = Interview(user_id=user_id, track_id=track_id, **normalized)
    db.add(interview)
    db.flush()
    _record_receipt(db, user_id=user_id, scope=scope, operation_key=operation_key, payload=normalized, entity_type="interview", entity_id=interview.id)
    return interview, False


def patch_interview(db: Session, *, user_id: int, interview_id: int, version: int, changes: dict[str, Any]) -> Interview:
    interview = _owned_interview(db, user_id, interview_id)
    if interview.version != version:
        raise ContactServiceError("stale_version", 409, "Interview changed. Reload and retry.")
    if "contact_id" in changes and changes["contact_id"] is not None:
        _owned_contact(db, user_id, int(changes["contact_id"]))
    starts_value = changes.get("starts_at", interview.starts_at)
    ends_value = changes.get("ends_at", interview.ends_at)
    if isinstance(starts_value, datetime) and starts_value.tzinfo is None:
        starts_at = starts_value
    else:
        starts_at, _ = validate_interview_window(starts_value, ends_value if getattr(ends_value, "tzinfo", None) else ends_value.replace(tzinfo=None))
    if isinstance(ends_value, datetime) and ends_value.tzinfo is None:
        ends_at = ends_value
    else:
        ends_at = ends_value
    if getattr(starts_value, "tzinfo", None) is not None or getattr(ends_value, "tzinfo", None) is not None:
        starts_at, ends_at = validate_interview_window(
            starts_value if getattr(starts_value, "tzinfo", None) is not None else starts_value.replace(tzinfo=__import__('datetime').timezone.utc),
            ends_value if getattr(ends_value, "tzinfo", None) is not None else ends_value.replace(tzinfo=__import__('datetime').timezone.utc),
        )
    elif ends_at <= starts_at or (ends_at - starts_at).total_seconds() > 86400:
        raise ContactContractError("invalid_interview_range", "Interview end must be after start and duration cannot exceed 24 hours.")
    changes = {**changes, "starts_at": starts_at, "ends_at": ends_at}
    for key, value in changes.items():
        setattr(interview, key, value)
    interview.version += 1
    interview.updated_at = datetime.utcnow()
    db.flush()
    return interview
