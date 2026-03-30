"""Competition-related DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date
from uuid import UUID

from ...domain.value_objects import CompetitionStatus


@dataclass
class CreateCompetitionDTO:
    """DTO for creating a competition."""
    name: str
    date: date
    registration_start: datetime
    registration_end: datetime
    variants_count: int
    max_score: int
    is_special: bool = False
    special_tours_count: int | None = None
    special_tour_modes: list[str] | None = None
    special_settings: dict | None = None


@dataclass
class UpdateCompetitionDTO:
    """DTO for updating a competition. All fields are optional."""
    name: str | None = None
    date: date | None = None
    registration_start: datetime | None = None
    registration_end: datetime | None = None
    variants_count: int | None = None
    max_score: int | None = None
    is_special: bool | None = None
    special_tours_count: int | None = None
    special_tour_modes: list[str] | None = None
    special_settings: dict | None = None


@dataclass
class CompetitionDTO:
    """DTO for competition data."""
    id: UUID
    name: str
    date: date
    registration_start: datetime
    registration_end: datetime
    variants_count: int
    max_score: int
    is_special: bool
    special_tours_count: int | None
    special_tour_modes: list[str] | None
    special_settings: dict | None
    status: CompetitionStatus
    created_by: UUID
    created_at: datetime
    updated_at: datetime
