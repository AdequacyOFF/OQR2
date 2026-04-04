"""Invigilator-related Pydantic schemas."""

from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime

from ...domain.value_objects import EventType


class RecordEventRequest(BaseModel):
    """Request to record a participant event."""
    attempt_id: UUID
    event_type: EventType
    timestamp: datetime | None = None


class RecordEventResponse(BaseModel):
    """Response after recording event."""
    id: UUID
    attempt_id: UUID
    event_type: str
    timestamp: datetime


class IssueExtraSheetRequest(BaseModel):
    """Request to issue an extra answer sheet."""
    attempt_id: UUID


class IssueExtraSheetResponse(BaseModel):
    """Response after issuing extra sheet."""
    answer_sheet_id: UUID
    sheet_token: str
    pdf_url: str


class IssueSpecialExtraSheetRequest(BaseModel):
    """Request to issue special olympiad extra sheet as DOCX."""
    attempt_id: UUID
    tour_number: int = Field(..., ge=1)
    task_number: int = Field(..., ge=1)


class EventItem(BaseModel):
    """Single event item."""
    id: UUID
    attempt_id: UUID
    event_type: str
    timestamp: datetime
    recorded_by: UUID


class AttemptEventsResponse(BaseModel):
    """Response with attempt events."""
    events: list[EventItem]


class ResolveSheetTokenRequest(BaseModel):
    """Resolve a scanned sheet token to attempt context."""
    sheet_token: str = Field(..., min_length=8)


class SpecialTourOption(BaseModel):
    """Tour config used by invigilator UI for special olympiad."""
    tour_number: int
    mode: str
    task_numbers: list[int]


class ResolveSheetTokenResponse(BaseModel):
    """Resolved context for a scanned sheet token."""
    attempt_id: UUID
    answer_sheet_id: UUID | None = None
    participant_name: str
    competition_id: UUID
    competition_name: str
    is_special_competition: bool = False
    special_tours: list["SpecialTourOption"] | None = None


class AttemptSheetItem(BaseModel):
    """Single answer sheet item."""
    id: UUID
    kind: str
    created_at: datetime
    pdf_file_path: str | None = None


class AttemptSheetsResponse(BaseModel):
    """All answer sheets attached to one attempt."""
    sheets: list[AttemptSheetItem]


class SearchSheetItem(BaseModel):
    """Search result for sheets by participant name."""
    participant_name: str
    competition_id: UUID
    competition_name: str
    attempt_id: UUID
    answer_sheet_id: UUID
    kind: str
    created_at: datetime


class SearchSheetsResponse(BaseModel):
    """Search response for sheet lookup."""
    items: list[SearchSheetItem]


class SearchParticipantItem(BaseModel):
    """Search result for participant with attempt context."""
    participant_id: UUID
    participant_name: str
    competition_id: UUID
    competition_name: str
    attempt_id: UUID
    room_name: str | None = None
    seat_number: int | None = None
    primary_answer_sheet_id: UUID | None = None


class SearchParticipantsResponse(BaseModel):
    """Search response for participant lookup in invigilator module."""
    items: list[SearchParticipantItem]
