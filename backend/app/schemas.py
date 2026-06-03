from datetime import datetime
from typing import List, Optional

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


class ColumnPrefOut(BaseModel):
    hidden_columns: List[str]
    column_order: List[str]


class ColumnPrefIn(BaseModel):
    hidden_columns: List[str]
    column_order: List[str] = []


ALL_COLUMNS = CSV_COLUMNS
