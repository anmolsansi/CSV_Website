"""Add account timezone preference.

Revision ID: 005
Revises: 004
Create Date: 2026-09-20
"""
from alembic import op
import sqlalchemy as sa


revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The temporary server default makes the additive NOT NULL column safe for
    # existing accounts. New accounts receive the UTC default from the ORM.
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "timezone",
                sa.String(length=64),
                nullable=False,
                server_default="UTC",
            )
        )
    # Keep this separate from the add-column batch. SQLite batch recreation
    # needs the temporary default while copying pre-existing rows.
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("timezone", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("timezone")
