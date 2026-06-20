"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-06-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(320), unique=True, nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        "oauth_identities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("provider_id", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("provider", "provider_id", name="uq_provider_identity"),
    )

    op.create_table(
        "url_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "url", name="uq_user_url_history"),
    )

    op.create_table(
        "csv_rows",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("upload_batch_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("clicked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("clicked_at", sa.DateTime(), nullable=True, index=True),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.text("false"), index=True),
        sa.Column("is_duplicate", sa.Boolean(), nullable=False, server_default=sa.text("false"), index=True),
        sa.Column("duplicate_of_id", sa.Integer(), sa.ForeignKey("csv_rows.id"), nullable=True, index=True),
        sa.Column("ats_group", sa.Text()),
        sa.Column("location_group", sa.Text()),
        sa.Column("search_bucket", sa.Text()),
        sa.Column("title", sa.Text()),
        sa.Column("title_match_status", sa.Text()),
        sa.Column("title_reject_reason", sa.Text()),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("display_domain", sa.Text()),
        sa.Column("company_guess", sa.Text()),
        sa.Column("job_id_guess", sa.Text()),
        sa.Column("canonical_company_job_key", sa.Text()),
        sa.Column("page_number", sa.Text()),
        sa.Column("decision", sa.Text()),
        sa.Column("rejection_reasons", sa.Text()),
        sa.Column("posted_status", sa.Text()),
        sa.Column("posted_value", sa.Text()),
        sa.Column("posted_source", sa.Text()),
        sa.Column("posted_age_days", sa.Text()),
        sa.Column("location_status", sa.Text()),
        sa.Column("location_evidence", sa.Text()),
        sa.Column("sponsorship_status", sa.Text()),
        sa.Column("positive_sponsorship_matches", sa.Text()),
        sa.Column("negative_sponsorship_matches", sa.Text()),
        sa.Column("sponsorship_evidence_snippet", sa.Text()),
        sa.Column("positive_sponsorship_evidence_snippet", sa.Text()),
        sa.Column("clearance_matches", sa.Text()),
        sa.Column("clearance_evidence_snippet", sa.Text()),
        sa.Column("jd_text_length", sa.Text()),
        sa.Column("jd_text", sa.Text()),
        sa.Column("extraction_method", sa.Text()),
        sa.Column("retry_attempted", sa.Text()),
        sa.Column("error", sa.Text()),
        sa.Column("resume_match_score", sa.Text()),
        sa.UniqueConstraint("user_id", "url", name="uq_user_url"),
    )

    op.create_table(
        "job_tracks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("csv_row_id", sa.Integer(), sa.ForeignKey("csv_rows.id"), nullable=True, index=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("company", sa.Text()),
        sa.Column("title", sa.Text()),
        sa.Column("ats_group", sa.Text()),
        sa.Column("search_bucket", sa.Text()),
        sa.Column("resume_match_score", sa.Text()),
        sa.Column("status", sa.String(50), nullable=False, server_default="opened", index=True),
        sa.Column("opened_at", sa.DateTime(), nullable=True, index=True),
        sa.Column("applied_at", sa.DateTime(), nullable=True, index=True),
        sa.Column("follow_up_at", sa.DateTime(), nullable=True, index=True),
        sa.Column("notes", sa.Text()),
        sa.Column("session_id", sa.Text()),
        sa.Column("open_count", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("last_opened_at", sa.DateTime(), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "url", name="uq_user_job_track_url"),
    )

    op.create_table(
        "saved_views",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("view_type", sa.String(50), nullable=False, server_default="job_links"),
        sa.Column("filters", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "name", "view_type", name="uq_user_saved_view"),
    )

    op.create_table(
        "search_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.Text()),
    )

    op.create_table(
        "column_preferences",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("hidden_columns", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("column_order", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("search_sessions.id"), nullable=True, index=True),
        sa.Column("event_type", sa.String(100), nullable=False, index=True),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), index=True),
    )

    op.create_table(
        "applypilot_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("search_sessions.id"), nullable=True),
        sa.Column("name", sa.String(200)),
        sa.Column("payload_json", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="downloaded"),
        sa.Column("job_count", sa.Integer(), server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_table(
        "user_goals",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("open_per_day", sa.Integer(), server_default=sa.text("30")),
        sa.Column("apply_per_day", sa.Integer(), server_default=sa.text("10")),
        sa.Column("followup_per_day", sa.Integer(), server_default=sa.text("5")),
        sa.Column("applypilot_per_day", sa.Integer(), server_default=sa.text("5")),
    )


def downgrade() -> None:
    op.drop_table("user_goals")
    op.drop_table("applypilot_batches")
    op.drop_table("audit_events")
    op.drop_table("column_preferences")
    op.drop_table("search_sessions")
    op.drop_table("saved_views")
    op.drop_table("job_tracks")
    op.drop_table("csv_rows")
    op.drop_table("url_history")
    op.drop_table("oauth_identities")
    op.drop_table("users")
