"""add reminder preferences and delivery state

Revision ID: 011
Revises: 010
Create Date: 2026-09-22

JG-037 adds durable, owner-scoped reminder preferences and reminder delivery
accounting. The migration is additive and does not activate any scheduler or
external delivery transport.
"""

from alembic import op
import sqlalchemy as sa


revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def _time_shape(field: str) -> str:
    return (
        f"length({field}) = 5 AND substr({field}, 3, 1) = ':' AND "
        f"substr({field}, 1, 2) BETWEEN '00' AND '23' AND "
        f"substr({field}, 4, 2) BETWEEN '00' AND '59'"
    )


def upgrade() -> None:
    op.create_table(
        "reminder_preferences",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("channel", sa.String(length=16), nullable=False, server_default="in_app"),
        sa.Column("local_time", sa.String(length=5), nullable=False, server_default="09:00"),
        sa.Column("quiet_start", sa.String(length=5), nullable=False, server_default="21:00"),
        sa.Column("quiet_end", sa.String(length=5), nullable=False, server_default="08:00"),
        sa.CheckConstraint(
            "channel IN ('in_app', 'email')",
            name="ck_reminder_preferences_channel",
        ),
        sa.CheckConstraint(
            _time_shape("local_time"),
            name="ck_reminder_preferences_local_time_shape",
        ),
        sa.CheckConstraint(
            _time_shape("quiet_start"),
            name="ck_reminder_preferences_quiet_start_shape",
        ),
        sa.CheckConstraint(
            _time_shape("quiet_end"),
            name="ck_reminder_preferences_quiet_end_shape",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "reminder_deliveries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("track_id", sa.Integer(), nullable=True),
        sa.Column("occurrence_key", sa.String(length=255), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "channel IN ('in_app', 'email')",
            name="ck_reminder_deliveries_channel",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'sending', 'sent', 'failed', 'unknown', 'cancelled')",
            name="ck_reminder_deliveries_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_reminder_deliveries_attempt_count",
        ),
        sa.CheckConstraint(
            "version > 0",
            name="ck_reminder_deliveries_version",
        ),
        sa.CheckConstraint(
            "(status = 'sent' AND sent_at IS NOT NULL) OR "
            "(status != 'sent' AND sent_at IS NULL)",
            name="ck_reminder_deliveries_sent_at_state",
        ),
        sa.ForeignKeyConstraint(["track_id"], ["job_tracks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "occurrence_key", "channel",
            name="uq_reminder_delivery_occurrence_channel",
        ),
    )
    op.create_index(
        "ix_reminder_deliveries_user_id",
        "reminder_deliveries",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_reminder_deliveries_track_id",
        "reminder_deliveries",
        ["track_id"],
        unique=False,
    )
    op.create_index(
        "ix_reminder_deliveries_status",
        "reminder_deliveries",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_reminder_deliveries_scheduled_at",
        "reminder_deliveries",
        ["scheduled_at"],
        unique=False,
    )
    op.create_index(
        "ix_reminder_deliveries_lease_until",
        "reminder_deliveries",
        ["lease_until"],
        unique=False,
    )
    op.create_index(
        "ix_reminder_deliveries_next_attempt_at",
        "reminder_deliveries",
        ["next_attempt_at"],
        unique=False,
    )
    op.create_index(
        "ix_reminder_deliveries_user_schedule",
        "reminder_deliveries",
        ["user_id", "scheduled_at"],
        unique=False,
    )
    op.create_index(
        "ix_reminder_deliveries_user_status_retry",
        "reminder_deliveries",
        ["user_id", "status", "next_attempt_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_reminder_deliveries_user_status_retry",
        table_name="reminder_deliveries",
    )
    op.drop_index(
        "ix_reminder_deliveries_user_schedule",
        table_name="reminder_deliveries",
    )
    op.drop_index(
        "ix_reminder_deliveries_next_attempt_at",
        table_name="reminder_deliveries",
    )
    op.drop_index(
        "ix_reminder_deliveries_lease_until",
        table_name="reminder_deliveries",
    )
    op.drop_index(
        "ix_reminder_deliveries_scheduled_at",
        table_name="reminder_deliveries",
    )
    op.drop_index(
        "ix_reminder_deliveries_status",
        table_name="reminder_deliveries",
    )
    op.drop_index(
        "ix_reminder_deliveries_track_id",
        table_name="reminder_deliveries",
    )
    op.drop_index(
        "ix_reminder_deliveries_user_id",
        table_name="reminder_deliveries",
    )
    op.drop_table("reminder_deliveries")
    op.drop_table("reminder_preferences")
