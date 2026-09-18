"""Add durable job lifecycle events.

Revision ID: 004
Revises: 003
Create Date: 2026-09-18
"""
from alembic import op
import sqlalchemy as sa


revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_lifecycle_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("event_key", sa.String(length=160), nullable=False),
        sa.Column("job_url", sa.Text(), nullable=False),
        sa.Column("csv_row_id", sa.Integer(), nullable=True),
        sa.Column("job_track_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["csv_row_id"], ["csv_rows.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["job_track_id"], ["job_tracks.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "user_id", "event_key", name="uq_user_lifecycle_event_key"
        ),
    )
    op.create_index(
        "ix_job_lifecycle_events_user_id",
        "job_lifecycle_events",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_job_lifecycle_events_user_time_kind",
        "job_lifecycle_events",
        ["user_id", "occurred_at", "kind"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_job_lifecycle_events_user_time_kind",
        table_name="job_lifecycle_events",
    )
    op.drop_index(
        "ix_job_lifecycle_events_user_id",
        table_name="job_lifecycle_events",
    )
    op.drop_table("job_lifecycle_events")
