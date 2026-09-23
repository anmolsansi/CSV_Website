from __future__ import annotations

from typing import Any

from .models import CSV_COLUMNS


MAX_BULK_TARGETS = 500
MAX_BULK_SNAPSHOT_BYTES = 1024 * 1024
UNDO_WINDOW_MINUTES = 10
BULK_ACTION_METADATA_DAYS = 30

BULK_ACTION_KINDS = frozenset({"archive_rows", "update_rows", "update_tracks"})
BULK_ENTITY_TYPES = frozenset({"csv_row", "job_track"})

# Before-images are intentionally narrow. Identity, owner, timestamps unrelated
# to the requested mutation, secrets, uploaded bytes, and whole-row dumps are
# never copied into the undo journal.
CSV_ROW_UNDO_FIELDS = frozenset(
    set(CSV_COLUMNS)
    | {
        "archived",
        "archived_at",
        "is_duplicate",
        "duplicate_of_id",
    }
)
JOB_TRACK_UNDO_FIELDS = frozenset(
    {
        "company",
        "title",
        "ats_group",
        "search_bucket",
        "resume_match_score",
        "status",
        "opened_at",
        "applied_at",
        "follow_up_at",
        "notes",
        "session_id",
        "open_count",
        "last_opened_at",
    }
)
UNDO_FIELD_ALLOWLISTS = {
    "csv_row": CSV_ROW_UNDO_FIELDS,
    "job_track": JOB_TRACK_UNDO_FIELDS,
}


class UndoContractError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 422,
        field: str = "__root__",
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.field = field
        self.context = context or {}

    def as_detail(self) -> dict[str, Any]:
        detail = {
            "code": self.code,
            "fields": [{"field": self.field, "message": self.message}],
        }
        detail.update(self.context)
        return detail
