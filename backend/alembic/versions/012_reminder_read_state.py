"""add persisted in-app reminder read state

Revision ID: 012
Revises: 011
Create Date: 2026-09-22

CCR-F4-READ-1: the frozen F4 contract requires in-app unread state to be
independently persisted. Revision 011 did not contain a read marker, so JG-039
could not truthfully implement that behavior without an additive schema repair.

The column is nullable and backward-compatible. NULL means unread/not marked
read. Email deliveries leave it NULL. Rollback removes only the read marker and
does not alter delivery status or acceptance history.
"""

from alembic import op
import sqlalchemy as sa


revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "reminder_deliveries",
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("reminder_deliveries", "read_at")
