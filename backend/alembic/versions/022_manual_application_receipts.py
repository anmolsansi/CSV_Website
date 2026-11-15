"""Add owner-scoped operational replay receipts for manual application records.

Revision ID: 022
Revises: 021

This additive change does not modify or backfill any historical JobTrack.
Downgrade drops receipts and must not be performed on live accounts.
"""
from alembic import op
import sqlalchemy as sa

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "manual_application_receipts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("request_key", sa.String(length=36), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("response_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(),
            nullable=False, server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "user_id", "request_key", name="uq_manual_application_receipts_user_key"
        ),
    )
    op.create_index(
        "ix_manual_application_receipts_user_created",
        "manual_application_receipts", ["user_id", "created_at"],
    )
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        op.execute(sa.text(
            'ALTER TABLE public."manual_application_receipts" ENABLE ROW LEVEL SECURITY'
        ))
        op.execute(sa.text(
            'REVOKE ALL PRIVILEGES ON TABLE public."manual_application_receipts" FROM PUBLIC'
        ))
        exposed_roles = {
            row[0] for row in connection.execute(sa.text(
                "SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')"
            ))
        }
        for role in exposed_roles:
            op.execute(sa.text(
                f'REVOKE ALL PRIVILEGES ON TABLE public."manual_application_receipts" FROM "{role}"'
            ))


def downgrade() -> None:
    # Destructive downgrade only for disposable/empty databases.
    op.drop_index(
        "ix_manual_application_receipts_user_created",
        table_name="manual_application_receipts",
    )
    op.drop_table("manual_application_receipts")
