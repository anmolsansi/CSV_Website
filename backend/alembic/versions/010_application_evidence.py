"""add application evidence and create receipts

Revision ID: 010
Revises: 009
Create Date: 2026-09-22

JG-033 adds owner-scoped application evidence plus thirty-day create
idempotency receipts. The migration is additive because revision 009 is
already the JG-030 job-identity migration on main.
"""

from alembic import op
import sqlalchemy as sa


revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "application_evidence",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("track_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('confirmation_url', 'confirmation_text', 'note')",
            name="ck_application_evidence_kind",
        ),
        sa.CheckConstraint("version >= 1", name="ck_application_evidence_version"),
        sa.ForeignKeyConstraint(["track_id"], ["job_tracks.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_application_evidence_user_id",
        "application_evidence",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_application_evidence_track_id",
        "application_evidence",
        ["track_id"],
        unique=False,
    )
    op.create_index(
        "ix_application_evidence_user_track",
        "application_evidence",
        ["user_id", "track_id"],
        unique=False,
    )
    op.create_index(
        "ix_application_evidence_user_deleted_updated",
        "application_evidence",
        ["user_id", "is_deleted", "updated_at"],
        unique=False,
    )

    op.create_table(
        "evidence_create_receipts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("request_key", sa.String(length=36), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("evidence_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["evidence_id"], ["application_evidence.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "request_key", name="uq_evidence_create_receipt_user_key"
        ),
    )
    op.create_index(
        "ix_evidence_create_receipts_user_id",
        "evidence_create_receipts",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_evidence_create_receipts_evidence_id",
        "evidence_create_receipts",
        ["evidence_id"],
        unique=False,
    )
    op.create_index(
        "ix_evidence_create_receipts_created_at",
        "evidence_create_receipts",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_evidence_create_receipts_created_at",
        table_name="evidence_create_receipts",
    )
    op.drop_index(
        "ix_evidence_create_receipts_evidence_id",
        table_name="evidence_create_receipts",
    )
    op.drop_index(
        "ix_evidence_create_receipts_user_id",
        table_name="evidence_create_receipts",
    )
    op.drop_table("evidence_create_receipts")

    op.drop_index(
        "ix_application_evidence_user_deleted_updated",
        table_name="application_evidence",
    )
    op.drop_index(
        "ix_application_evidence_user_track",
        table_name="application_evidence",
    )
    op.drop_index(
        "ix_application_evidence_track_id",
        table_name="application_evidence",
    )
    op.drop_index(
        "ix_application_evidence_user_id",
        table_name="application_evidence",
    )
    op.drop_table("application_evidence")
