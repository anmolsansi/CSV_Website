from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from .database import Base


CONTACT_ROLE_VALUES = ("recruiter", "referrer", "interviewer", "other")
INTERVIEW_KIND_VALUES = ("phone", "video", "onsite", "other")
INTERVIEW_STATUS_VALUES = ("scheduled", "completed", "cancelled")


class Contact(Base):
    """Owner-scoped private recruiter/referrer/interviewer record."""

    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    email = Column(String(320), nullable=True)
    profile_url = Column(String(2048), nullable=True)
    company_display = Column(String(300), nullable=True)
    notes = Column(Text, nullable=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_deleted = Column(Boolean, nullable=False, default=False, index=True)

    __table_args__ = (
        CheckConstraint("length(name) BETWEEN 1 AND 200", name="ck_contacts_name_length"),
        CheckConstraint("email IS NULL OR length(email) <= 320", name="ck_contacts_email_length"),
        CheckConstraint("profile_url IS NULL OR length(profile_url) <= 2048", name="ck_contacts_profile_url_length"),
        CheckConstraint("company_display IS NULL OR length(company_display) <= 300", name="ck_contacts_company_length"),
        CheckConstraint("notes IS NULL OR length(notes) <= 20000", name="ck_contacts_notes_length"),
        CheckConstraint("version > 0", name="ck_contacts_version"),
        Index("ix_contacts_user_name", "user_id", "name"),
        Index("ix_contacts_user_deleted", "user_id", "is_deleted"),
    )


class ApplicationContact(Base):
    """Owner-scoped association between an application and a contact."""

    __tablename__ = "application_contacts"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    track_id = Column(Integer, ForeignKey("job_tracks.id", ondelete="CASCADE"), nullable=False, index=True)
    contact_id = Column(Integer, ForeignKey("contacts.id", ondelete="RESTRICT"), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    referral_source = Column(String(300), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint(
            "role IN ('recruiter', 'referrer', 'interviewer', 'other')",
            name="ck_application_contacts_role",
        ),
        CheckConstraint(
            "referral_source IS NULL OR length(referral_source) <= 300",
            name="ck_application_contacts_referral_source_length",
        ),
        UniqueConstraint("track_id", "contact_id", "role", name="uq_application_contact_track_contact_role"),
        Index("ix_application_contacts_user_track", "user_id", "track_id"),
    )


class Interview(Base):
    """Owner-scoped scheduled interview for one application."""

    __tablename__ = "interviews"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    track_id = Column(Integer, ForeignKey("job_tracks.id", ondelete="CASCADE"), nullable=False, index=True)
    contact_id = Column(Integer, ForeignKey("contacts.id", ondelete="RESTRICT"), nullable=True, index=True)
    starts_at = Column(DateTime, nullable=False, index=True)
    ends_at = Column(DateTime, nullable=False, index=True)
    timezone = Column(String(64), nullable=False)
    kind = Column(String(20), nullable=False)
    meeting_url = Column(String(2048), nullable=True)
    location = Column(String(500), nullable=True)
    status = Column(String(20), nullable=False, default="scheduled", index=True)
    notes = Column(Text, nullable=True)
    round_label = Column(String(100), nullable=True)
    preparation_notes = Column(Text, nullable=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        CheckConstraint("kind IN ('phone', 'video', 'onsite', 'other')", name="ck_interviews_kind"),
        CheckConstraint("status IN ('scheduled', 'completed', 'cancelled')", name="ck_interviews_status"),
        CheckConstraint("ends_at > starts_at", name="ck_interviews_time_order"),
        CheckConstraint("ends_at <= starts_at + INTERVAL '24 hours'", name="ck_interviews_max_duration_postgresql"),
        CheckConstraint("length(timezone) BETWEEN 1 AND 64", name="ck_interviews_timezone_length"),
        CheckConstraint("meeting_url IS NULL OR length(meeting_url) <= 2048", name="ck_interviews_meeting_url_length"),
        CheckConstraint("location IS NULL OR length(location) <= 500", name="ck_interviews_location_length"),
        CheckConstraint("notes IS NULL OR length(notes) <= 20000", name="ck_interviews_notes_length"),
        CheckConstraint("round_label IS NULL OR length(round_label) <= 100", name="ck_interviews_round_label_length"),
        CheckConstraint("preparation_notes IS NULL OR length(preparation_notes) <= 20000", name="ck_interviews_preparation_notes_length"),
        CheckConstraint("version > 0", name="ck_interviews_version"),
        Index("ix_interviews_user_track_start", "user_id", "track_id", "starts_at"),
        Index("ix_interviews_user_status_start", "user_id", "status", "starts_at"),
    )


class MutationReceipt(Base):
    """Durable replay record for owner-scoped idempotent mutations."""

    __tablename__ = "mutation_receipts"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    operation_key = Column(String(36), nullable=False)
    scope = Column(String(64), nullable=False)
    payload_hash = Column(String(64), nullable=False)
    result_entity_type = Column(String(40), nullable=False)
    result_entity_id = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    __table_args__ = (
        UniqueConstraint("user_id", "scope", "operation_key", name="uq_mutation_receipt_user_scope_key"),
        CheckConstraint("length(operation_key) = 36", name="ck_mutation_receipts_key_length"),
        CheckConstraint("length(payload_hash) = 64", name="ck_mutation_receipts_hash_length"),
        Index("ix_mutation_receipts_user_created", "user_id", "created_at"),
    )
