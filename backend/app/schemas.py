from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel

from .models import CSV_COLUMNS


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


class JobTrackUpdateIn(BaseModel):
    company: Optional[str] = None
    title: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    applied_at: Optional[str] = None
    follow_up_at: Optional[str] = None
    mark_applied: bool = False


class BulkUpdateIn(BaseModel):
    ids: List[int]
    patch: JobTrackUpdateIn


class BulkFromRowsIn(BaseModel):
    row_ids: List[int]


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
