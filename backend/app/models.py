from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    JSON,
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


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(320), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    identities = relationship(
        "OAuthIdentity", back_populates="user", cascade="all, delete-orphan"
    )
    rows = relationship("CsvRow", back_populates="user", cascade="all, delete-orphan")
    job_tracks = relationship(
        "JobTrack", back_populates="user", cascade="all, delete-orphan"
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
    is_duplicate = Column(Boolean, default=False, nullable=False, index=True)
    duplicate_of_id = Column(Integer, ForeignKey("csv_rows.id"), nullable=True, index=True)

    ats_group = Column(Text)
    location_group = Column(Text)
    search_bucket = Column(Text)
    title = Column(Text)
    title_match_status = Column(Text)
    title_reject_reason = Column(Text)
    url = Column(Text, nullable=False)
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

    __table_args__ = (
        UniqueConstraint("user_id", "url", name="uq_user_url"),
    )


class JobTrack(Base):
    __tablename__ = "job_tracks"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    csv_row_id = Column(Integer, ForeignKey("csv_rows.id"), nullable=True, index=True)
    url = Column(Text, nullable=False)
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

    __table_args__ = (
        UniqueConstraint("user_id", "url", name="uq_user_job_track_url"),
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
