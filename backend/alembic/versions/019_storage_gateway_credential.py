"""Add private credential used by the zero-dollar storage gateway.

Revision ID: 019_storage_gateway_credential
Revises: 018_bulk_undo_foundation
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import inspect


revision = "019_storage_gateway_credential"
down_revision = "018_bulk_undo_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "storage_gateway_credentials" not in inspector.get_table_names():
        op.execute(
            """
            CREATE TABLE storage_gateway_credentials (
                id INTEGER PRIMARY KEY,
                token VARCHAR(128) NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT ck_storage_gateway_singleton CHECK (id = 1)
            )
            """
        )

    if bind.dialect.name == "postgresql":
        op.execute(
            "INSERT INTO storage_gateway_credentials (id, token) "
            "VALUES (1, gen_random_uuid()::text || gen_random_uuid()::text) "
            "ON CONFLICT (id) DO NOTHING"
        )
        op.execute("ALTER TABLE storage_gateway_credentials ENABLE ROW LEVEL SECURITY")
        op.execute("REVOKE ALL ON TABLE storage_gateway_credentials FROM anon, authenticated")
    else:
        # SQLite CI/development does not expose a Data API. The credential still
        # exists so migration parity and gateway-token lookup can be tested.
        import secrets

        token = secrets.token_hex(32)
        bind.exec_driver_sql(
            "INSERT OR IGNORE INTO storage_gateway_credentials (id, token) VALUES (1, ?)",
            (token,),
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS storage_gateway_credentials")
