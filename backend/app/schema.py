from sqlalchemy import text

from .database import Base, engine
from .models import CSV_COLUMNS


def _csv_row_text_column_statements() -> list[str]:
    return [
        f'ALTER TABLE csv_rows ADD COLUMN IF NOT EXISTS "{column}" TEXT'
        for column in CSV_COLUMNS
    ]


def _postgres_schema_patch_statements() -> list[str]:
    return [
        # Columns added after the original upload table. create_all() does not
        # alter existing tables, so a reused local pgdata volume can miss these
        # and cause /upload or /rows to return 500.
        'ALTER TABLE csv_rows ADD COLUMN IF NOT EXISTS clicked BOOLEAN NOT NULL DEFAULT FALSE',
        'ALTER TABLE csv_rows ADD COLUMN IF NOT EXISTS clicked_at TIMESTAMP',
        'ALTER TABLE csv_rows ADD COLUMN IF NOT EXISTS archived BOOLEAN NOT NULL DEFAULT FALSE',
        'ALTER TABLE csv_rows ADD COLUMN IF NOT EXISTS is_duplicate BOOLEAN NOT NULL DEFAULT FALSE',
        'ALTER TABLE csv_rows ADD COLUMN IF NOT EXISTS duplicate_of_id INTEGER',
        *_csv_row_text_column_statements(),
        'ALTER TABLE job_tracks ADD COLUMN IF NOT EXISTS csv_row_id INTEGER',
        'ALTER TABLE job_tracks ADD COLUMN IF NOT EXISTS ats_group TEXT',
        'ALTER TABLE job_tracks ADD COLUMN IF NOT EXISTS search_bucket TEXT',
        'ALTER TABLE job_tracks ADD COLUMN IF NOT EXISTS resume_match_score TEXT',
        "ALTER TABLE job_tracks ADD COLUMN IF NOT EXISTS status VARCHAR(50) NOT NULL DEFAULT 'opened'",
        'ALTER TABLE job_tracks ADD COLUMN IF NOT EXISTS opened_at TIMESTAMP',
        'ALTER TABLE job_tracks ADD COLUMN IF NOT EXISTS applied_at TIMESTAMP',
        'ALTER TABLE job_tracks ADD COLUMN IF NOT EXISTS follow_up_at TIMESTAMP',
        'ALTER TABLE job_tracks ADD COLUMN IF NOT EXISTS notes TEXT',
        'ALTER TABLE job_tracks ADD COLUMN IF NOT EXISTS session_id TEXT',
        'ALTER TABLE job_tracks ADD COLUMN IF NOT EXISTS open_count INTEGER NOT NULL DEFAULT 1',
        'ALTER TABLE job_tracks ADD COLUMN IF NOT EXISTS last_opened_at TIMESTAMP',
        'ALTER TABLE job_tracks ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT NOW()',
        'ALTER TABLE job_tracks ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT NOW()',
        'CREATE INDEX IF NOT EXISTS ix_csv_rows_clicked_at ON csv_rows (clicked_at)',
        'CREATE INDEX IF NOT EXISTS ix_csv_rows_archived ON csv_rows (archived)',
        'CREATE INDEX IF NOT EXISTS ix_csv_rows_is_duplicate ON csv_rows (is_duplicate)',
        'CREATE INDEX IF NOT EXISTS ix_csv_rows_duplicate_of_id ON csv_rows (duplicate_of_id)',
        'CREATE INDEX IF NOT EXISTS ix_job_tracks_csv_row_id ON job_tracks (csv_row_id)',
        'CREATE INDEX IF NOT EXISTS ix_job_tracks_status ON job_tracks (status)',
        'CREATE INDEX IF NOT EXISTS ix_job_tracks_opened_at ON job_tracks (opened_at)',
        'CREATE INDEX IF NOT EXISTS ix_job_tracks_applied_at ON job_tracks (applied_at)',
        'CREATE INDEX IF NOT EXISTS ix_job_tracks_follow_up_at ON job_tracks (follow_up_at)',
        'CREATE INDEX IF NOT EXISTS ix_job_tracks_last_opened_at ON job_tracks (last_opened_at)',
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_user_url'
                AND conrelid = 'csv_rows'::regclass
            ) THEN
                ALTER TABLE csv_rows ADD CONSTRAINT uq_user_url UNIQUE (user_id, url);
            END IF;
        END $$
        """,
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_user_url_history'
                AND conrelid = 'url_history'::regclass
            ) THEN
                ALTER TABLE url_history ADD CONSTRAINT uq_user_url_history UNIQUE (user_id, url);
            END IF;
        END $$
        """,
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_user_job_track_url'
                AND conrelid = 'job_tracks'::regclass
            ) THEN
                ALTER TABLE job_tracks ADD CONSTRAINT uq_user_job_track_url UNIQUE (user_id, url);
            END IF;
        END $$
        """,
    ]


def ensure_schema() -> None:
    """Create missing tables and patch reused local Postgres volumes.

    SQLAlchemy create_all() creates missing tables only. It does not add columns
    to tables that already exist, which is common when docker compose reuses the
    named pgdata volume across app updates.
    """
    Base.metadata.create_all(bind=engine)

    if engine.dialect.name != "postgresql":
        return

    with engine.begin() as connection:
        for statement in _postgres_schema_patch_statements():
            connection.execute(text(statement))
