from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


DocumentKind = Literal["resume", "cover_letter"]
DocumentUsage = Literal["used", "reference"]
DocumentState = Literal["pending", "ready", "failed", "deleted"]
DocumentMediaType = Literal["application/pdf", "text/plain"]

MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
MAX_ACCOUNT_DOCUMENT_BYTES = 100 * 1024 * 1024
MAX_DOCUMENT_LABEL_CHARS = 150
MAX_DOCUMENT_FILENAME_CHARS = 255
DOCUMENT_RECEIPT_RETENTION_DAYS = 30
DOCUMENT_RECONCILIATION_GRACE_SECONDS = 60 * 60


class StrictDocumentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DocumentUploadMetadata(StrictDocumentModel):
    kind: DocumentKind
    label: str = Field(min_length=1, max_length=MAX_DOCUMENT_LABEL_CHARS)
    document_family_id: UUID | None = None

    @model_validator(mode="after")
    def normalize_label(self):
        normalized = self.label.strip()
        if not normalized:
            raise ValueError("Document label cannot be blank.")
        object.__setattr__(self, "label", normalized)
        return self


class DocumentLinkIn(StrictDocumentModel):
    document_version_id: UUID
    usage: DocumentUsage
    replace_document_version_id: UUID | None = None

    @model_validator(mode="after")
    def validate_replacement(self):
        if self.usage != "used" and self.replace_document_version_id is not None:
            raise ValueError("Only a Used attachment can replace another Used attachment.")
        if self.document_version_id == self.replace_document_version_id:
            raise ValueError("Replacement must select a different document version.")
        return self


class DocumentRecord(StrictDocumentModel):
    id: UUID
    document_family_id: UUID
    kind: DocumentKind
    label: str
    original_filename: str
    media_type: DocumentMediaType
    size_bytes: int = Field(ge=0, le=MAX_DOCUMENT_BYTES)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    version_number: int = Field(gt=0)
    created_at: str
    state: DocumentState
    availability: Literal["ready", "missing", "not_ready"]


class ApplicationDocumentRecord(StrictDocumentModel):
    id: int
    track_id: int
    kind: DocumentKind
    usage: DocumentUsage
    attached_at: str
    document: DocumentRecord


class DocumentApplicationRecord(StrictDocumentModel):
    track_id: int
    company: str | None
    title: str | None
    status: str
    kind: DocumentKind
    usage: DocumentUsage
    attached_at: str
