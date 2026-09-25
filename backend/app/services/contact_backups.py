from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid5

from pydantic import ValidationError
from sqlalchemy.orm import Session

from .backup_sessions import atomic_restore, snapshot_export

from ..backup_schemas import BackupContractError, parse_backup_json, validate_backup_v2
from ..contact_models import ApplicationContact, Contact, Interview, MutationReceipt
from ..contact_schemas import ContactCreateRequest, InterviewCreateRequest, ApplicationContactCreateRequest
from ..backup_schemas import MAX_TOTAL_RECORDS
from ..models import JobTrack
from .backups import export_backup_v2, restore_backup_payload


F8_BACKUP_SCHEMA_REVISION = "1.0.0"
F8_BACKUP_KEY = "f8_private"


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise BackupContractError("invalid_f8_timestamp", 400, "F8 backup timestamps require an explicit timezone.")
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _checksum(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _ref(backup_id: UUID, section: str, source_id: int) -> str:
    return str(uuid5(backup_id, f"f8:{section}:{source_id}"))


def _base_track_refs(payload: dict[str, Any]) -> dict[str, str]:
    return {
        item["url"]: item["backup_ref"]
        for item in payload.get("sections", {}).get("job_tracks", [])
    }


@snapshot_export
def export_backup_v2_with_contacts(db: Session, user_id: int) -> dict[str, Any]:
    """Add the F8 durable private graph without changing legacy v2 validators.

    Accounts with no F8 private records keep the exact frozen v2 envelope. This
    preserves compatibility with existing validators and release contracts. The
    checksummed F8 extension is emitted only when it carries private F8 content.
    """
    payload = export_backup_v2(db, user_id)
    backup_id = UUID(payload["backup_id"])
    track_refs = _base_track_refs(payload)

    contacts = db.query(Contact).filter(Contact.user_id == user_id).order_by(Contact.id.asc()).all()
    links = db.query(ApplicationContact).filter(ApplicationContact.user_id == user_id).order_by(ApplicationContact.id.asc()).all()
    interviews = db.query(Interview).filter(Interview.user_id == user_id).order_by(Interview.id.asc()).all()

    if not contacts and not links and not interviews:
        return payload

    owned_tracks = {item.id: item for item in db.query(JobTrack).filter(JobTrack.user_id == user_id).all()}

    contact_refs = {item.id: _ref(backup_id, "contacts", item.id) for item in contacts}
    sections = {
        "contacts": [
            {
                "backup_ref": contact_refs[item.id],
                "name": item.name,
                "email": item.email,
                "profile_url": item.profile_url,
                "company_display": item.company_display,
                "notes": item.notes,
                "version": item.version,
                "created_at": _utc_iso(item.created_at),
                "updated_at": _utc_iso(item.updated_at),
                "is_deleted": item.is_deleted,
            }
            for item in contacts
        ],
        "application_contacts": [],
        "interviews": [],
    }

    for item in links:
        track = owned_tracks.get(item.track_id)
        track_ref = track_refs.get(track.url) if track else None
        contact_ref = contact_refs.get(item.contact_id)
        if track_ref is None or contact_ref is None:
            raise BackupContractError(
                "conflicting_reference_graph",
                409,
                "F8 application contact references data outside the authenticated backup snapshot.",
                section="application_contacts",
            )
        sections["application_contacts"].append({
            "backup_ref": _ref(backup_id, "application_contacts", item.id),
            "track_ref": track_ref,
            "contact_ref": contact_ref,
            "role": item.role,
            "referral_source": item.referral_source,
            "created_at": _utc_iso(item.created_at),
        })

    for item in interviews:
        track = owned_tracks.get(item.track_id)
        track_ref = track_refs.get(track.url) if track else None
        if track_ref is None or (item.contact_id is not None and item.contact_id not in contact_refs):
            raise BackupContractError(
                "conflicting_reference_graph",
                409,
                "F8 interview references data outside the authenticated backup snapshot.",
                section="interviews",
            )
        sections["interviews"].append({
            "backup_ref": _ref(backup_id, "interviews", item.id),
            "track_ref": track_ref,
            "contact_ref": contact_refs.get(item.contact_id),
            "starts_at": _utc_iso(item.starts_at),
            "ends_at": _utc_iso(item.ends_at),
            "timezone": item.timezone,
            "kind": item.kind,
            "meeting_url": item.meeting_url,
            "location": item.location,
            "status": item.status,
            "notes": item.notes,
            "round_label": item.round_label,
            "preparation_notes": item.preparation_notes,
            "version": item.version,
            "created_at": _utc_iso(item.created_at),
            "updated_at": _utc_iso(item.updated_at),
        })

    extension = {"schema_revision": F8_BACKUP_SCHEMA_REVISION, "sections": sections}
    extension["checksum_sha256"] = _checksum(extension)
    payload[F8_BACKUP_KEY] = extension
    return payload


def _validate_extension(extension: Any) -> dict[str, Any]:
    if not isinstance(extension, dict):
        raise BackupContractError("invalid_f8_backup", 400, "F8 backup extension must be an object.")
    allowed = {"schema_revision", "sections", "checksum_sha256"}
    if set(extension) != allowed or extension.get("schema_revision") != F8_BACKUP_SCHEMA_REVISION:
        raise BackupContractError("invalid_f8_backup", 400, "F8 backup extension has an unsupported schema.")
    sections = extension.get("sections")
    if not isinstance(sections, dict) or set(sections) != {"contacts", "application_contacts", "interviews"}:
        raise BackupContractError("invalid_f8_backup", 400, "F8 backup extension sections are invalid.")
    for name, records in sections.items():
        if not isinstance(records, list):
            raise BackupContractError("invalid_f8_backup", 400, f"F8 section {name} must be a list.")
    signed = {"schema_revision": extension["schema_revision"], "sections": sections}
    if extension.get("checksum_sha256") != _checksum(signed):
        raise BackupContractError("checksum_mismatch", 400, "F8 backup extension checksum does not match its contents.")
    models = {"contacts": ContactCreateRequest, "application_contacts": ApplicationContactCreateRequest,
              "interviews": InterviewCreateRequest}
    seen: set[str] = set()
    if sum(len(records) for records in sections.values()) > MAX_TOTAL_RECORDS:
        raise BackupContractError("too_many_records", 413, "Backup extension exceeds the record limit.")
    try:
        for name, records in sections.items():
            model = models[name]
            data_fields = set(model.model_fields) - {"contact_id"}
            metadata_fields = {"backup_ref", "created_at"}
            if name != "application_contacts":
                metadata_fields |= {"updated_at", "version"}
            if name == "contacts":
                metadata_fields.add("is_deleted")
            else:
                metadata_fields |= {"track_ref", "contact_ref"}
            for item in records:
                if not isinstance(item, dict) or set(item) != data_fields | metadata_fields:
                    raise ValueError("Invalid record fields")
                ref = item["backup_ref"]
                if not isinstance(ref, str) or str(UUID(ref)) != ref or ref in seen:
                    raise ValueError("Invalid or duplicate backup reference")
                seen.add(ref)
                for field in ("track_ref", "contact_ref"):
                    value = item.get(field)
                    if value is not None and (not isinstance(value, str) or str(UUID(value)) != value):
                        raise ValueError("Invalid relationship reference")
                for field in ("created_at", "updated_at", "starts_at", "ends_at"):
                    if field in item:
                        _parse_utc(item[field])
                if "version" in item and (type(item["version"]) is not int or item["version"] < 1):
                    raise ValueError("Invalid version")
                if name == "contacts" and type(item["is_deleted"]) is not bool:
                    raise ValueError("Invalid deletion state")
                data = {key: item[key] for key in data_fields}
                if name == "application_contacts":
                    data["contact_id"] = 1  # Validate the portable role/text, not a source database ID.
                model.model_validate(data)
    except (ValueError, TypeError, KeyError, AttributeError, ValidationError) as exc:
        raise BackupContractError("invalid_f8_backup", 400, "F8 backup contains an invalid record.") from exc
    return sections


def _receipt_entity(db: Session, user_id: int, scope: str, backup_ref: str, record: dict[str, Any]) -> int | None:
    existing = db.query(MutationReceipt).filter(
        MutationReceipt.user_id == user_id,
        MutationReceipt.scope == scope,
        MutationReceipt.operation_key == backup_ref,
    ).first()
    if existing is None:
        return None
    payload_hash = _checksum(record)
    if existing.payload_hash != payload_hash:
        raise BackupContractError("restore_conflict", 409, "Previously restored F8 record now has different content.")
    return int(existing.result_entity_id)


def _write_receipt(db: Session, user_id: int, scope: str, record: dict[str, Any], entity_type: str, entity_id: int) -> None:
    db.add(MutationReceipt(
        user_id=user_id,
        operation_key=record["backup_ref"],
        scope=scope,
        payload_hash=_checksum(record),
        result_entity_type=entity_type,
        result_entity_id=str(entity_id),
    ))


@atomic_restore
def restore_backup_payload_with_contacts(db: Session, user_id: int, raw: bytes, mode: str, *, _base_result: dict[str, Any] | None = None) -> dict[str, Any]:
    parsed = parse_backup_json(raw)
    if not isinstance(parsed, dict):
        raise BackupContractError("invalid_backup", 400, "Backup document must be an object.")
    extension = parsed.pop(F8_BACKUP_KEY, None)
    base_raw = json.dumps(parsed, ensure_ascii=False, allow_nan=False).encode("utf-8")
    sections = _validate_extension(extension) if extension is not None else None
    if sections is None:
        return _base_result if _base_result is not None else restore_backup_payload(db, user_id, base_raw, mode)

    validate_backup_v2(parsed)
    base_tracks = {item["backup_ref"]: item for item in parsed.get("sections", {}).get("job_tracks", [])}
    known_contact_refs = {item.get("backup_ref") for item in sections["contacts"]}
    for item in sections["application_contacts"]:
        if item.get("track_ref") not in base_tracks or item.get("contact_ref") not in known_contact_refs:
            raise BackupContractError("conflicting_reference_graph", 409, "F8 contact link contains an unresolved reference.")
    for item in sections["interviews"]:
        if item.get("track_ref") not in base_tracks or (item.get("contact_ref") is not None and item.get("contact_ref") not in known_contact_refs):
            raise BackupContractError("conflicting_reference_graph", 409, "F8 interview contains an unresolved reference.")
    # Receipt hash conflicts must fail preflight as well as an actual restore.
    replay_ids = {name: [_receipt_entity(db, user_id, scope, item["backup_ref"], item)
                         for item in sections[name]]
                  for name, scope in (("contacts", "backup:contact"), ("interviews", "backup:interview"))}
    result = _base_result if _base_result is not None else restore_backup_payload(db, user_id, base_raw, mode)
    destination_tracks: dict[str, JobTrack] = {}
    for ref, record in base_tracks.items():
        track = db.query(JobTrack).filter(JobTrack.user_id == user_id, JobTrack.url == record["url"]).first()
        if track is not None:
            destination_tracks[ref] = track

    if mode == "verify_only":
        contact_ids = dict(zip(
            (item["backup_ref"] for item in sections["contacts"]), replay_ids["contacts"],
        ))
        existing_links = 0
        for item in sections["application_contacts"]:
            track = destination_tracks.get(item["track_ref"])
            contact_id = contact_ids.get(item["contact_ref"])
            if track is not None and contact_id is not None:
                existing_links += int(db.query(ApplicationContact).filter_by(
                    user_id=user_id, track_id=track.id, contact_id=contact_id, role=item["role"],
                ).first() is not None)
        result["counts"].update({
            "contacts": {"created": sum(value is None for value in replay_ids["contacts"]),
                         "existing": sum(value is not None for value in replay_ids["contacts"])},
            "application_contacts": {"created": len(sections["application_contacts"]) - existing_links,
                                     "existing": existing_links},
            "interviews": {"created": sum(value is None for value in replay_ids["interviews"]),
                           "existing": sum(value is not None for value in replay_ids["interviews"])},
        })
        return result

    created = {"contacts": 0, "application_contacts": 0, "interviews": 0}
    existing_counts = {"contacts": 0, "application_contacts": 0, "interviews": 0}
    contact_map: dict[str, Contact] = {}

    try:
        for item in sections["contacts"]:
            entity_id = _receipt_entity(db, user_id, "backup:contact", item["backup_ref"], item)
            contact = db.query(Contact).filter(Contact.id == entity_id, Contact.user_id == user_id).first() if entity_id else None
            if contact is None:
                contact = Contact(
                    user_id=user_id,
                    name=item["name"],
                    email=item.get("email"),
                    profile_url=item.get("profile_url"),
                    company_display=item.get("company_display"),
                    notes=item.get("notes"),
                    version=max(int(item.get("version", 1)), 1),
                    created_at=_parse_utc(item["created_at"]),
                    updated_at=_parse_utc(item["updated_at"]),
                    is_deleted=bool(item.get("is_deleted", False)),
                )
                db.add(contact)
                db.flush()
                _write_receipt(db, user_id, "backup:contact", item, "contact", contact.id)
                created["contacts"] += 1
            else:
                existing_counts["contacts"] += 1
            contact_map[item["backup_ref"]] = contact

        for item in sections["application_contacts"]:
            track = destination_tracks.get(item["track_ref"])
            contact = contact_map.get(item["contact_ref"])
            if track is None or contact is None:
                raise BackupContractError("conflicting_reference_graph", 409, "F8 contact link could not resolve its destination references.")
            link = db.query(ApplicationContact).filter(
                ApplicationContact.user_id == user_id,
                ApplicationContact.track_id == track.id,
                ApplicationContact.contact_id == contact.id,
                ApplicationContact.role == item["role"],
            ).first()
            if link is None:
                link = ApplicationContact(
                    user_id=user_id,
                    track_id=track.id,
                    contact_id=contact.id,
                    role=item["role"],
                    referral_source=item.get("referral_source"),
                    created_at=_parse_utc(item["created_at"]),
                )
                db.add(link)
                created["application_contacts"] += 1
            else:
                existing_counts["application_contacts"] += 1

        for item in sections["interviews"]:
            entity_id = _receipt_entity(db, user_id, "backup:interview", item["backup_ref"], item)
            interview = db.query(Interview).filter(Interview.id == entity_id, Interview.user_id == user_id).first() if entity_id else None
            if interview is None:
                track = destination_tracks.get(item["track_ref"])
                contact = contact_map.get(item.get("contact_ref")) if item.get("contact_ref") else None
                if track is None:
                    raise BackupContractError("conflicting_reference_graph", 409, "F8 interview could not resolve its application.")
                interview = Interview(
                    user_id=user_id,
                    track_id=track.id,
                    contact_id=contact.id if contact else None,
                    starts_at=_parse_utc(item["starts_at"]),
                    ends_at=_parse_utc(item["ends_at"]),
                    timezone=item["timezone"],
                    kind=item["kind"],
                    meeting_url=item.get("meeting_url"),
                    location=item.get("location"),
                    status=item.get("status", "scheduled"),
                    notes=item.get("notes"),
                    round_label=item.get("round_label"),
                    preparation_notes=item.get("preparation_notes"),
                    version=max(int(item.get("version", 1)), 1),
                    created_at=_parse_utc(item["created_at"]),
                    updated_at=_parse_utc(item["updated_at"]),
                )
                db.add(interview)
                db.flush()
                _write_receipt(db, user_id, "backup:interview", item, "interview", interview.id)
                created["interviews"] += 1
            else:
                existing_counts["interviews"] += 1

        db.flush()
    except Exception:
        db.rollback()
        raise

    for name in created:
        result["counts"][name] = {"created": created[name], "existing": existing_counts[name]}
    return result
