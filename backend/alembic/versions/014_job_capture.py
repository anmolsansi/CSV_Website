"""add manual job capture provenance and replay identity

Revision ID: 014
Revises: 013
Create Date: 2026-09-22

JG-045 adds nullable capture provenance to existing CSV rows plus durable
idempotency and fixed-window rate-limit state. Legacy rows remain unchanged.
"""

from alembic import op
import sqlalchemy as sa


revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("csv_rows", sa.Column("capture_source", sa.String(length=16), nullable=True))
    op.add_column("csv_rows", sa.Column("captured_at", sa.DateTime(), nullable=True))
    op.add_column("csv_rows", sa.Column("capture_notes", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_csv_rows_capture_source",
        "csv_rows",
        "capture_source IS NULL OR capture_source IN ('manual', 'bookmarklet')",
    )
    op.create_check_constraint(
        "ck_csv_rows_capture_notes_length",
        "csv_rows",
        "capture_notes IS NULL OR length(capture_notes) <= 20000",
    )
    op.create_index("ix_csv_rows_captured_at", "csv_rows", ["captured_at"], unique=False)

    op.create_table(
        "capture_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("request_key", sa.String(length=36), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("row_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["row_id"], ["csv_rows.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "request_key", name="uq_capture_request_user_key"
        ),
    )
    op.create_index("ix_capture_requests_user_id", "capture_requests", ["user_id"], unique=False)
    op.create_index("ix_capture_requests_row_id", "capture_requests", ["row_id"], unique=False)
    op.create_index("ix_capture_requests_created_at", "capture_requests", ["created_at"], unique=False)

    op.create_table(
        "request_window_counters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("window_start", sa.DateTime(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("count >= 0", name="ck_request_window_counters_count"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "scope", "window_start",
            name="uq_request_window_counter_user_scope_window",
        ),
    )
    op.create_index(
        "ix_request_window_counters_user_id",
        "request_window_counters",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_request_window_counters_window_start",
        "request_window_counters",
        ["window_start"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_request_window_counters_window_start",
        table_name="request_window_counters",
    )
    op.drop_index(
        "ix_request_window_counters_user_id",
        table_name="request_window_counters",
    )
    op.drop_table("request_window_counters")

    op.drop_index("ix_capture_requests_created_at", table_name="capture_requests")
    op.drop_index("ix_capture_requests_row_id", table_name="capture_requests")
    op.drop_index("ix_capture_requests_user_id", table_name="capture_requests")
    op.drop_table("capture_requests")

    op.drop_index("ix_csv_rows_captured_at", table_name="csv_rows")
    op.drop_constraint("ck_csv_rows_capture_notes_length", "csv_rows", type_="check")
    op.drop_constraint("ck_csv_rows_capture_source", "csv_rows", type_="check")
    op.drop_column("csv_rows", "capture_notes")
    op.drop_column("csv_rows", "captured_at")
    op.drop_column("csv_rows", "capture_source")
