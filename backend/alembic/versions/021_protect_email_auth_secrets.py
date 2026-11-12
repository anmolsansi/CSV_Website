"""Lock down password credentials and one-time tokens from public Data APIs.

Revision ID: 021
Revises: 020

PostgreSQL only: enabling RLS and revoking API-client grants is non-destructive.
The backend must use a trusted owner/service database role with privileges.
Downgrade deliberately leaves protections in place.
"""
from alembic import op
import sqlalchemy as sa

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None

_PRIVATE_TABLES = (
    "password_credentials",
    "email_action_tokens",
    "email_auth_rate_limits",
)


def upgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name != "postgresql":
        return

    roles = {
        str(row[0])
        for row in connection.execute(
            sa.text(
                "SELECT rolname FROM pg_roles "
                "WHERE rolname IN ('anon', 'authenticated')"
            )
        )
    }
    for table in _PRIVATE_TABLES:
        # No policies are created: neither anon nor authenticated may use
        # the Data API to read even hashed secrets or pending action tokens.
        op.execute(sa.text(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'REVOKE ALL PRIVILEGES ON TABLE public."{table}" FROM PUBLIC'))
        for role in roles:
            op.execute(
                sa.text(f'REVOKE ALL PRIVILEGES ON TABLE public."{table}" FROM "{role}"')
            )


def downgrade() -> None:
    # Never re-expose secret material on rollback. Additive auth tables remain.
    pass
