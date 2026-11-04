"""Add account-owned external job visits and browser apply idempotency receipts.

Revision ID: 019
Revises: 018

No imported URLs, existing application state or historical records are backfilled.
Downgrade drops newly added tables and MUST NOT be run on live data containing
visits. Old application code can keep both additive tables during a rollback.
"""
from alembic import op
import sqlalchemy as sa


revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_visits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("canonical_url_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "first_visited_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "user_id", "canonical_url_hash", name="uq_job_visits_user_hash"
        ),
    )
    op.create_index(
        "ix_job_visits_user_first_visited",
        "job_visits",
        ["user_id", "first_visited_at"],
    )

    op.create_table(
        "browser_apply_receipts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("request_key", sa.String(length=36), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("response_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "user_id", "request_key", name="uq_browser_apply_receipts_user_key"
        ),
    )
    op.create_index(
        "ix_browser_apply_receipts_user_created",
        "browser_apply_receipts",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    # Destructive downgrade is reserved for empty/disposable databases.
    op.drop_index("ix_browser_apply_receipts_user_created", table_name="browser_apply_receipts")
    op.drop_table("browser_apply_receipts")
    op.drop_index("ix_job_visits_user_first_visited", table_name="job_visits")
    op.drop_table("job_visits")
