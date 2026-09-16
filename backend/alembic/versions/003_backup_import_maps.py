"""Add backup import identity mappings.

Revision ID: 003
Revises: 002
Create Date: 2026-09-16
"""
from alembic import op
import sqlalchemy as sa


revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


IDENTITY_INDEX = "uq_backup_import_map_identity"


def upgrade() -> None:
    op.create_table(
        "backup_import_maps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("backup_id", sa.String(length=36), nullable=False),
        sa.Column("section", sa.String(length=50), nullable=False),
        sa.Column("backup_ref", sa.String(length=255), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        IDENTITY_INDEX,
        "backup_import_maps",
        ["user_id", "backup_id", "section", "backup_ref"],
        unique=True,
    )
    op.create_index(
        "ix_backup_import_maps_user_id",
        "backup_import_maps",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_backup_import_maps_user_id", table_name="backup_import_maps")
    op.drop_index(IDENTITY_INDEX, table_name="backup_import_maps")
    op.drop_table("backup_import_maps")
