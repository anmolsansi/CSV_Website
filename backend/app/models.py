from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    JSON,
    event,
    inspect,
    text,
)
from sqlalchemy.orm import relationship

from .database import Base

# All CSV columns are stored as nullable text.
CSV_COLUMNS = [
    # Core job fields
    "ats_group", "location_group", "search_bucket", "title",
    "title_match_status", "title_reject_reason", "url", "display_domain",
    "company_guess", "job_id_guess", "canonical_company_job_key",
    "application_url", "application_dedupe_key",
    "page_number", "decision", "rejection_reasons",
    # Posting metadata
    "posted_status", "posted_value", "posted_source", "posted_age_days",
    # Location
    "location_status", "location_evidence",
    "is_usa_role", "location_country", "location_city", "location_state",
    "location_raw_extracted", "location_confidence", "location_source",
    # Sponsorship
    "sponsorship_status", "positive_sponsorship_matches",
    "negative_sponsorship_matches", "sponsorship_evidence_snippet",
    "positive_sponsorship_evidence_snippet",
    # Clearance
    "clearance_matches", "clearance_evidence_snippet",
    # Job description
    "jd_quality_status", "jd_quality_reasons",
    "jd_text_length", "jd_text",
    "extraction_method", "retry_attempted", "error", "source_file",
    # Work model & salary
    "work_model_extracted",
    "salary_min_extracted", "salary_max_extracted", "salary_currency_extracted",
    # Extracted posting metadata
    "posted_status_extracted", "posted_value_extracted",
    "posted_source_extracted", "posted_age_days_extracted",
    # Extracted sponsorship
    "sponsorship_status_extracted",
    "positive_sponsorship_matches_extracted",
    "negative_sponsorship_matches_extracted",
    "positive_sponsorship_evidence_extracted",
    "negative_sponsorship_evidence_extracted",
    # Extracted clearance
    "clearance_or_citizenship_extracted",
    "clearance_or_citizenship_evidence_extracted",
    # Education & employment
    "education_requirement_extracted", "employment_type_extracted",
    # Scoring & fit
    "resume_match_score", "resume_score", "fit_category",
    "score_confidence", "role_family", "seniority_level", "required_years_min",
    # Skills extraction
    "core_languages_extracted", "core_frameworks_extracted",
    "core_cloud_devops_extracted", "database_requirements_extracted",
    "ai_ml_requirements_extracted",
    "matched_resume_skills", "missing_or_weaker_skills", "score_reason",
    # JD usability
    "closed_or_unusable_jd", "closed_or_unusable_reason",
]

JOB_TRACK_STATUS_VALUES = [
    "opened", "applied", "follow_up", "interview",
    "rejected", "offer", "not_applying",
]
JOB_AVAILABILITY_STATE_VALUES = ["unknown", "available", "unavailable", "closed"]
JOB_DEADLINE_SOURCE_VALUES = ["user", "import"]
JOB_CHECK_REQUEST_STATUS_VALUES = ["pending", "running", "done", "failed"]
REMINDER_CHANNEL_VALUES = ["in_app", "email"]
REMINDER_DELIVERY_STATUS_VALUES = [
    "pending", "sending", "sent", "failed", "unknown", "cancelled",
]
DOCUMENT_KIND_VALUES = ["resume", "cover_letter"]
DOCUMENT_MEDIA_TYPE_VALUES = ["application/pdf", "text/plain"]
DOCUMENT_STATE_VALUES = ["pending", "ready", "failed", "deleted"]
DOCUMENT_USAGE_VALUES = ["used", "reference"]


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(320), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    timezone = Column(String(64), nullable=False, default="UTC")
    # JG-012: null/0 disables automatic archive; configured values are
    # validated at the authenticated API boundary.
    retention_days = Column(Integer, nullable=True)

    identities = relationship(
        "OAuthIdentity", back_populates="user", cascade="all, delete-orphan"
    )
    rows = relationship("CsvRow", back_populates="user", cascade="all, delete-orphan")
    job_tracks = relationship(
        "JobTrack", back_populates="user", cascade="all, delete-orphan"
    )
    company_aliases = relationship(
        "CompanyAlias", back_populates="user", cascade="all, delete-orphan"
    )
    url_history = relationship(
        "UrlHistory", back_populates="user", cascade="all, delete-orphan"
    )
    preference = relationship(
        "ColumnPreference", back_populates="user", uselist=False,
        cascade="all, delete-orphan",
    )
    audit_events = relationship(
        "AuditEvent", backref="user", cascade="all, delete-orphan"
    )
    applypilot_batches = relationship(
        "ApplyPilotBatch", backref="user", cascade="all, delete-orphan"
    )
    goal = relationship(
        "UserGoal", backref="user", uselist=False, cascade="all, delete-orphan"
    )
    lifecycle_events = relationship(
        "JobLifecycleEvent", back_populates="user", cascade="all, delete-orphan"
    )
    application_evidence = relationship(
        "ApplicationEvidence", back_populates="user", cascade="all, delete-orphan"
    )
    evidence_create_receipts = relationship(
        "EvidenceCreateReceipt", back_populates="user", cascade="all, delete-orphan"
    )
    work_items = relationship(
        "WorkItem", back_populates="user", cascade="all, delete-orphan"
    )
    work_item_overrides = relationship(
        "WorkItemOverride", back_populates="user", cascade="all, delete-orphan"
    )
    reminder_preference = relationship(
        "ReminderPreference", back_populates="user", uselist=False,
        cascade="all, delete-orphan",
    )
    reminder_deliveries = relationship(
        "ReminderDelivery", back_populates="user", cascade="all, delete-orphan"
    )
    document_versions = relationship(
        "DocumentVersion", back_populates="user", cascade="all, delete-orphan"
    )
    application_documents = relationship(
        "ApplicationDocument", back_populates="user", cascade="all, delete-orphan"
    )
    document_create_receipts = relationship(
        "DocumentCreateReceipt", back_populates="user", cascade="all, delete-orphan"
    )
    capture_requests = relationship(
        "CaptureRequest", back_populates="user", cascade="all, delete-orphan"
    )
    request_window_counters = relationship(
        "RequestWindowCounter", back_populates="user", cascade="all, delete-orphan"
    )
    job_availability = relationship(
        "JobAvailability", back_populates="user", cascade="all, delete-orphan"
    )
    job_check_requests = relationship(
        "JobCheckRequest", back_populates="user", cascade="all, delete-orphan"
    )


class OAuthIdentity(Base):
    __tablename__ = "oauth_identities"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    provider = Column(String(50), nullable=False)
    provider_id = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="identities")

    __table_args__ = (
        UniqueConstraint("provider", "provider_id", name="uq_provider_identity"),
    )


class UrlHistory(Base):
    __tablename__ = "url_history"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    url = Column(Text, nullable=False)
    first_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="url_history")

    __table_args__ = (
        UniqueConstraint("user_id", "url", name="uq_user_url_history"),
    )


class CsvRow(Base):
    __tablename__ = "csv_rows"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    upload_batch_id = Column(String(36), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    clicked = Column(Boolean, default=False, nullable=False)
    clicked_at = Column(DateTime, nullable=True, index=True)
    archived = Column(Boolean, default=False, nullable=False, index=True)
    # Legacy archived rows intentionally keep this NULL. A timestamp is written
    # only when an unarchived row transitions into the archive.
    archived_at = Column(DateTime, nullable=True, index=True)
    capture_source = Column(String(16), nullable=True)
    captured_at = Column(DateTime, nullable=True, index=True)
    capture_notes = Column(Text, nullable=True)
    is_duplicate = Column(Boolean, default=False, nullable=False, index=True)
    duplicate_of_id = Column(Integer, ForeignKey("csv_rows.id"), nullable=True, index=True)

    ats_group = Column(Text)
    location_group = Column(Text)
    search_bucket = Column(Text)
    title = Column(Text)
    title_match_status = Column(Text)
    title_reject_reason = Column(Text)
    url = Column(Text, nullable=False)
    canonical_url = Column(Text, nullable=True)
    canonical_url_hash = Column(String(64), nullable=True)
    display_domain = Column(Text)
    company_guess = Column(Text)
    job_id_guess = Column(Text)
    canonical_company_job_key = Column(Text)
    application_url = Column(Text)
    application_dedupe_key = Column(Text)
    page_number = Column(Text)
    decision = Column(Text)
    rejection_reasons = Column(Text)
    posted_status = Column(Text)
    posted_value = Column(Text)
    posted_source = Column(Text)
    posted_age_days = Column(Text)
    location_status = Column(Text)
    location_evidence = Column(Text)
    is_usa_role = Column(Text)
    location_country = Column(Text)
    location_city = Column(Text)
    location_state = Column(Text)
    location_raw_extracted = Column(Text)
    location_confidence = Column(Text)
    location_source = Column(Text)
    sponsorship_status = Column(Text)
    positive_sponsorship_matches = Column(Text)
    negative_sponsorship_matches = Column(Text)
    sponsorship_evidence_snippet = Column(Text)
    positive_sponsorship_evidence_snippet = Column(Text)
    clearance_matches = Column(Text)
    clearance_evidence_snippet = Column(Text)
    jd_quality_status = Column(Text)
    jd_quality_reasons = Column(Text)
    jd_text_length = Column(Text)
    jd_text = Column(Text)
    extraction_method = Column(Text)
    retry_attempted = Column(Text)
    error = Column(Text)
    source_file = Column(Text)
    work_model_extracted = Column(Text)
    salary_min_extracted = Column(Text)
    salary_max_extracted = Column(Text)
    salary_currency_extracted = Column(Text)
    posted_status_extracted = Column(Text)
    posted_value_extracted = Column(Text)
    posted_source_extracted = Column(Text)
    posted_age_days_extracted = Column(Text)
    sponsorship_status_extracted = Column(Text)
    positive_sponsorship_matches_extracted = Column(Text)
    negative_sponsorship_matches_extracted = Column(Text)
    positive_sponsorship_evidence_extracted = Column(Text)
    negative_sponsorship_evidence_extracted = Column(Text)
    clearance_or_citizenship_extracted = Column(Text)
    clearance_or_citizenship_evidence_extracted = Column(Text)
    education_requirement_extracted = Column(Text)
    employment_type_extracted = Column(Text)
    resume_match_score = Column(Text)
    resume_score = Column(Text)
    fit_category = Column(Text)
    score_confidence = Column(Text)
    role_family = Column(Text)
    seniority_level = Column(Text)
    required_years_min = Column(Text)
    core_languages_extracted = Column(Text)
    core_frameworks_extracted = Column(Text)
    core_cloud_devops_extracted = Column(Text)
    database_requirements_extracted = Column(Text)
    ai_ml_requirements_extracted = Column(Text)
    matched_resume_skills = Column(Text)
    missing_or_weaker_skills = Column(Text)
    score_reason = Column(Text)
    closed_or_unusable_jd = Column(Text)
    closed_or_unusable_reason = Column(Text)

    user = relationship("User", back_populates="rows")
    job_track = relationship("JobTrack", back_populates="csv_row", uselist=False)
    duplicate_of = relationship("CsvRow", remote_side=[id], uselist=False)
    capture_requests = relationship("CaptureRequest", back_populates="row")

    __table_args__ = (
        CheckConstraint(
            "capture_source IS NULL OR capture_source IN ('manual', 'bookmarklet')",
            name="ck_csv_rows_capture_source",
        ),
        CheckConstraint(
            "capture_notes IS NULL OR length(capture_notes) <= 20000",
            name="ck_csv_rows_capture_notes_length",
        ),
        UniqueConstraint("user_id", "url", name="uq_user_url"),
        Index(
            "ix_csv_rows_user_canonical_hash",
            "user_id", "canonical_url_hash",
        ),
    )


class JobTrack(Base):
    __tablename__ = "job_tracks"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    csv_row_id = Column(Integer, ForeignKey("csv_rows.id"), nullable=True, index=True)
    url = Column(Text, nullable=False)
    canonical_url = Column(Text, nullable=True)
    canonical_url_hash = Column(String(64), nullable=True)
    company = Column(Text)
    title = Column(Text)
    ats_group = Column(Text)
    search_bucket = Column(Text)
    resume_match_score = Column(Text)
    status = Column(String(50), default="opened", nullable=False, index=True)
    opened_at = Column(DateTime, nullable=True, index=True)
    applied_at = Column(DateTime, nullable=True, index=True)
    follow_up_at = Column(DateTime, nullable=True, index=True)
    notes = Column(Text)
    session_id = Column(Text)
    open_count = Column(Integer, default=1, nullable=False)
    last_opened_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,
                        nullable=False)

    user = relationship("User", back_populates="job_tracks")
    csv_row = relationship("CsvRow", back_populates="job_track")
    application_evidence = relationship(
        "ApplicationEvidence", back_populates="track"
    )
    reminder_deliveries = relationship(
        "ReminderDelivery", back_populates="track"
    )
    application_documents = relationship(
        "ApplicationDocument", back_populates="track", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("user_id", "url", name="uq_user_job_track_url"),
        Index(
            "ix_job_tracks_user_canonical_hash",
            "user_id", "canonical_url_hash",
        ),
    )


class CaptureRequest(Base):
    """Owner-scoped idempotency record for manual/bookmarklet capture."""

    __tablename__ = "capture_requests"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    request_key = Column(String(36), nullable=False)
    payload_hash = Column(String(64), nullable=False)
    row_id = Column(
        Integer, ForeignKey("csv_rows.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = relationship("User", back_populates="capture_requests")
    row = relationship("CsvRow", back_populates="capture_requests")

    __table_args__ = (
        UniqueConstraint(
            "user_id", "request_key",
            name="uq_capture_request_user_key",
        ),
    )


class RequestWindowCounter(Base):
    """Persisted fixed-window request counter shared across app processes."""

    __tablename__ = "request_window_counters"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    scope = Column(String(64), nullable=False)
    window_start = Column(DateTime, nullable=False, index=True)
    count = Column(Integer, nullable=False, default=0)

    user = relationship("User", back_populates="request_window_counters")

    __table_args__ = (
        CheckConstraint("count >= 0", name="ck_request_window_counters_count"),
        UniqueConstraint(
            "user_id", "scope", "window_start",
            name="uq_request_window_counter_user_scope_window",
        ),
    )


class JobAvailability(Base):
    """Owner-scoped freshness and deadline evidence keyed by original job URL."""

    __tablename__ = "job_availability"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    job_url = Column(Text, nullable=False)
    deadline_at = Column(DateTime, nullable=True, index=True)
    deadline_source = Column(String(16), nullable=True)
    state = Column(String(16), nullable=False, default="unknown", index=True)
    last_checked_at = Column(DateTime, nullable=True)
    check_reason = Column(String(64), nullable=True)
    confirmed_closed_at = Column(DateTime, nullable=True)
    version = Column(Integer, nullable=False, default=1)

    user = relationship("User", back_populates="job_availability")
    check_requests = relationship(
        "JobCheckRequest", back_populates="availability", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "job_url",
            name="uq_job_availability_user_url",
        ),
        CheckConstraint(
            "state IN ('unknown', 'available', 'unavailable', 'closed')",
            name="ck_job_availability_state",
        ),
        CheckConstraint(
            "deadline_source IS NULL OR deadline_source IN ('user', 'import')",
            name="ck_job_availability_deadline_source",
        ),
        CheckConstraint(
            "version > 0",
            name="ck_job_availability_version",
        ),
        CheckConstraint(
            "(state = 'closed' AND confirmed_closed_at IS NOT NULL) OR "
            "(state <> 'closed' AND confirmed_closed_at IS NULL)",
            name="ck_job_availability_closed_confirmation",
        ),
        Index(
            "ix_job_availability_user_deadline",
            "user_id", "deadline_at",
        ),
    )


class JobCheckRequest(Base):
    """Durable, bounded metadata for an explicit future link-check attempt."""

    __tablename__ = "job_check_requests"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    availability_id = Column(
        Integer, ForeignKey("job_availability.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    requested_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    status = Column(String(16), nullable=False, default="pending")
    lease_until = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_code = Column(String(64), nullable=True)

    user = relationship("User", back_populates="job_check_requests")
    availability = relationship("JobAvailability", back_populates="check_requests")

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'done', 'failed')",
            name="ck_job_check_requests_status",
        ),
        Index(
            "ix_job_check_requests_user_requested",
            "user_id", "requested_at",
        ),
        Index(
            "ix_job_check_requests_status_lease",
            "status", "lease_until",
        ),
    )


class DocumentVersion(Base):
    """Immutable, owner-scoped resume or cover-letter file version."""

    __tablename__ = "document_versions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    document_family_id = Column(String(36), nullable=False, index=True)
    kind = Column(String(20), nullable=False)
    label = Column(String(150), nullable=False)
    original_filename = Column(String(255), nullable=False)
    media_type = Column(String(32), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False)
    storage_key = Column(String(255), nullable=False, unique=True)
    version_number = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    state = Column(String(16), default="pending", nullable=False, index=True)

    user = relationship("User", back_populates="document_versions")
    application_documents = relationship(
        "ApplicationDocument", back_populates="document_version"
    )
    create_receipts = relationship(
        "DocumentCreateReceipt", back_populates="document_version"
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "document_family_id", "version_number",
            name="uq_document_version_user_family_version",
        ),
        CheckConstraint(
            "kind IN ('resume', 'cover_letter')",
            name="ck_document_versions_kind",
        ),
        CheckConstraint(
            "media_type IN ('application/pdf', 'text/plain')",
            name="ck_document_versions_media_type",
        ),
        CheckConstraint(
            "state IN ('pending', 'ready', 'failed', 'deleted')",
            name="ck_document_versions_state",
        ),
        CheckConstraint(
            "size_bytes >= 0 AND size_bytes <= 10485760",
            name="ck_document_versions_size",
        ),
        CheckConstraint(
            "version_number > 0",
            name="ck_document_versions_version_number",
        ),
        Index(
            "ix_document_versions_user_kind_created",
            "user_id", "kind", "created_at",
        ),
        Index(
            "ix_document_versions_user_family",
            "user_id", "document_family_id",
        ),
    )


class ApplicationDocument(Base):
    """A user's assertion that an immutable document was used or referenced."""

    __tablename__ = "application_documents"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    track_id = Column(
        Integer, ForeignKey("job_tracks.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    document_version_id = Column(
        String(36), ForeignKey("document_versions.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    kind = Column(String(20), nullable=False)
    usage = Column(String(16), nullable=False)
    attached_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="application_documents")
    track = relationship("JobTrack", back_populates="application_documents")
    document_version = relationship(
        "DocumentVersion", back_populates="application_documents"
    )

    __table_args__ = (
        UniqueConstraint(
            "track_id", "document_version_id",
            name="uq_application_document_track_version",
        ),
        CheckConstraint(
            "kind IN ('resume', 'cover_letter')",
            name="ck_application_documents_kind",
        ),
        CheckConstraint(
            "usage IN ('used', 'reference')",
            name="ck_application_documents_usage",
        ),
        Index(
            "uq_application_document_used_kind",
            "user_id", "track_id", "kind",
            unique=True,
            sqlite_where=text("usage = 'used'"),
            postgresql_where=text("usage = 'used'"),
        ),
    )


class DocumentCreateReceipt(Base):
    """Thirty-day idempotency record for document upload requests."""

    __tablename__ = "document_create_receipts"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    request_key = Column(String(36), nullable=False)
    payload_hash = Column(String(64), nullable=False)
    document_id = Column(
        String(36), ForeignKey("document_versions.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    status = Column(String(16), nullable=False, default="ready")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = relationship("User", back_populates="document_create_receipts")
    document_version = relationship(
        "DocumentVersion", back_populates="create_receipts"
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "request_key",
            name="uq_document_create_receipt_user_key",
        ),
        CheckConstraint(
            "status IN ('pending', 'ready', 'failed')",
            name="ck_document_create_receipts_status",
        ),
    )


_DOCUMENT_IMMUTABLE_FIELDS = (
    "user_id",
    "document_family_id",
    "kind",
    "original_filename",
    "media_type",
    "size_bytes",
    "sha256",
    "storage_key",
    "version_number",
)


@event.listens_for(DocumentVersion, "before_update")
def _prevent_document_content_overwrite(mapper, connection, target) -> None:
    state = inspect(target)
    changed = [
        field
        for field in _DOCUMENT_IMMUTABLE_FIELDS
        if state.attrs[field].history.has_changes()
    ]
    if changed:
        raise ValueError(
            "Document version content is immutable; upload a new version instead."
        )


class ReminderPreference(Base):
    """Owner-scoped reminder opt-in and local scheduling preferences."""

    __tablename__ = "reminder_preferences"

    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    enabled = Column(Boolean, default=False, nullable=False)
    channel = Column(String(16), default="in_app", nullable=False)
    local_time = Column(String(5), default="09:00", nullable=False)
    quiet_start = Column(String(5), default="21:00", nullable=False)
    quiet_end = Column(String(5), default="08:00", nullable=False)

    user = relationship("User", back_populates="reminder_preference")

    __table_args__ = (
        CheckConstraint(
            "channel IN ('in_app', 'email')",
            name="ck_reminder_preferences_channel",
        ),
        CheckConstraint(
            "length(local_time) = 5 AND substr(local_time, 3, 1) = ':' AND "
            "substr(local_time, 1, 2) BETWEEN '00' AND '23' AND "
            "substr(local_time, 4, 2) BETWEEN '00' AND '59'",
            name="ck_reminder_preferences_local_time_shape",
        ),
        CheckConstraint(
            "length(quiet_start) = 5 AND substr(quiet_start, 3, 1) = ':' AND "
            "substr(quiet_start, 1, 2) BETWEEN '00' AND '23' AND "
            "substr(quiet_start, 4, 2) BETWEEN '00' AND '59'",
            name="ck_reminder_preferences_quiet_start_shape",
        ),
        CheckConstraint(
            "length(quiet_end) = 5 AND substr(quiet_end, 3, 1) = ':' AND "
            "substr(quiet_end, 1, 2) BETWEEN '00' AND '23' AND "
            "substr(quiet_end, 4, 2) BETWEEN '00' AND '59'",
            name="ck_reminder_preferences_quiet_end_shape",
        ),
    )


class ReminderDelivery(Base):
    """Durable reminder occurrence and delivery accounting state."""

    __tablename__ = "reminder_deliveries"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    track_id = Column(
        Integer, ForeignKey("job_tracks.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    occurrence_key = Column(String(255), nullable=False)
    channel = Column(String(16), nullable=False)
    status = Column(String(16), default="pending", nullable=False, index=True)
    scheduled_at = Column(DateTime(timezone=True), nullable=False, index=True)
    lease_until = Column(DateTime(timezone=True), nullable=True, index=True)
    attempt_count = Column(Integer, default=0, nullable=False)
    next_attempt_at = Column(DateTime(timezone=True), nullable=True, index=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
    last_error_code = Column(String(64), nullable=True)
    version = Column(Integer, default=1, nullable=False)

    user = relationship("User", back_populates="reminder_deliveries")
    track = relationship("JobTrack", back_populates="reminder_deliveries")

    __table_args__ = (
        UniqueConstraint(
            "user_id", "occurrence_key", "channel",
            name="uq_reminder_delivery_occurrence_channel",
        ),
        CheckConstraint(
            "channel IN ('in_app', 'email')",
            name="ck_reminder_deliveries_channel",
        ),
        CheckConstraint(
            "status IN ('pending', 'sending', 'sent', 'failed', 'unknown', 'cancelled')",
            name="ck_reminder_deliveries_status",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_reminder_deliveries_attempt_count",
        ),
        CheckConstraint(
            "version > 0",
            name="ck_reminder_deliveries_version",
        ),
        CheckConstraint(
            "(status = 'sent' AND sent_at IS NOT NULL) OR "
            "(status != 'sent' AND sent_at IS NULL)",
            name="ck_reminder_deliveries_sent_at_state",
        ),
        Index(
            "ix_reminder_deliveries_user_schedule",
            "user_id", "scheduled_at",
        ),
        Index(
            "ix_reminder_deliveries_user_status_retry",
            "user_id", "status", "next_attempt_at",
        ),
    )


class CompanyAlias(Base):
    __tablename__ = "company_aliases"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    alias_key = Column(String(320), nullable=False)
    display_name = Column(String(320), nullable=False)
    company_key = Column(String(36), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="company_aliases")

    __table_args__ = (
        UniqueConstraint(
            "user_id", "alias_key", name="uq_company_alias_user_alias_key"
        ),
        Index(
            "ix_company_aliases_user_company_key",
            "user_id", "company_key",
        ),
    )


class ApplicationEvidence(Base):
    """Owner-scoped evidence attached to durable application memory.

    Deleted evidence remains as a marker. Its private body may be retained only
    for the bounded recovery window and is redacted by ordinary serializers.
    """

    __tablename__ = "application_evidence"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    track_id = Column(
        Integer, ForeignKey("job_tracks.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    kind = Column(String(32), nullable=False)
    body = Column(Text, nullable=True)
    occurred_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False,
    )
    version = Column(Integer, default=1, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)

    user = relationship("User", back_populates="application_evidence")
    track = relationship("JobTrack", back_populates="application_evidence")

    __table_args__ = (
        CheckConstraint(
            "kind IN ('confirmation_url', 'confirmation_text', 'note')",
            name="ck_application_evidence_kind",
        ),
        CheckConstraint("version >= 1", name="ck_application_evidence_version"),
        Index(
            "ix_application_evidence_user_track",
            "user_id", "track_id",
        ),
        Index(
            "ix_application_evidence_user_deleted_updated",
            "user_id", "is_deleted", "updated_at",
        ),
    )


class EvidenceCreateReceipt(Base):
    """Thirty-day idempotency receipt for future evidence-create mutations."""

    __tablename__ = "evidence_create_receipts"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    request_key = Column(String(36), nullable=False)
    payload_hash = Column(String(64), nullable=False)
    evidence_id = Column(
        Integer, ForeignKey("application_evidence.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = relationship("User", back_populates="evidence_create_receipts")
    evidence = relationship("ApplicationEvidence")

    __table_args__ = (
        UniqueConstraint(
            "user_id", "request_key", name="uq_evidence_create_receipt_user_key"
        ),
    )


class JobLifecycleEvent(Base):
    __tablename__ = "job_lifecycle_events"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    event_key = Column(String(160), nullable=False)
    job_url = Column(Text, nullable=False)
    csv_row_id = Column(
        Integer, ForeignKey("csv_rows.id", ondelete="SET NULL"), nullable=True
    )
    job_track_id = Column(
        Integer, ForeignKey("job_tracks.id", ondelete="SET NULL"), nullable=True
    )
    kind = Column(String(32), nullable=False)
    occurred_at = Column(DateTime, nullable=False)
    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    source = Column(String(32), nullable=False)
    payload = Column(JSON, default=dict, nullable=False)

    user = relationship("User", back_populates="lifecycle_events")

    __table_args__ = (
        UniqueConstraint(
            "user_id", "event_key", name="uq_user_lifecycle_event_key"
        ),
        Index(
            "ix_job_lifecycle_events_user_time_kind",
            "user_id", "occurred_at", "kind",
        ),
    )


class SavedView(Base):
    __tablename__ = "saved_views"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    name = Column(String(120), nullable=False)
    view_type = Column(String(50), nullable=False, default="job_links")
    filters = Column(JSON, default=dict, nullable=False)
    is_pinned = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "name", "view_type", name="uq_user_saved_view"),
    )


class SearchSession(Base):
    __tablename__ = "search_sessions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    name = Column(String(160), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ended_at = Column(DateTime, nullable=True)
    notes = Column(Text)


class ColumnPreference(Base):
    __tablename__ = "column_preferences"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),
                     primary_key=True)
    hidden_columns = Column(JSON, default=list, nullable=False)
    column_order = Column(JSON, default=list, nullable=False)

    user = relationship("User", back_populates="preference")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("search_sessions.id"), nullable=True, index=True)
    event_type = Column(String(100), nullable=False, index=True)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(Integer, nullable=True)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class ApplyPilotBatch(Base):
    __tablename__ = "applypilot_batches"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("search_sessions.id"), nullable=True)
    name = Column(String(200))
    payload_json = Column(JSON, nullable=False)
    status = Column(String(50), default="downloaded", nullable=False)
    job_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserGoal(Base):
    __tablename__ = "user_goals"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),
                     primary_key=True)
    open_per_day = Column(Integer, default=30)
    apply_per_day = Column(Integer, default=10)
    followup_per_day = Column(Integer, default=5)
    applypilot_per_day = Column(Integer, default=5)


class WorkItem(Base):
    """Durable manual action for the Today queue.

    Follow-up actions remain derived from JobTrack.follow_up_at and are never
    copied into this table.
    """

    __tablename__ = "work_items"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    track_id = Column(
        Integer, ForeignKey("job_tracks.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    row_id = Column(
        Integer, ForeignKey("csv_rows.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    source_view_id = Column(
        Integer, ForeignKey("saved_views.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    origin_key = Column(String(255), nullable=True)
    description = Column(String(500), nullable=False)
    due_at = Column(DateTime(timezone=True), nullable=True, index=True)
    priority = Column(SmallInteger, nullable=False, default=1)
    state = Column(String(16), nullable=False, default="pending", index=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="work_items")
    track = relationship("JobTrack")
    row = relationship("CsvRow")
    source_view = relationship("SavedView")

    __table_args__ = (
        UniqueConstraint(
            "user_id", "origin_key", name="uq_user_work_item_origin_key"
        ),
        CheckConstraint(
            "length(trim(description)) BETWEEN 1 AND 500 "
            "AND description = trim(description)",
            name="ck_work_items_description_trimmed_length",
        ),
        CheckConstraint(
            "priority >= 0 AND priority <= 3",
            name="ck_work_items_priority_range",
        ),
        CheckConstraint(
            "state IN ('pending', 'done')",
            name="ck_work_items_state",
        ),
        CheckConstraint("version > 0", name="ck_work_items_version_positive"),
        CheckConstraint(
            "state != 'done' OR completed_at IS NOT NULL",
            name="ck_work_items_done_has_completed_at",
        ),
        Index("ix_work_items_user_due", "user_id", "due_at"),
    )


class WorkItemOverride(Base):
    """Per-user snooze state for a server-generated Today action key."""

    __tablename__ = "work_item_overrides"

    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    action_key = Column(String(255), primary_key=True)
    snoozed_until = Column(DateTime(timezone=True), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)

    user = relationship("User", back_populates="work_item_overrides")

    __table_args__ = (
        CheckConstraint(
            "length(action_key) BETWEEN 1 AND 255",
            name="ck_work_item_overrides_action_key_length",
        ),
        CheckConstraint(
            "version > 0",
            name="ck_work_item_overrides_version_positive",
        ),
        Index(
            "ix_work_item_overrides_user_snoozed",
            "user_id", "snoozed_until",
        ),
    )


class MaintenanceStatus(Base):
    """Durable aggregate health for cross-process maintenance workers."""

    __tablename__ = "maintenance_status"

    job_name = Column(String(100), primary_key=True)
    outcome = Column(String(32), nullable=False)
    last_attempted_at = Column(DateTime, nullable=False)
    last_successful_at = Column(DateTime, nullable=True)
    last_failed_at = Column(DateTime, nullable=True)
    result_json = Column(JSON, default=dict, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class BackupImportMap(Base):
    """Stable mapping from a portable backup reference to a destination row."""

    __tablename__ = "backup_import_maps"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    backup_id = Column(String(36), nullable=False)
    section = Column(String(50), nullable=False)
    backup_ref = Column(String(255), nullable=False)
    target_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "user_id", "backup_id", "section", "backup_ref",
            name="uq_backup_import_map_identity",
        ),
    )
