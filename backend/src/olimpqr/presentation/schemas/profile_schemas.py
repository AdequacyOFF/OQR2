"""Profile-related Pydantic schemas."""

import datetime as dt
from typing import Optional
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime


class ParticipantProfileResponse(BaseModel):
    """Response with participant profile info."""
    id: UUID
    user_id: UUID
    full_name: str
    school: str
    grade: Optional[int] = None
    institution_id: Optional[UUID] = None
    institution_location: Optional[str] = None
    is_captain: bool = False
    dob: Optional[dt.date] = None
    created_at: datetime
    updated_at: datetime

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "user_id": "123e4567-e89b-12d3-a456-426614174001",
                "full_name": "Иванов Иван Иванович",
                "school": "Школа №1",
                "grade": 10,
                "created_at": "2026-02-12T12:00:00",
                "updated_at": "2026-02-13T14:30:00"
            }]
        }
    }


class UpdateProfileRequest(BaseModel):
    """Request to update participant profile."""
    full_name: str = Field(min_length=2, description="ФИО (минимум 2 символа)")
    school: str = Field(min_length=2, description="Название школы (минимум 2 символа)")
    grade: Optional[int] = Field(None, ge=1, le=12, description="Класс (1-12)")
    institution_location: Optional[str] = Field(None, min_length=2, description="Город/филиал учебного учреждения")
    is_captain: Optional[bool] = Field(None, description="Является ли участник капитаном")
    dob: Optional[dt.date] = Field(None, description="Дата рождения")

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "full_name": "Иванов Иван Иванович",
                "school": "Школа №1",
                "grade": 10
            }]
        }
    }
