"""add private import previews and reusable mappings

Revision ID: 017
Revises: 016
Create Date: 2026-09-23

F9 keeps uploaded import plans owner-scoped and transient while retaining only
saved mappings and bounded commit replay results as durable metadata.
"""

from alembic import op
import sqlalchemy as sa


revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "import_previews",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("source_filename", sa.String(length=255), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("headers_json", sa.JSON(), nullable=False),
        sa.Column("header_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("mapping_json", sa.JSON(), nullable=False),
        sa.Column("normalized_rows_json", sa.JSON(), nullable=True),
        sa.Column("rejected_rows_json", sa.JSON(), nullable=True),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("destination_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ready"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("commit_key", sa.String(length=36), nullable=True),
        sa.Column("commit_payload_hash", sa.String(length=64), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("committed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('ready', 'committing', 'committed', 'failed')",
            name="ck_import_previews_status",
        ),
        sa.CheckConstraint("version > 0", name="ck_import_previews_version"),
        sa.CheckConstraint("length(source_sha256) = 64", name="ck_import_previews_source_sha256_length"),
        sa.CheckConstraint("length(header_fingerprint) = 64", name="ck_import_previews_header_fingerprint_length"),
        sa.CheckConstraint("length(destination_fingerprint) = 64", name="ck_import_previews_destination_fingerprint_length"),
        sa.CheckConstraint("commit_key IS NULL OR length(commit_key) = 36", name="ck_import_previews_commit_key_length"),
        sa.CheckConstraint("commit_payload_hash IS NULL OR length(commit_payload_hash) = 64", name="ck_import_previews_commit_hash_length"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "commit_key", name="uq_import_previews_user_commit_key"),
    )
    op.create_index("ix_import_previews_user_id", "import_previews", ["user_id"], unique=False)
    op.create_index("ix_import_previews_expires_at", "import_previews", ["expires_at"], unique=False)
    op.create_index("ix_import_previews_status", "import_previews", ["status"], unique=False)
    op.create_index("ix_import_previews_committed_at", "import_previews", ["committed_at"], unique=False)
    op.create_index("ix_import_previews_user_expires", "import_previews", ["user_id", "expires_at"], unique=False)
    op.create_index("ix_import_previews_user_status", "import_previews", ["user_id", "status"], unique=False)
    op.create_index("ix_import_previews_user_committed", "import_previews", ["user_id", "committed_at"], unique=False)

    op.create_table(
        "import_mappings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("header_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("mapping_json", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("length(name) BETWEEN 1 AND 100", name="ck_import_mappings_name_length"),
        sa.CheckConstraint("length(header_fingerprint) = 64", name="ck_import_mappings_header_fingerprint_length"),
        sa.CheckConstraint("version > 0", name="ck_import_mappings_version"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name", name="uq_import_mapping_user_name"),
    )
    op.create_index("ix_import_mappings_user_id", "import_mappings", ["user_id"], unique=False)
    op.create_index("ix_import_mappings_header_fingerprint", "import_mappings", ["header_fingerprint"], unique=False)
    op.create_index("ix_import_mappings_user_fingerprint", "import_mappings", ["user_id", "header_fingerprint"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_import_mappings_user_fingerprint", table_name="import_mappings")
    op.drop_index("ix_import_mappings_header_fingerprint", table_name="import_mappings")
    op.drop_index("ix_import_mappings_user_id", table_name="import_mappings")
    op.drop_table("import_mappings")

    op.drop_index("ix_import_previews_user_committed", table_name="import_previews")
    op.drop_index("ix_import_previews_user_status", table_name="import_previews")
    op.drop_index("ix_import_previews_user_expires", table_name="import_previews")
    op.drop_index("ix_import_previews_committed_at", table_name="import_previews")
    op.drop_index("ix_import_previews_status", table_name="import_previews")
    op.drop_index("ix_import_previews_expires_at", table_name="import_previews")
    op.drop_index("ix_import_previews_user_id", table_name="import_previews")
    op.drop_table("import_previews")
