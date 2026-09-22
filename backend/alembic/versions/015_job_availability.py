"""add job availability, deadlines, and durable check request metadata

Revision ID: 015
Revises: 014
Create Date: 2026-09-22

JG-049 stores owner-scoped URL availability independently of CSV rows. The
transient JobCheckRequest table keeps only bounded request/lease metadata and is
excluded from portable backups.
"""

from alembic import op
import sqlalchemy as sa


revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_availability",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("job_url", sa.Text(), nullable=False),
        sa.Column("deadline_at", sa.DateTime(), nullable=True),
        sa.Column("deadline_source", sa.String(length=16), nullable=True),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="unknown"),
        sa.Column("last_checked_at", sa.DateTime(), nullable=True),
        sa.Column("check_reason", sa.String(length=64), nullable=True),
        sa.Column("confirmed_closed_at", sa.DateTime(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "state IN ('unknown', 'available', 'unavailable', 'closed')",
            name="ck_job_availability_state",
        ),
        sa.CheckConstraint(
            "deadline_source IS NULL OR deadline_source IN ('user', 'import')",
            name="ck_job_availability_deadline_source",
        ),
        sa.CheckConstraint("version > 0", name="ck_job_availability_version"),
        sa.CheckConstraint(
            "(state = 'closed' AND confirmed_closed_at IS NOT NULL) OR "
            "(state <> 'closed' AND confirmed_closed_at IS NULL)",
            name="ck_job_availability_closed_confirmation",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "job_url", name="uq_job_availability_user_url"),
    )
    op.create_index("ix_job_availability_user_id", "job_availability", ["user_id"], unique=False)
    op.create_index("ix_job_availability_deadline_at", "job_availability", ["deadline_at"], unique=False)
    op.create_index("ix_job_availability_state", "job_availability", ["state"], unique=False)
    op.create_index(
        "ix_job_availability_user_deadline",
        "job_availability",
        ["user_id", "deadline_at"],
        unique=False,
    )

    op.create_table(
        "job_check_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("availability_id", sa.Integer(), nullable=False),
        sa.Column("requested_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("lease_until", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'done', 'failed')",
            name="ck_job_check_requests_status",
        ),
        sa.ForeignKeyConstraint(["availability_id"], ["job_availability.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_job_check_requests_user_id", "job_check_requests", ["user_id"], unique=False)
    op.create_index("ix_job_check_requests_availability_id", "job_check_requests", ["availability_id"], unique=False)
    op.create_index(
        "ix_job_check_requests_user_requested",
        "job_check_requests",
        ["user_id", "requested_at"],
        unique=False,
    )
    op.create_index(
        "ix_job_check_requests_status_lease",
        "job_check_requests",
        ["status", "lease_until"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_job_check_requests_status_lease", table_name="job_check_requests")
    op.drop_index("ix_job_check_requests_user_requested", table_name="job_check_requests")
    op.drop_index("ix_job_check_requests_availability_id", table_name="job_check_requests")
    op.drop_index("ix_job_check_requests_user_id", table_name="job_check_requests")
    op.drop_table("job_check_requests")

    op.drop_index("ix_job_availability_user_deadline", table_name="job_availability")
    op.drop_index("ix_job_availability_state", table_name="job_availability")
    op.drop_index("ix_job_availability_deadline_at", table_name="job_availability")
    op.drop_index("ix_job_availability_user_id", table_name="job_availability")
    op.drop_table("job_availability")
