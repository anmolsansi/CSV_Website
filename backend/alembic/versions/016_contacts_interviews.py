"""add private contacts, application links, interviews, and mutation receipts

Revision ID: 016
Revises: 015
Create Date: 2026-09-23

F8 stores owner-scoped recruiter/interviewer context and calendar-safe interview
metadata. Contacts are soft-deleted and mutation receipts are durable replay
records retained independently of request processes.
"""

from alembic import op
import sqlalchemy as sa


revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contacts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("profile_url", sa.String(length=2048), nullable=True),
        sa.Column("company_display", sa.String(length=300), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.CheckConstraint("length(name) BETWEEN 1 AND 200", name="ck_contacts_name_length"),
        sa.CheckConstraint("email IS NULL OR length(email) <= 320", name="ck_contacts_email_length"),
        sa.CheckConstraint("profile_url IS NULL OR length(profile_url) <= 2048", name="ck_contacts_profile_url_length"),
        sa.CheckConstraint("company_display IS NULL OR length(company_display) <= 300", name="ck_contacts_company_length"),
        sa.CheckConstraint("notes IS NULL OR length(notes) <= 20000", name="ck_contacts_notes_length"),
        sa.CheckConstraint("version > 0", name="ck_contacts_version"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_contacts_user_id", "contacts", ["user_id"], unique=False)
    op.create_index("ix_contacts_is_deleted", "contacts", ["is_deleted"], unique=False)
    op.create_index("ix_contacts_user_name", "contacts", ["user_id", "name"], unique=False)
    op.create_index("ix_contacts_user_deleted", "contacts", ["user_id", "is_deleted"], unique=False)

    op.create_table(
        "application_contacts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("track_id", sa.Integer(), nullable=False),
        sa.Column("contact_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("referral_source", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("role IN ('recruiter', 'referrer', 'interviewer', 'other')", name="ck_application_contacts_role"),
        sa.CheckConstraint("referral_source IS NULL OR length(referral_source) <= 300", name="ck_application_contacts_referral_source_length"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["track_id"], ["job_tracks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("track_id", "contact_id", "role", name="uq_application_contact_track_contact_role"),
    )
    op.create_index("ix_application_contacts_user_id", "application_contacts", ["user_id"], unique=False)
    op.create_index("ix_application_contacts_track_id", "application_contacts", ["track_id"], unique=False)
    op.create_index("ix_application_contacts_contact_id", "application_contacts", ["contact_id"], unique=False)
    op.create_index("ix_application_contacts_user_track", "application_contacts", ["user_id", "track_id"], unique=False)

    op.create_table(
        "interviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("track_id", sa.Integer(), nullable=False),
        sa.Column("contact_id", sa.Integer(), nullable=True),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("meeting_url", sa.String(length=2048), nullable=True),
        sa.Column("location", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="scheduled"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("round_label", sa.String(length=100), nullable=True),
        sa.Column("preparation_notes", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("kind IN ('phone', 'video', 'onsite', 'other')", name="ck_interviews_kind"),
        sa.CheckConstraint("status IN ('scheduled', 'completed', 'cancelled')", name="ck_interviews_status"),
        sa.CheckConstraint("ends_at > starts_at", name="ck_interviews_time_order"),
        sa.CheckConstraint("length(timezone) BETWEEN 1 AND 64", name="ck_interviews_timezone_length"),
        sa.CheckConstraint("meeting_url IS NULL OR length(meeting_url) <= 2048", name="ck_interviews_meeting_url_length"),
        sa.CheckConstraint("location IS NULL OR length(location) <= 500", name="ck_interviews_location_length"),
        sa.CheckConstraint("notes IS NULL OR length(notes) <= 20000", name="ck_interviews_notes_length"),
        sa.CheckConstraint("round_label IS NULL OR length(round_label) <= 100", name="ck_interviews_round_label_length"),
        sa.CheckConstraint("preparation_notes IS NULL OR length(preparation_notes) <= 20000", name="ck_interviews_preparation_notes_length"),
        sa.CheckConstraint("version > 0", name="ck_interviews_version"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["track_id"], ["job_tracks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_interviews_user_id", "interviews", ["user_id"], unique=False)
    op.create_index("ix_interviews_track_id", "interviews", ["track_id"], unique=False)
    op.create_index("ix_interviews_contact_id", "interviews", ["contact_id"], unique=False)
    op.create_index("ix_interviews_starts_at", "interviews", ["starts_at"], unique=False)
    op.create_index("ix_interviews_ends_at", "interviews", ["ends_at"], unique=False)
    op.create_index("ix_interviews_status", "interviews", ["status"], unique=False)
    op.create_index("ix_interviews_user_track_start", "interviews", ["user_id", "track_id", "starts_at"], unique=False)
    op.create_index("ix_interviews_user_status_start", "interviews", ["user_id", "status", "starts_at"], unique=False)

    op.create_table(
        "mutation_receipts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("operation_key", sa.String(length=36), nullable=False),
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("result_entity_type", sa.String(length=40), nullable=False),
        sa.Column("result_entity_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("length(operation_key) = 36", name="ck_mutation_receipts_key_length"),
        sa.CheckConstraint("length(payload_hash) = 64", name="ck_mutation_receipts_hash_length"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "scope", "operation_key", name="uq_mutation_receipt_user_scope_key"),
    )
    op.create_index("ix_mutation_receipts_user_id", "mutation_receipts", ["user_id"], unique=False)
    op.create_index("ix_mutation_receipts_created_at", "mutation_receipts", ["created_at"], unique=False)
    op.create_index("ix_mutation_receipts_user_created", "mutation_receipts", ["user_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_mutation_receipts_user_created", table_name="mutation_receipts")
    op.drop_index("ix_mutation_receipts_created_at", table_name="mutation_receipts")
    op.drop_index("ix_mutation_receipts_user_id", table_name="mutation_receipts")
    op.drop_table("mutation_receipts")

    op.drop_index("ix_interviews_user_status_start", table_name="interviews")
    op.drop_index("ix_interviews_user_track_start", table_name="interviews")
    op.drop_index("ix_interviews_status", table_name="interviews")
    op.drop_index("ix_interviews_ends_at", table_name="interviews")
    op.drop_index("ix_interviews_starts_at", table_name="interviews")
    op.drop_index("ix_interviews_contact_id", table_name="interviews")
    op.drop_index("ix_interviews_track_id", table_name="interviews")
    op.drop_index("ix_interviews_user_id", table_name="interviews")
    op.drop_table("interviews")

    op.drop_index("ix_application_contacts_user_track", table_name="application_contacts")
    op.drop_index("ix_application_contacts_contact_id", table_name="application_contacts")
    op.drop_index("ix_application_contacts_track_id", table_name="application_contacts")
    op.drop_index("ix_application_contacts_user_id", table_name="application_contacts")
    op.drop_table("application_contacts")

    op.drop_index("ix_contacts_user_deleted", table_name="contacts")
    op.drop_index("ix_contacts_user_name", table_name="contacts")
    op.drop_index("ix_contacts_is_deleted", table_name="contacts")
    op.drop_index("ix_contacts_user_id", table_name="contacts")
    op.drop_table("contacts")
