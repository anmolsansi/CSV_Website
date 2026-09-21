"""persist conservative job identity and company aliases

Revision ID: 009
Revises: 008
Create Date: 2026-09-21

JG-030 adds nullable derived canonical URL fields plus owner-scoped company
aliases. Original CsvRow.url and JobTrack.url remain unchanged and canonical
hash indexes are deliberately non-unique so collision candidates never merge
records automatically.
"""

from alembic import op
import sqlalchemy as sa


revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("csv_rows", sa.Column("canonical_url", sa.Text(), nullable=True))
    op.add_column(
        "csv_rows",
        sa.Column("canonical_url_hash", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_csv_rows_user_canonical_hash",
        "csv_rows",
        ["user_id", "canonical_url_hash"],
        unique=False,
    )

    op.add_column("job_tracks", sa.Column("canonical_url", sa.Text(), nullable=True))
    op.add_column(
        "job_tracks",
        sa.Column("canonical_url_hash", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_job_tracks_user_canonical_hash",
        "job_tracks",
        ["user_id", "canonical_url_hash"],
        unique=False,
    )

    op.create_table(
        "company_aliases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("alias_key", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=320), nullable=False),
        sa.Column("company_key", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "alias_key",
            name="uq_company_alias_user_alias_key",
        ),
    )
    op.create_index(
        "ix_company_aliases_user_id",
        "company_aliases",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_company_aliases_user_company_key",
        "company_aliases",
        ["user_id", "company_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_company_aliases_user_company_key",
        table_name="company_aliases",
    )
    op.drop_index("ix_company_aliases_user_id", table_name="company_aliases")
    op.drop_table("company_aliases")

    op.drop_index(
        "ix_job_tracks_user_canonical_hash",
        table_name="job_tracks",
    )
    op.drop_column("job_tracks", "canonical_url_hash")
    op.drop_column("job_tracks", "canonical_url")

    op.drop_index(
        "ix_csv_rows_user_canonical_hash",
        table_name="csv_rows",
    )
    op.drop_column("csv_rows", "canonical_url_hash")
    op.drop_column("csv_rows", "canonical_url")
