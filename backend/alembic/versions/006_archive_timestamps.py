"""Add archive timestamp and account retention preference.

Revision ID: 006
Revises: 005
Create Date: 2026-09-20

JG-012 is intentionally additive. Existing archived rows retain archived_at=NULL
because their archive time is unknown, and existing users retain
retention_days=NULL so automatic retention stays disabled.
"""
from alembic import op
import sqlalchemy as sa


revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("retention_days", sa.Integer(), nullable=True))

    with op.batch_alter_table("csv_rows") as batch_op:
        batch_op.add_column(sa.Column("archived_at", sa.DateTime(), nullable=True))

    op.create_index(
        "ix_csv_rows_archived_at",
        "csv_rows",
        ["archived_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_csv_rows_archived_at", table_name="csv_rows")

    with op.batch_alter_table("csv_rows") as batch_op:
        batch_op.drop_column("archived_at")

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("retention_days")
