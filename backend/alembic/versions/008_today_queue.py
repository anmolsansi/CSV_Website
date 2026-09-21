"""add Today work items and follow-up overrides

Revision ID: 008
Revises: 007
Create Date: 2026-09-21

JG-025 adds durable manual actions plus per-user snooze overrides. Existing
JobTrack.follow_up_at remains the source of truth for derived follow-up actions.
The migration is additive and all source references detach with SET NULL.
"""

from alembic import op
import sqlalchemy as sa


revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "work_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("track_id", sa.Integer(), nullable=True),
        sa.Column("row_id", sa.Integer(), nullable=True),
        sa.Column("source_view_id", sa.Integer(), nullable=True),
        sa.Column("origin_key", sa.String(length=255), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("priority", sa.SmallInteger(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "length(trim(description)) BETWEEN 1 AND 500 "
            "AND description = trim(description)",
            name="ck_work_items_description_trimmed_length",
        ),
        sa.CheckConstraint(
            "priority >= 0 AND priority <= 3",
            name="ck_work_items_priority_range",
        ),
        sa.CheckConstraint(
            "state IN ('pending', 'done')",
            name="ck_work_items_state",
        ),
        sa.CheckConstraint(
            "version > 0",
            name="ck_work_items_version_positive",
        ),
        sa.CheckConstraint(
            "state != 'done' OR completed_at IS NOT NULL",
            name="ck_work_items_done_has_completed_at",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["track_id"], ["job_tracks.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["row_id"], ["csv_rows.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["source_view_id"], ["saved_views.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "origin_key", name="uq_user_work_item_origin_key"
        ),
    )
    op.create_index("ix_work_items_user_id", "work_items", ["user_id"])
    op.create_index("ix_work_items_track_id", "work_items", ["track_id"])
    op.create_index("ix_work_items_row_id", "work_items", ["row_id"])
    op.create_index(
        "ix_work_items_source_view_id", "work_items", ["source_view_id"]
    )
    op.create_index("ix_work_items_due_at", "work_items", ["due_at"])
    op.create_index("ix_work_items_state", "work_items", ["state"])
    op.create_index(
        "ix_work_items_user_due", "work_items", ["user_id", "due_at"]
    )

    op.create_table(
        "work_item_overrides",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("action_key", sa.String(length=255), nullable=False),
        sa.Column(
            "snoozed_until", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "length(action_key) BETWEEN 1 AND 255",
            name="ck_work_item_overrides_action_key_length",
        ),
        sa.CheckConstraint(
            "version > 0",
            name="ck_work_item_overrides_version_positive",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("user_id", "action_key"),
    )
    op.create_index(
        "ix_work_item_overrides_snoozed_until",
        "work_item_overrides",
        ["snoozed_until"],
    )
    op.create_index(
        "ix_work_item_overrides_user_snoozed",
        "work_item_overrides",
        ["user_id", "snoozed_until"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_work_item_overrides_user_snoozed",
        table_name="work_item_overrides",
    )
    op.drop_index(
        "ix_work_item_overrides_snoozed_until",
        table_name="work_item_overrides",
    )
    op.drop_table("work_item_overrides")

    op.drop_index("ix_work_items_user_due", table_name="work_items")
    op.drop_index("ix_work_items_state", table_name="work_items")
    op.drop_index("ix_work_items_due_at", table_name="work_items")
    op.drop_index("ix_work_items_source_view_id", table_name="work_items")
    op.drop_index("ix_work_items_row_id", table_name="work_items")
    op.drop_index("ix_work_items_track_id", table_name="work_items")
    op.drop_index("ix_work_items_user_id", table_name="work_items")
    op.drop_table("work_items")
