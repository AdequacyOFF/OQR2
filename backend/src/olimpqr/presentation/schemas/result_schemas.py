"""Public result schemas."""

from pydantic import BaseModel
from uuid import UUID
from typing import Optional


class ResultEntry(BaseModel):
    """Single result entry (anonymised by default)."""
    rank: int
    participant_name: str
    school: str
    grade: int | None = None
    score: float
    max_score: float


class CompetitionResultsResponse(BaseModel):
    """Published results for a competition."""
    competition_id: UUID
    competition_name: str
    results: list[ResultEntry]
    total_participants: int
