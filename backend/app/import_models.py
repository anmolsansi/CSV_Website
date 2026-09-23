from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)

from .database import Base


IMPORT_PREVIEW_STATUS_VALUES = ("ready", "committing", "committed", "failed")


class ImportPreview(Base):
    """Owner-scoped private import plan and durable commit replay record."""

    __tablename__ = "import_previews"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_filename = Column(String(255), nullable=False)
    source_sha256 = Column(String(64), nullable=False)
    headers_json = Column(JSON, nullable=False)
    header_fingerprint = Column(String(64), nullable=False)
    mapping_json = Column(JSON, nullable=False)
    normalized_rows_json = Column(JSON, nullable=True)
    rejected_rows_json = Column(JSON, nullable=True)
    summary_json = Column(JSON, nullable=False)
    destination_fingerprint = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False, index=True)
    status = Column(String(20), nullable=False, default="ready", index=True)
    version = Column(Integer, nullable=False, default=1)
    commit_key = Column(String(36), nullable=True)
    commit_payload_hash = Column(String(64), nullable=True)
    result_json = Column(JSON, nullable=True)
    committed_at = Column(DateTime, nullable=True, index=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('ready', 'committing', 'committed', 'failed')",
            name="ck_import_previews_status",
        ),
        CheckConstraint("version > 0", name="ck_import_previews_version"),
        CheckConstraint(
            "length(source_sha256) = 64",
            name="ck_import_previews_source_sha256_length",
        ),
        CheckConstraint(
            "length(header_fingerprint) = 64",
            name="ck_import_previews_header_fingerprint_length",
        ),
        CheckConstraint(
            "length(destination_fingerprint) = 64",
            name="ck_import_previews_destination_fingerprint_length",
        ),
        CheckConstraint(
            "commit_key IS NULL OR length(commit_key) = 36",
            name="ck_import_previews_commit_key_length",
        ),
        CheckConstraint(
            "commit_payload_hash IS NULL OR length(commit_payload_hash) = 64",
            name="ck_import_previews_commit_hash_length",
        ),
        UniqueConstraint(
            "user_id",
            "commit_key",
            name="uq_import_previews_user_commit_key",
        ),
        Index("ix_import_previews_user_expires", "user_id", "expires_at"),
        Index("ix_import_previews_user_status", "user_id", "status"),
        Index("ix_import_previews_user_committed", "user_id", "committed_at"),
    )


class ImportMapping(Base):
    """Reusable owner-scoped source-column-index to JobGrid-field mapping."""

    __tablename__ = "import_mappings"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(100), nullable=False)
    header_fingerprint = Column(String(64), nullable=False, index=True)
    mapping_json = Column(JSON, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_import_mapping_user_name"),
        CheckConstraint(
            "length(name) BETWEEN 1 AND 100",
            name="ck_import_mappings_name_length",
        ),
        CheckConstraint(
            "length(header_fingerprint) = 64",
            name="ck_import_mappings_header_fingerprint_length",
        ),
        CheckConstraint("version > 0", name="ck_import_mappings_version"),
        Index(
            "ix_import_mappings_user_fingerprint",
            "user_id",
            "header_fingerprint",
        ),
    )
