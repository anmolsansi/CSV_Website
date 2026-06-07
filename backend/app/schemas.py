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
    submitted_at: Optional[str] = None
    follow_up_at: Optional[str] = None
    mark_submitted: bool = False


class ColumnPrefOut(BaseModel):
    hidden_columns: List[str]
    column_order: List[str]


class ColumnPrefIn(BaseModel):
    hidden_columns: List[str]
    column_order: List[str] = []


ALL_COLUMNS = CSV_COLUMNS
