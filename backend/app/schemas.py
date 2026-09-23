from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, StrictInt

from .models import CSV_COLUMNS


JobTrackStatus = Literal[
    "opened",
    "applied",
    "follow_up",
    "interview",
    "rejected",
    "offer",
    "not_applying",
]


class UserOut(BaseModel):
    id: int
    email: str

    class Config:
        from_attributes = True


class RowOut(BaseModel):
    id: int
    clicked: bool
    clicked_at: Optional[datetime]
    data: dict


class RowDeleteIn(BaseModel):
    row_ids: List[int]
    mode: Literal["archive", "delete"] = "delete"
    request_key: Optional[str] = None
    expected_versions: Dict[int, StrictInt] = Field(default_factory=dict)
    confirmation_token: Optional[str] = None

    def model_post_init(self, __context) -> None:
        if (
            self.mode == "delete"
            and self.confirmation_token is None
            and not self.expected_versions
            and self.request_key is None
        ):
            self.__pydantic_fields_set__.discard("mode")


class RowRestoreIn(BaseModel):
    row_ids: List[int]
    expected_versions: Dict[int, StrictInt]
    mode: Literal["all_or_nothing", "restore_unchanged"] = "all_or_nothing"


class PermanentDeletePreviewIn(BaseModel):
    row_ids: List[int]
    expected_versions: Dict[int, StrictInt] = Field(default_factory=dict)


class JobTrackUpdateIn(BaseModel):
    company: Optional[str] = None
    title: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    applied_at: Optional[str] = None
    follow_up_at: Optional[str] = None
    mark_applied: bool = False

    def model_post_init(self, __context) -> None:
        if self.status == "applied" and "applied_at" not in self.__pydantic_fields_set__ and not self.mark_applied:
            self.mark_applied = True
            self.__pydantic_fields_set__.add("mark_applied")


class BulkUpdateIn(BaseModel):
    ids: List[int]
    patch: JobTrackUpdateIn


class BulkFromRowsIn(BaseModel):
    row_ids: List[int]
    status: Optional[JobTrackStatus] = None
    capture_notes_mode: Literal["preserve", "append"] = "preserve"


class SavedViewIn(BaseModel):
    name: str
    view_type: str = "job_links"
    filters: dict


class SessionIn(BaseModel):
    name: str = "Job search session"
    notes: Optional[str] = None


class SessionUpdateIn(BaseModel):
    notes: Optional[str] = None
    end: bool = False
    submitted_at: Optional[str] = None
    follow_up_at: Optional[str] = None
    mark_submitted: bool = False


class ColumnPrefOut(BaseModel):
    hidden_columns: List[str]
    column_order: List[str]


class ColumnPrefIn(BaseModel):
    hidden_columns: List[str]
    column_order: List[str] = []


class ApplyPilotResultIn(BaseModel):
    url: str
    submitted: bool = False
    questions_extracted: Optional[bool] = False
    manual_review_needed: Optional[bool] = False
    application_url: Optional[str] = None
    error: Optional[str] = None
    screenshot_path: Optional[str] = None
    submitted_at: Optional[str] = None


class ShareViewOut(BaseModel):
    share_url: str
    expires_at: str


ALL_COLUMNS = CSV_COLUMNS