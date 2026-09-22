from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import BinaryIO, Any
from uuid import UUID, uuid4

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import (
    DocumentStorageConfigurationError,
    settings,
    validate_document_storage_path,
)
from ..document_schemas import (
    DOCUMENT_RECEIPT_RETENTION_DAYS,
    DOCUMENT_RECONCILIATION_GRACE_SECONDS,
    MAX_ACCOUNT_DOCUMENT_BYTES,
    MAX_DOCUMENT_BYTES,
    DocumentLinkIn,
    DocumentUploadMetadata,
)
from ..models import (
    ApplicationDocument,
    AuditEvent,
    DocumentCreateReceipt,
    DocumentVersion,
    JobTrack,
    User,
)


CHUNK_BYTES = 64 * 1024
TRASH_RETENTION_HOURS = 24
_SAFE_FILENAME_RE = re.compile(r"[\x00-\x1f\x7f]")


class DocumentServiceError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 422,
        field: str = "__root__",
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.field = field
        self.context = context or {}


@dataclass(frozen=True)
class StagedDocument:
    path: Path
    original_filename: str
    media_type: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class DocumentCreateResult:
    document: DocumentVersion
    replayed: bool


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat() + ("" if value.tzinfo is not None else "Z")


def _storage_root(*, create: bool = False) -> Path:
    try:
        root = validate_document_storage_path(
            settings.DOCUMENT_STORAGE_DIR,
            environment=settings.ENVIRONMENT,
        )
    except DocumentStorageConfigurationError as exc:
        raise DocumentServiceError(
            "document_storage_unavailable",
            "Private document storage is not configured for this environment.",
            status_code=503,
        ) from exc

    if create:
        try:
            root.mkdir(parents=True, exist_ok=True)
            for child in ("staging", "documents", "trash"):
                (root / child).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise DocumentServiceError(
                "document_storage_unavailable",
                "Private document storage is not writable.",
                status_code=503,
            ) from exc
    if not root.exists() or not root.is_dir():
        raise DocumentServiceError(
            "document_storage_unavailable",
            "Private document storage is not available.",
            status_code=503,
        )
    return root


def _resolve_storage_key(root: Path, storage_key: str) -> Path:
    candidate = (root / storage_key).resolve(strict=False)
    if root != candidate and root not in candidate.parents:
        raise DocumentServiceError(
            "invalid_storage_key",
            "Stored document location is invalid.",
            status_code=500,
        )
    return candidate


def safe_display_filename(value: str | None) -> str:
    raw = str(value or "document").replace("\\", "/")
    basename = raw.rsplit("/", 1)[-1]
    basename = _SAFE_FILENAME_RE.sub("", basename).strip().strip(".")
    if not basename:
        basename = "document"
    return basename[:255]


def _detect_media_type(path: Path) -> str:
    with path.open("rb") as handle:
        prefix = handle.read(5)
    if prefix == b"%PDF-":
        return "application/pdf"
    try:
        path.read_bytes().decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise DocumentServiceError(
            "unsupported_document_format",
            "Only genuine PDF files and valid UTF-8 plain text are supported.",
            status_code=415,
            field="file",
        ) from exc
    return "text/plain"


def stage_upload(
    stream: BinaryIO,
    *,
    original_filename: str | None,
    claimed_media_type: str | None,
) -> StagedDocument:
    root = _storage_root(create=True)
    owner_staging = root / "staging"
    owner_staging.mkdir(parents=True, exist_ok=True)
    path = owner_staging / f"{uuid4().hex}.part"
    digest = hashlib.sha256()
    size_bytes = 0

    try:
        with path.open("xb") as output:
            while True:
                chunk = stream.read(CHUNK_BYTES)
                if not chunk:
                    break
                size_bytes += len(chunk)
                if size_bytes > MAX_DOCUMENT_BYTES:
                    raise DocumentServiceError(
                        "document_too_large",
                        "Document exceeds the 10 MiB file limit.",
                        status_code=413,
                        field="file",
                    )
                digest.update(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())

        if size_bytes == 0:
            raise DocumentServiceError(
                "empty_document",
                "Document file cannot be empty.",
                field="file",
            )

        detected = _detect_media_type(path)
        claimed = str(claimed_media_type or "").split(";", 1)[0].strip().lower()
        if claimed in {"application/pdf", "text/plain"} and claimed != detected:
            raise DocumentServiceError(
                "media_type_mismatch",
                "Uploaded bytes do not match the declared media type.",
                status_code=415,
                field="file",
            )

        return StagedDocument(
            path=path,
            original_filename=safe_display_filename(original_filename),
            media_type=detected,
            size_bytes=size_bytes,
            sha256=digest.hexdigest(),
        )
    except Exception:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _payload_hash(metadata: DocumentUploadMetadata, staged: StagedDocument) -> str:
    payload = {
        "kind": metadata.kind,
        "label": metadata.label,
        "document_family_id": (
            str(metadata.document_family_id) if metadata.document_family_id else None
        ),
        "original_filename": staged.original_filename,
        "media_type": staged.media_type,
        "size_bytes": staged.size_bytes,
        "sha256": staged.sha256,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _owned_user_for_update(session: Session, user_id: int) -> User:
    user = (
        session.query(User)
        .filter(User.id == user_id)
        .with_for_update()
        .first()
    )
    if user is None:
        raise DocumentServiceError(
            "inaccessible_account",
            "Authenticated account is not available.",
            status_code=404,
        )
    return user


def _used_bytes(session: Session, user_id: int) -> int:
    value = (
        session.query(func.coalesce(func.sum(DocumentVersion.size_bytes), 0))
        .filter(
            DocumentVersion.user_id == user_id,
            DocumentVersion.state.in_(("pending", "ready")),
        )
        .scalar()
    )
    return int(value or 0)


def _owned_track(
    session: Session, *, user_id: int, track_id: int, for_update: bool = False
) -> JobTrack:
    query = session.query(JobTrack).filter(
        JobTrack.id == track_id,
        JobTrack.user_id == user_id,
    )
    if for_update:
        query = query.with_for_update()
    track = query.first()
    if track is None:
        raise DocumentServiceError(
            "inaccessible_job_track",
            "Application is not available to this account.",
            status_code=404,
        )
    return track


def _owned_document(
    session: Session,
    *,
    user_id: int,
    document_id: str,
    for_update: bool = False,
    include_deleted: bool = False,
) -> DocumentVersion:
    query = session.query(DocumentVersion).filter(
        DocumentVersion.id == str(document_id),
        DocumentVersion.user_id == user_id,
    )
    if not include_deleted:
        query = query.filter(DocumentVersion.state != "deleted")
    if for_update:
        query = query.with_for_update()
    document = query.first()
    if document is None:
        raise DocumentServiceError(
            "document_not_found",
            "Document is not available to this account.",
            status_code=404,
        )
    return document


def create_document(
    session: Session,
    *,
    user_id: int,
    metadata: DocumentUploadMetadata,
    staged: StagedDocument,
    request_key: UUID | str,
    now: datetime | None = None,
) -> DocumentCreateResult:
    now = now or datetime.utcnow()
    try:
        request_key_value = str(UUID(str(request_key)))
    except (TypeError, ValueError, AttributeError) as exc:
        staged.path.unlink(missing_ok=True)
        raise DocumentServiceError(
            "invalid_idempotency_key",
            "Idempotency-Key must be a valid UUID.",
            field="Idempotency-Key",
        ) from exc

    digest = _payload_hash(metadata, staged)
    _owned_user_for_update(session, user_id)

    cutoff = now - timedelta(days=DOCUMENT_RECEIPT_RETENTION_DAYS)
    expired = (
        session.query(DocumentCreateReceipt)
        .filter(
            DocumentCreateReceipt.user_id == user_id,
            DocumentCreateReceipt.request_key == request_key_value,
            DocumentCreateReceipt.created_at < cutoff,
        )
        .first()
    )
    if expired is not None:
        session.delete(expired)
        session.flush()

    existing = (
        session.query(DocumentCreateReceipt)
        .filter(
            DocumentCreateReceipt.user_id == user_id,
            DocumentCreateReceipt.request_key == request_key_value,
        )
        .first()
    )
    if existing is not None:
        if existing.payload_hash != digest:
            staged.path.unlink(missing_ok=True)
            raise DocumentServiceError(
                "idempotency_conflict",
                "Idempotency-Key was already used for different document content.",
                status_code=409,
                field="Idempotency-Key",
            )
        document = _owned_document(
            session,
            user_id=user_id,
            document_id=existing.document_id,
            include_deleted=True,
        )
        staged.path.unlink(missing_ok=True)
        if existing.status != "ready" or document.state != "ready":
            raise DocumentServiceError(
                "upload_not_ready",
                "The original upload has not reached a ready state.",
                status_code=409,
            )
        return DocumentCreateResult(document=document, replayed=True)

    current_bytes = _used_bytes(session, user_id)
    if current_bytes + staged.size_bytes > MAX_ACCOUNT_DOCUMENT_BYTES:
        staged.path.unlink(missing_ok=True)
        raise DocumentServiceError(
            "document_quota_exceeded",
            "Uploading this document would exceed the 100 MiB account quota.",
            status_code=413,
            field="file",
            context={
                "used_bytes": current_bytes,
                "limit_bytes": MAX_ACCOUNT_DOCUMENT_BYTES,
            },
        )

    family_id = (
        str(metadata.document_family_id)
        if metadata.document_family_id is not None
        else str(uuid4())
    )
    family_query = session.query(DocumentVersion).filter(
        DocumentVersion.user_id == user_id,
        DocumentVersion.document_family_id == family_id,
    )
    existing_family = family_query.order_by(DocumentVersion.version_number.desc()).first()
    if existing_family is not None and existing_family.kind != metadata.kind:
        staged.path.unlink(missing_ok=True)
        raise DocumentServiceError(
            "document_family_kind_conflict",
            "A document family cannot mix resume and cover-letter versions.",
            status_code=409,
            field="document_family_id",
        )
    next_version = (
        (existing_family.version_number + 1) if existing_family is not None else 1
    )

    document_id = str(uuid4())
    storage_key = f"documents/{user_id}/{uuid4().hex}.bin"
    document = DocumentVersion(
        id=document_id,
        user_id=user_id,
        document_family_id=family_id,
        kind=metadata.kind,
        label=metadata.label,
        original_filename=staged.original_filename,
        media_type=staged.media_type,
        size_bytes=staged.size_bytes,
        sha256=staged.sha256,
        storage_key=storage_key,
        version_number=next_version,
        created_at=now,
        state="pending",
    )
    receipt = DocumentCreateReceipt(
        user_id=user_id,
        request_key=request_key_value,
        payload_hash=digest,
        document_id=document_id,
        status="pending",
        created_at=now,
    )
    session.add(document)
    session.add(receipt)
    session.flush()

    root = _storage_root(create=True)
    final_path = _resolve_storage_key(root, storage_key)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.replace(staged.path, final_path)
        with final_path.open("rb") as persisted:
            os.fsync(persisted.fileno())
        dir_fd = os.open(str(final_path.parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError as exc:
        document.state = "failed"
        receipt.status = "failed"
        try:
            staged.path.unlink(missing_ok=True)
        except OSError:
            pass
        raise DocumentServiceError(
            "document_publish_failed",
            "Document bytes could not be published to private storage.",
            status_code=500,
        ) from exc

    document.state = "ready"
    receipt.status = "ready"
    session.flush()
    return DocumentCreateResult(document=document, replayed=False)


def document_availability(document: DocumentVersion) -> str:
    if document.state != "ready":
        return "not_ready"
    try:
        root = _storage_root(create=False)
        path = _resolve_storage_key(root, document.storage_key)
    except DocumentServiceError:
        return "missing"
    return "ready" if path.is_file() else "missing"


def serialize_document(document: DocumentVersion) -> dict[str, Any]:
    return {
        "id": document.id,
        "document_family_id": document.document_family_id,
        "kind": document.kind,
        "label": document.label,
        "original_filename": document.original_filename,
        "media_type": document.media_type,
        "size_bytes": document.size_bytes,
        "sha256": document.sha256,
        "version_number": document.version_number,
        "created_at": _utc_iso(document.created_at),
        "state": document.state,
        "availability": document_availability(document),
    }


def list_documents(session: Session, *, user_id: int) -> dict[str, Any]:
    documents = (
        session.query(DocumentVersion)
        .filter(
            DocumentVersion.user_id == user_id,
            DocumentVersion.state != "deleted",
        )
        .order_by(DocumentVersion.created_at.desc(), DocumentVersion.id.desc())
        .all()
    )
    return {
        "items": [serialize_document(item) for item in documents],
        "quota": {
            "used_bytes": _used_bytes(session, user_id),
            "limit_bytes": MAX_ACCOUNT_DOCUMENT_BYTES,
        },
        "document_bytes_backup": "excluded",
    }


def download_target(
    session: Session, *, user_id: int, document_id: str
) -> tuple[DocumentVersion, Path]:
    document = _owned_document(
        session, user_id=user_id, document_id=document_id
    )
    if document.state != "ready":
        raise DocumentServiceError(
            "document_not_ready",
            "Document is not ready for download.",
            status_code=409,
        )
    root = _storage_root(create=False)
    path = _resolve_storage_key(root, document.storage_key)
    if not path.is_file():
        raise DocumentServiceError(
            "document_bytes_missing",
            "Document metadata exists, but its private file bytes require recovery.",
            status_code=409,
            context={"document_id": document.id},
        )
    return document, path


def list_track_documents(
    session: Session, *, user_id: int, track_id: int
) -> list[dict[str, Any]]:
    _owned_track(session, user_id=user_id, track_id=track_id)
    links = (
        session.query(ApplicationDocument)
        .filter(
            ApplicationDocument.user_id == user_id,
            ApplicationDocument.track_id == track_id,
        )
        .order_by(ApplicationDocument.attached_at.asc(), ApplicationDocument.id.asc())
        .all()
    )
    return [
        {
            "id": link.id,
            "track_id": link.track_id,
            "kind": link.kind,
            "usage": link.usage,
            "attached_at": _utc_iso(link.attached_at),
            "document": serialize_document(link.document_version),
        }
        for link in links
    ]


def link_document(
    session: Session,
    *,
    user_id: int,
    track_id: int,
    payload: DocumentLinkIn,
    now: datetime | None = None,
) -> ApplicationDocument:
    now = now or datetime.utcnow()
    track = _owned_track(
        session, user_id=user_id, track_id=track_id, for_update=True
    )
    document = _owned_document(
        session,
        user_id=user_id,
        document_id=str(payload.document_version_id),
        for_update=True,
    )
    if document.state != "ready" or document_availability(document) != "ready":
        raise DocumentServiceError(
            "document_not_ready",
            "Only a ready document with available private bytes can be attached.",
            status_code=409,
            field="document_version_id",
        )

    same = (
        session.query(ApplicationDocument)
        .filter(
            ApplicationDocument.user_id == user_id,
            ApplicationDocument.track_id == track_id,
            ApplicationDocument.document_version_id == document.id,
        )
        .first()
    )
    if same is not None:
        if same.usage == payload.usage:
            return same
        raise DocumentServiceError(
            "document_already_attached",
            "This document version is already attached with a different usage.",
            status_code=409,
        )

    if payload.usage == "used":
        current = (
            session.query(ApplicationDocument)
            .filter(
                ApplicationDocument.user_id == user_id,
                ApplicationDocument.track_id == track_id,
                ApplicationDocument.kind == document.kind,
                ApplicationDocument.usage == "used",
            )
            .with_for_update()
            .first()
        )
        if current is not None:
            if payload.replace_document_version_id is None:
                raise DocumentServiceError(
                    "used_document_conflict",
                    "A Used document is already recorded. Confirm the exact version being corrected.",
                    status_code=409,
                    context={
                        "current_document_version_id": current.document_version_id,
                    },
                )
            if str(payload.replace_document_version_id) != current.document_version_id:
                raise DocumentServiceError(
                    "stale_used_document_correction",
                    "The recorded Used document changed. Reload before correcting it.",
                    status_code=409,
                    context={
                        "current_document_version_id": current.document_version_id,
                    },
                )
            previous_id = current.document_version_id
            session.delete(current)
            session.flush()
            session.add(
                AuditEvent(
                    user_id=user_id,
                    event_type="document_used_corrected",
                    entity_type="job_track",
                    entity_id=track.id,
                    metadata_json={
                        "kind": document.kind,
                        "from_document_version_id": previous_id,
                        "to_document_version_id": document.id,
                    },
                    created_at=now,
                )
            )
        elif payload.replace_document_version_id is not None:
            raise DocumentServiceError(
                "stale_used_document_correction",
                "There is no current Used document to replace.",
                status_code=409,
            )

    link = ApplicationDocument(
        user_id=user_id,
        track_id=track.id,
        document_version_id=document.id,
        kind=document.kind,
        usage=payload.usage,
        attached_at=now,
    )
    session.add(link)
    session.flush()
    return link


def detach_document(
    session: Session,
    *,
    user_id: int,
    track_id: int,
    document_id: str,
) -> bool:
    _owned_track(session, user_id=user_id, track_id=track_id)
    link = (
        session.query(ApplicationDocument)
        .filter(
            ApplicationDocument.user_id == user_id,
            ApplicationDocument.track_id == track_id,
            ApplicationDocument.document_version_id == str(document_id),
        )
        .first()
    )
    if link is None:
        return False
    session.delete(link)
    session.flush()
    return True


def list_document_applications(
    session: Session,
    *,
    user_id: int,
    document_id: str,
    page: int = 1,
    limit: int = 50,
) -> dict[str, Any]:
    _owned_document(
        session,
        user_id=user_id,
        document_id=document_id,
        include_deleted=True,
    )
    safe_limit = max(1, min(int(limit), 50))
    safe_page = max(1, int(page))
    query = (
        session.query(ApplicationDocument, JobTrack)
        .join(JobTrack, JobTrack.id == ApplicationDocument.track_id)
        .filter(
            ApplicationDocument.user_id == user_id,
            ApplicationDocument.document_version_id == str(document_id),
            JobTrack.user_id == user_id,
        )
    )
    total = query.count()
    rows = (
        query.order_by(ApplicationDocument.attached_at.desc())
        .offset((safe_page - 1) * safe_limit)
        .limit(safe_limit)
        .all()
    )
    return {
        "items": [
            {
                "track_id": track.id,
                "company": track.company,
                "title": track.title,
                "status": track.status,
                "kind": link.kind,
                "usage": link.usage,
                "attached_at": _utc_iso(link.attached_at),
            }
            for link, track in rows
        ],
        "page": safe_page,
        "page_size": safe_limit,
        "total_count": total,
        "has_next": safe_page * safe_limit < total,
    }


def delete_document(
    session: Session,
    *,
    user_id: int,
    document_id: str,
) -> DocumentVersion:
    document = _owned_document(
        session,
        user_id=user_id,
        document_id=document_id,
        for_update=True,
    )
    references = list_document_applications(
        session,
        user_id=user_id,
        document_id=document.id,
        page=1,
        limit=50,
    )
    if references["total_count"]:
        raise DocumentServiceError(
            "document_is_referenced",
            "Detach this document from its applications before deleting it.",
            status_code=409,
            context={"applications": references["items"]},
        )

    root = _storage_root(create=True)
    source = _resolve_storage_key(root, document.storage_key)
    if source.exists():
        trash_dir = root / "trash" / str(user_id)
        trash_dir.mkdir(parents=True, exist_ok=True)
        target = trash_dir / f"{document.id}-{uuid4().hex}.bin"
        try:
            os.replace(source, target)
        except OSError as exc:
            raise DocumentServiceError(
                "document_delete_failed",
                "Document bytes could not be moved into private retention storage.",
                status_code=500,
            ) from exc
    document.state = "deleted"
    session.flush()
    return document


def reconcile_document_storage(
    session: Session,
    *,
    now: datetime | None = None,
    limit: int = 100,
) -> dict[str, int]:
    now = now or datetime.utcnow()
    safe_limit = max(1, min(int(limit), 500))
    root = _storage_root(create=True)
    grace = now - timedelta(seconds=DOCUMENT_RECONCILIATION_GRACE_SECONDS)
    counters = {
        "staging_removed": 0,
        "pending_ready": 0,
        "pending_failed": 0,
        "missing_ready": 0,
        "orphan_removed": 0,
        "trash_removed": 0,
    }

    staging_files = sorted((root / "staging").glob("*.part"))[:safe_limit]
    for path in staging_files:
        try:
            modified = datetime.utcfromtimestamp(path.stat().st_mtime)
            if modified < grace:
                path.unlink(missing_ok=True)
                counters["staging_removed"] += 1
        except OSError:
            continue

    pending = (
        session.query(DocumentVersion)
        .filter(
            DocumentVersion.state == "pending",
            DocumentVersion.created_at < grace,
        )
        .order_by(DocumentVersion.created_at.asc())
        .limit(safe_limit)
        .all()
    )
    for document in pending:
        path = _resolve_storage_key(root, document.storage_key)
        if path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest == document.sha256 and path.stat().st_size == document.size_bytes:
                document.state = "ready"
                counters["pending_ready"] += 1
            else:
                document.state = "failed"
                counters["pending_failed"] += 1
        else:
            document.state = "failed"
            counters["pending_failed"] += 1

    ready = (
        session.query(DocumentVersion)
        .filter(DocumentVersion.state == "ready")
        .order_by(DocumentVersion.created_at.asc())
        .limit(safe_limit)
        .all()
    )
    for document in ready:
        path = _resolve_storage_key(root, document.storage_key)
        if not path.is_file():
            counters["missing_ready"] += 1

    known_keys = {
        value
        for (value,) in session.query(DocumentVersion.storage_key).all()
    }
    document_root = root / "documents"
    scanned = 0
    if document_root.exists():
        for path in document_root.rglob("*.bin"):
            if scanned >= safe_limit:
                break
            scanned += 1
            try:
                rel = path.resolve().relative_to(root).as_posix()
                modified = datetime.utcfromtimestamp(path.stat().st_mtime)
                if rel not in known_keys and modified < grace:
                    path.unlink(missing_ok=True)
                    counters["orphan_removed"] += 1
            except (OSError, ValueError):
                continue

    trash_cutoff = now - timedelta(hours=TRASH_RETENTION_HOURS)
    scanned = 0
    for path in (root / "trash").rglob("*.bin"):
        if scanned >= safe_limit:
            break
        scanned += 1
        try:
            modified = datetime.utcfromtimestamp(path.stat().st_mtime)
            if modified < trash_cutoff:
                path.unlink(missing_ok=True)
                counters["trash_removed"] += 1
        except OSError:
            continue

    session.flush()
    return counters
