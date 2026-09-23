"""add optimistic versions and bounded undo journal foundation

Revision ID: 018
Revises: 017
Create Date: 2026-09-23

JG-061 adds conflict-detection versions to CsvRow/JobTrack and private,
owner-scoped bulk-action metadata. Undo routes are deliberately not exposed by
this revision; later F10 tickets own transactional bulk mutation and restore.
"""

from alembic import op
import sqlalchemy as sa


revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "csv_rows",
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.create_check_constraint(
        "ck_csv_rows_version_positive",
        "csv_rows",
        "version > 0",
    )

    op.add_column(
        "job_tracks",
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.create_check_constraint(
        "ck_job_tracks_version_positive",
        "job_tracks",
        "version > 0",
    )

    op.create_table(
        "bulk_actions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("request_key", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="completed"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("undo_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('archive_rows', 'update_rows', 'update_tracks')",
            name="ck_bulk_actions_kind",
        ),
        sa.CheckConstraint(
            "status IN ('completed', 'undone', 'partially_undone', 'expired')",
            name="ck_bulk_actions_status",
        ),
        sa.CheckConstraint("length(id) = 36", name="ck_bulk_actions_id_length"),
        sa.CheckConstraint("length(request_key) = 36", name="ck_bulk_actions_request_key_length"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "request_key", name="uq_bulk_actions_user_request_key"),
    )
    op.create_index("ix_bulk_actions_user_id", "bulk_actions", ["user_id"], unique=False)
    op.create_index("ix_bulk_actions_status", "bulk_actions", ["status"], unique=False)
    op.create_index("ix_bulk_actions_created_at", "bulk_actions", ["created_at"], unique=False)
    op.create_index("ix_bulk_actions_undo_expires_at", "bulk_actions", ["undo_expires_at"], unique=False)
    op.create_index("ix_bulk_actions_user_created", "bulk_actions", ["user_id", "created_at"], unique=False)
    op.create_index("ix_bulk_actions_user_undo_expiry", "bulk_actions", ["user_id", "undo_expires_at"], unique=False)

    op.create_table(
        "bulk_action_effects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("action_id", sa.String(length=36), nullable=False),
        sa.Column("entity_type", sa.String(length=16), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("before_json", sa.JSON(), nullable=True),
        sa.Column("after_version", sa.Integer(), nullable=False),
        sa.Column("undo_status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.CheckConstraint(
            "entity_type IN ('csv_row', 'job_track')",
            name="ck_bulk_action_effects_entity_type",
        ),
        sa.CheckConstraint(
            "undo_status IN ('pending', 'restored', 'conflict', 'missing')",
            name="ck_bulk_action_effects_undo_status",
        ),
        sa.CheckConstraint("after_version > 0", name="ck_bulk_action_effects_after_version_positive"),
        sa.ForeignKeyConstraint(["action_id"], ["bulk_actions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "action_id",
            "entity_type",
            "entity_id",
            name="uq_bulk_action_effect_entity",
        ),
    )
    op.create_index("ix_bulk_action_effects_action_id", "bulk_action_effects", ["action_id"], unique=False)
    op.create_index("ix_bulk_action_effects_undo_status", "bulk_action_effects", ["undo_status"], unique=False)
    op.create_index(
        "ix_bulk_action_effects_action_status",
        "bulk_action_effects",
        ["action_id", "undo_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_bulk_action_effects_action_status", table_name="bulk_action_effects")
    op.drop_index("ix_bulk_action_effects_undo_status", table_name="bulk_action_effects")
    op.drop_index("ix_bulk_action_effects_action_id", table_name="bulk_action_effects")
    op.drop_table("bulk_action_effects")

    op.drop_index("ix_bulk_actions_user_undo_expiry", table_name="bulk_actions")
    op.drop_index("ix_bulk_actions_user_created", table_name="bulk_actions")
    op.drop_index("ix_bulk_actions_undo_expires_at", table_name="bulk_actions")
    op.drop_index("ix_bulk_actions_created_at", table_name="bulk_actions")
    op.drop_index("ix_bulk_actions_status", table_name="bulk_actions")
    op.drop_index("ix_bulk_actions_user_id", table_name="bulk_actions")
    op.drop_table("bulk_actions")

    op.drop_constraint("ck_job_tracks_version_positive", "job_tracks", type_="check")
    op.drop_column("job_tracks", "version")
    op.drop_constraint("ck_csv_rows_version_positive", "csv_rows", type_="check")
    op.drop_column("csv_rows", "version")
