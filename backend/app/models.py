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
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from .database import Base

# All CSV columns are stored as nullable text.
CSV_COLUMNS = [
    "ats_group", "location_group", "search_bucket", "title",
    "title_match_status", "title_reject_reason", "url", "display_domain",
    "company_guess", "job_id_guess", "canonical_company_job_key",
    "page_number", "decision", "rejection_reasons", "posted_status",
    "posted_value", "posted_source", "posted_age_days", "location_status",
    "location_evidence", "sponsorship_status", "positive_sponsorship_matches",
    "negative_sponsorship_matches", "sponsorship_evidence_snippet",
    "positive_sponsorship_evidence_snippet", "clearance_matches",
    "clearance_evidence_snippet", "jd_text_length", "jd_text",
    "extraction_method", "retry_attempted", "error", "resume_match_score",
]


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    # Email is the account identity: multiple OAuth providers with the same
    # email link to the same user.
    email = Column(String(320), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    identities = relationship(
        "OAuthIdentity", back_populates="user", cascade="all, delete-orphan"
    )
    rows = relationship("CsvRow", back_populates="user", cascade="all, delete-orphan")
    preference = relationship(
        "ColumnPreference", back_populates="user", uselist=False,
        cascade="all, delete-orphan",
    )


class OAuthIdentity(Base):
    __tablename__ = "oauth_identities"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    provider = Column(String(50), nullable=False)  # google | microsoft | apple
    provider_id = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="identities")

    __table_args__ = (
        UniqueConstraint("provider", "provider_id", name="uq_provider_identity"),
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

    # CSV data columns
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
    page_number = Column(Text)
    decision = Column(Text)
    rejection_reasons = Column(Text)
    posted_status = Column(Text)
    posted_value = Column(Text)
    posted_source = Column(Text)
    posted_age_days = Column(Text)
    location_status = Column(Text)
    location_evidence = Column(Text)
    sponsorship_status = Column(Text)
    positive_sponsorship_matches = Column(Text)
    negative_sponsorship_matches = Column(Text)
    sponsorship_evidence_snippet = Column(Text)
    positive_sponsorship_evidence_snippet = Column(Text)
    clearance_matches = Column(Text)
    clearance_evidence_snippet = Column(Text)
    jd_text_length = Column(Text)
    jd_text = Column(Text)
    extraction_method = Column(Text)
    retry_attempted = Column(Text)
    error = Column(Text)
    resume_match_score = Column(Text)

    user = relationship("User", back_populates="rows")

    __table_args__ = (
        UniqueConstraint("user_id", "url", name="uq_user_url"),
    )


class ColumnPreference(Base):
    __tablename__ = "column_preferences"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),
                     primary_key=True)
    hidden_columns = Column(JSONB, default=list, nullable=False)
    column_order = Column(JSONB, default=list, nullable=False)

    user = relationship("User", back_populates="preference")
