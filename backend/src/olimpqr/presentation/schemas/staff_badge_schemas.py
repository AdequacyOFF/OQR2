"""Staff badge Pydantic schemas."""

from uuid import UUID
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class StaffBadgeItem(BaseModel):
    id: UUID
    competition_id: Optional[UUID] = None
    full_name: str
    role: str
    institution: Optional[str] = None
    has_photo: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class StaffBadgeListResponse(BaseModel):
    items: list[StaffBadgeItem]
    total: int


class StaffBadgeCreateRequest(BaseModel):
    competition_id: Optional[UUID] = None
    full_name: str = Field(..., min_length=2)
    role: str = Field(..., min_length=2)
    institution: Optional[str] = None


class StaffBadgeImportItem(BaseModel):
    full_name: str
    role: str
    institution: Optional[str] = None


class StaffBadgeImportRequest(BaseModel):
    competition_id: Optional[UUID] = None
    items: list[StaffBadgeImportItem] = Field(..., min_length=1)


class StaffBadgeGenerateRequest(BaseModel):
    competition_id: Optional[UUID] = None
    badge_ids: Optional[list[UUID]] = Field(None, description="Specific badge IDs; all if omitted")
