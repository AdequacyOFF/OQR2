"""Competition-related Pydantic schemas."""

import datetime as dt
from typing import List
from pydantic import BaseModel, Field
from uuid import UUID

from ...domain.value_objects import CompetitionStatus
from ...domain.entities import Competition


class CreateCompetitionRequest(BaseModel):
    """Request schema for creating a competition."""
    name: str = Field(..., min_length=3, description="Competition name")
    date: dt.date = Field(..., description="Competition date")
    registration_start: dt.datetime = Field(..., description="Registration start datetime")
    registration_end: dt.datetime = Field(..., description="Registration end datetime")
    variants_count: int = Field(..., ge=1, description="Number of test variants")
    max_score: int = Field(..., ge=1, description="Maximum possible score")
    is_special: bool = Field(False, description="Special olympiad mode")
    special_tours_count: int | None = Field(None, ge=1, description="Number of tours for special olympiad")
    special_tour_modes: list[str] | None = Field(
        None,
        description="Tour modes list. Allowed: individual, individual_captains, team",
    )
    special_settings: dict | None = Field(None, description="Additional special olympiad settings")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "Математическая олимпиада 2026",
                    "date": "2026-03-15",
                    "registration_start": "2026-02-01T00:00:00",
                    "registration_end": "2026-03-10T23:59:59",
                    "variants_count": 4,
                    "max_score": 100
                }
            ]
        }
    }


class UpdateCompetitionRequest(BaseModel):
    """Request schema for updating a competition. All fields are optional."""
    name: str | None = Field(None, min_length=3, description="Competition name")
    date: dt.date | None = Field(None, description="Competition date")
    registration_start: dt.datetime | None = Field(None, description="Registration start datetime")
    registration_end: dt.datetime | None = Field(None, description="Registration end datetime")
    variants_count: int | None = Field(None, ge=1, description="Number of test variants")
    max_score: int | None = Field(None, ge=1, description="Maximum possible score")
    is_special: bool | None = Field(None, description="Special olympiad mode")
    special_tours_count: int | None = Field(None, ge=1, description="Number of tours for special olympiad")
    special_tour_modes: list[str] | None = Field(
        None,
        description="Tour modes list. Allowed: individual, individual_captains, team",
    )
    special_settings: dict | None = Field(None, description="Additional special olympiad settings")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "Математическая олимпиада 2026 (обновлено)",
                    "max_score": 120
                }
            ]
        }
    }


class CompetitionResponse(BaseModel):
    """Response schema for competition data."""
    id: UUID
    name: str
    date: dt.date
    registration_start: dt.datetime
    registration_end: dt.datetime
    variants_count: int
    max_score: int
    is_special: bool
    special_tours_count: int | None = None
    special_tour_modes: list[str] | None = None
    special_settings: dict | None = None
    status: CompetitionStatus
    created_by: UUID
    created_at: dt.datetime
    updated_at: dt.datetime

    @classmethod
    def from_entity(cls, entity: Competition) -> "CompetitionResponse":
        """Create response from Competition entity."""
        return cls(
            id=entity.id,
            name=entity.name,
            date=entity.date,
            registration_start=entity.registration_start,
            registration_end=entity.registration_end,
            variants_count=entity.variants_count,
            max_score=entity.max_score,
            is_special=entity.is_special,
            special_tours_count=entity.special_tours_count,
            special_tour_modes=entity.special_tour_modes,
            special_settings=entity.special_settings,
            status=entity.status,
            created_by=entity.created_by,
            created_at=entity.created_at,
            updated_at=entity.updated_at
        )

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "examples": [
                {
                    "id": "123e4567-e89b-12d3-a456-426614174000",
                    "name": "Математическая олимпиада 2026",
                    "date": "2026-03-15",
                    "registration_start": "2026-02-01T00:00:00",
                    "registration_end": "2026-03-10T23:59:59",
                    "variants_count": 4,
                    "max_score": 100,
                    "status": "draft",
                    "created_by": "123e4567-e89b-12d3-a456-426614174001",
                    "created_at": "2026-02-01T10:00:00",
                    "updated_at": "2026-02-01T10:00:00"
                }
            ]
        }
    }


class CompetitionListResponse(BaseModel):
    """Response schema for list of competitions."""
    competitions: List[CompetitionResponse]
    total: int

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "competitions": [
                        {
                            "id": "123e4567-e89b-12d3-a456-426614174000",
                            "name": "Математическая олимпиада 2026",
                            "date": "2026-03-15",
                            "registration_start": "2026-02-01T00:00:00",
                            "registration_end": "2026-03-10T23:59:59",
                            "variants_count": 4,
                            "max_score": 100,
                            "status": "registration_open",
                            "created_by": "123e4567-e89b-12d3-a456-426614174001",
                            "created_at": "2026-02-01T10:00:00",
                            "updated_at": "2026-02-05T10:00:00"
                        }
                    ],
                    "total": 1
                }
            ]
        }
    }
