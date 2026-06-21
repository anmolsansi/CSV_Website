"""Add new CSV columns for full field coverage

Revision ID: 002
Revises: 001
Create Date: 2026-06-20
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    new_columns = [
        "application_url", "application_dedupe_key",
        "is_usa_role", "location_country", "location_city", "location_state",
        "location_raw_extracted", "location_confidence", "location_source",
        "jd_quality_status", "jd_quality_reasons",
        "source_file",
        "work_model_extracted",
        "salary_min_extracted", "salary_max_extracted", "salary_currency_extracted",
        "posted_status_extracted", "posted_value_extracted",
        "posted_source_extracted", "posted_age_days_extracted",
        "sponsorship_status_extracted",
        "positive_sponsorship_matches_extracted",
        "negative_sponsorship_matches_extracted",
        "positive_sponsorship_evidence_extracted",
        "negative_sponsorship_evidence_extracted",
        "clearance_or_citizenship_extracted",
        "clearance_or_citizenship_evidence_extracted",
        "education_requirement_extracted", "employment_type_extracted",
        "resume_score", "fit_category",
        "score_confidence", "role_family", "seniority_level", "required_years_min",
        "core_languages_extracted", "core_frameworks_extracted",
        "core_cloud_devops_extracted", "database_requirements_extracted",
        "ai_ml_requirements_extracted",
        "matched_resume_skills", "missing_or_weaker_skills", "score_reason",
        "closed_or_unusable_jd", "closed_or_unusable_reason",
    ]
    for col in new_columns:
        op.add_column("csv_rows", sa.Column(col, sa.Text(), nullable=True))


def downgrade() -> None:
    new_columns = [
        "closed_or_unusable_reason", "closed_or_unusable_jd",
        "score_reason", "missing_or_weaker_skills", "matched_resume_skills",
        "ai_ml_requirements_extracted", "database_requirements_extracted",
        "core_cloud_devops_extracted", "core_frameworks_extracted",
        "core_languages_extracted",
        "required_years_min", "seniority_level", "role_family",
        "score_confidence", "fit_category", "resume_score",
        "employment_type_extracted", "education_requirement_extracted",
        "clearance_or_citizenship_evidence_extracted",
        "clearance_or_citizenship_extracted",
        "negative_sponsorship_evidence_extracted",
        "positive_sponsorship_evidence_extracted",
        "negative_sponsorship_matches_extracted",
        "positive_sponsorship_matches_extracted",
        "sponsorship_status_extracted",
        "posted_age_days_extracted", "posted_source_extracted",
        "posted_value_extracted", "posted_status_extracted",
        "salary_currency_extracted", "salary_max_extracted", "salary_min_extracted",
        "work_model_extracted",
        "source_file",
        "jd_quality_reasons", "jd_quality_status",
        "location_source", "location_confidence", "location_raw_extracted",
        "location_state", "location_city", "location_country", "is_usa_role",
        "application_dedupe_key", "application_url",
    ]
    for col in new_columns:
        op.drop_column("csv_rows", col)
