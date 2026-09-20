"""add durable maintenance status

Revision ID: 007
Revises: 006
Create Date: 2026-09-20

JG-014 stores aggregate maintenance health in the database so API-serving
processes can report the designated worker's state without relying on
process-local memory. The table contains operational aggregates only and no
user-owned data.
"""

from alembic import op
import sqlalchemy as sa


revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "maintenance_status",
        sa.Column("job_name", sa.String(length=100), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("last_attempted_at", sa.DateTime(), nullable=False),
        sa.Column("last_successful_at", sa.DateTime(), nullable=True),
        sa.Column("last_failed_at", sa.DateTime(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("job_name"),
    )


def downgrade() -> None:
    op.drop_table("maintenance_status")
