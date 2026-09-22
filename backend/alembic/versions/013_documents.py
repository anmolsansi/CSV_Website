"""add immutable application document versions

Revision ID: 013
Revises: 012
Create Date: 2026-09-22

JG-041 adds private document metadata, immutable family versions, application
associations, and idempotency receipts. Document bytes remain outside the
database and are not made recoverable by this migration.
"""

from alembic import op
import sqlalchemy as sa


revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("document_family_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("label", sa.String(length=150), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=32), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=255), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="pending"),
        sa.CheckConstraint(
            "kind IN ('resume', 'cover_letter')",
            name="ck_document_versions_kind",
        ),
        sa.CheckConstraint(
            "media_type IN ('application/pdf', 'text/plain')",
            name="ck_document_versions_media_type",
        ),
        sa.CheckConstraint(
            "state IN ('pending', 'ready', 'failed', 'deleted')",
            name="ck_document_versions_state",
        ),
        sa.CheckConstraint(
            "size_bytes >= 0 AND size_bytes <= 10485760",
            name="ck_document_versions_size",
        ),
        sa.CheckConstraint(
            "version_number > 0",
            name="ck_document_versions_version_number",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key", name="uq_document_versions_storage_key"),
        sa.UniqueConstraint(
            "user_id", "document_family_id", "version_number",
            name="uq_document_version_user_family_version",
        ),
    )
    op.create_index(
        "ix_document_versions_user_id", "document_versions", ["user_id"], unique=False
    )
    op.create_index(
        "ix_document_versions_document_family_id",
        "document_versions",
        ["document_family_id"],
        unique=False,
    )
    op.create_index(
        "ix_document_versions_state", "document_versions", ["state"], unique=False
    )
    op.create_index(
        "ix_document_versions_user_kind_created",
        "document_versions",
        ["user_id", "kind", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_document_versions_user_family",
        "document_versions",
        ["user_id", "document_family_id"],
        unique=False,
    )

    op.create_table(
        "application_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("track_id", sa.Integer(), nullable=False),
        sa.Column("document_version_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("usage", sa.String(length=16), nullable=False),
        sa.Column("attached_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('resume', 'cover_letter')",
            name="ck_application_documents_kind",
        ),
        sa.CheckConstraint(
            "usage IN ('used', 'reference')",
            name="ck_application_documents_usage",
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"], ["document_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["track_id"], ["job_tracks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "track_id", "document_version_id",
            name="uq_application_document_track_version",
        ),
    )
    op.create_index(
        "ix_application_documents_user_id",
        "application_documents",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_application_documents_track_id",
        "application_documents",
        ["track_id"],
        unique=False,
    )
    op.create_index(
        "ix_application_documents_document_version_id",
        "application_documents",
        ["document_version_id"],
        unique=False,
    )
    op.create_index(
        "uq_application_document_used_kind",
        "application_documents",
        ["user_id", "track_id", "kind"],
        unique=True,
        postgresql_where=sa.text("usage = 'used'"),
        sqlite_where=sa.text("usage = 'used'"),
    )

    op.create_table(
        "document_create_receipts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("request_key", sa.String(length=36), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="ready"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'ready', 'failed')",
            name="ck_document_create_receipts_status",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["document_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "request_key",
            name="uq_document_create_receipt_user_key",
        ),
    )
    op.create_index(
        "ix_document_create_receipts_user_id",
        "document_create_receipts",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_document_create_receipts_document_id",
        "document_create_receipts",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        "ix_document_create_receipts_created_at",
        "document_create_receipts",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_document_create_receipts_created_at",
        table_name="document_create_receipts",
    )
    op.drop_index(
        "ix_document_create_receipts_document_id",
        table_name="document_create_receipts",
    )
    op.drop_index(
        "ix_document_create_receipts_user_id",
        table_name="document_create_receipts",
    )
    op.drop_table("document_create_receipts")

    op.drop_index(
        "uq_application_document_used_kind",
        table_name="application_documents",
    )
    op.drop_index(
        "ix_application_documents_document_version_id",
        table_name="application_documents",
    )
    op.drop_index(
        "ix_application_documents_track_id",
        table_name="application_documents",
    )
    op.drop_index(
        "ix_application_documents_user_id",
        table_name="application_documents",
    )
    op.drop_table("application_documents")

    op.drop_index(
        "ix_document_versions_user_family",
        table_name="document_versions",
    )
    op.drop_index(
        "ix_document_versions_user_kind_created",
        table_name="document_versions",
    )
    op.drop_index(
        "ix_document_versions_state",
        table_name="document_versions",
    )
    op.drop_index(
        "ix_document_versions_document_family_id",
        table_name="document_versions",
    )
    op.drop_index(
        "ix_document_versions_user_id",
        table_name="document_versions",
    )
    op.drop_table("document_versions")
