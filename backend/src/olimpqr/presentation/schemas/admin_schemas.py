"""Admin-related Pydantic schemas."""

import datetime as dt
from pydantic import BaseModel, EmailStr, Field
from uuid import UUID
from datetime import datetime
from typing import Any, Dict, Optional

from ...domain.value_objects import UserRole


class CreateStaffRequest(BaseModel):
    """Create a staff user (admitter / scanner / invigilator / admin / participant)."""
    email: EmailStr
    password: str = Field(..., min_length=8)
    role: UserRole
    full_name: Optional[str] = None
    school: Optional[str] = None
    grade: Optional[int] = Field(None, ge=1, le=12)
    institution_id: Optional[UUID] = None
    institution_location: Optional[str] = None
    is_captain: bool = False
    dob: Optional[dt.date] = None


class UpdateUserRequest(BaseModel):
    """Update user fields."""
    is_active: Optional[bool] = None
    role: Optional[UserRole] = None


class UserListResponse(BaseModel):
    """Paginated list of users."""
    items: list["AdminUserResponse"]
    total: int


class AdminUserResponse(BaseModel):
    """User response for admin panel."""
    id: UUID
    email: str
    role: UserRole
    is_active: bool
    created_at: datetime


class AuditLogEntry(BaseModel):
    """Single audit log entry."""
    id: UUID
    entity_type: str
    entity_id: UUID
    action: str
    user_id: Optional[UUID]
    ip_address: Optional[str]
    details: Dict[str, Any]
    timestamp: datetime

    model_config = {"from_attributes": True}


class AuditLogListResponse(BaseModel):
    """Paginated list of audit log entries."""
    items: list[AuditLogEntry]
    total: int


class StatisticsResponse(BaseModel):
    """System statistics for admin dashboard."""
    total_competitions: int
    total_users: int
    total_scans: int
    total_registrations: int
    total_participants: int


class AdminRegisterRequest(BaseModel):
    """Admin registers a participant for a competition."""
    participant_id: UUID
    competition_id: UUID


class AdminRegisterResponse(BaseModel):
    """Response after admin registration."""
    registration_id: UUID
    entry_token: str


class ReplaceParticipantRequest(BaseModel):
    """Replace old participant in a registration with a new one."""
    new_participant_id: UUID


class ReplaceParticipantResponse(BaseModel):
    """Response after participant replacement."""
    new_registration_id: UUID
    entry_token: str
    seat_transferred: bool
    room_name: Optional[str] = None
    seat_number: Optional[int] = None
    variant_number: Optional[int] = None
    warning: Optional[str] = None


class AdminRegistrationItem(BaseModel):
    """Single registration item for admin list."""
    registration_id: UUID
    participant_id: UUID
    participant_name: str
    participant_school: str
    participant_institution_location: Optional[str] = None
    participant_is_captain: bool = False
    institution_name: Optional[str] = None
    entry_token: Optional[str] = None
    status: str
    seat_room_name: Optional[str] = None
    seat_number: Optional[int] = None
    variant_number: Optional[int] = None


class AdminRegistrationListResponse(BaseModel):
    """Paginated list of registrations for a competition."""
    items: list[AdminRegistrationItem]
    total: int


class TourProgress(BaseModel):
    """Score progress for a single tour."""
    tour_number: int
    task_scores: Optional[Dict[str, int]] = None
    tour_total: Optional[int] = None
    tour_time: Optional[str] = None


class TourTimeItem(BaseModel):
    """Start/finish times for a single tour of a competition."""
    tour_number: int
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_minutes: Optional[int] = None


class SetTourTimeRequest(BaseModel):
    """Request body for setting tour start/finish times."""
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class TourConfigItem(BaseModel):
    """Configuration for a single tour (mode and task numbers)."""
    tour_number: int
    mode: str  # "individual" | "individual_captains" | "team"
    task_numbers: list[int] = []
    captains_task: bool = False
    captains_task_numbers: list[int] = []


class ScoringProgressItem(BaseModel):
    """Single participant scoring status for admin/scanner progress table."""
    registration_id: UUID
    participant_id: UUID
    participant_name: str
    participant_school: str
    variant_number: Optional[int] = None
    attempt_id: Optional[UUID] = None
    attempt_status: Optional[str] = None
    tours: list["TourProgress"] = []
    score_total: Optional[int] = None
    is_captain: bool = False


class ScoringProgressResponse(BaseModel):
    """Full competition scoring progress for admin/scanner table."""
    competition_id: UUID
    competition_name: str
    is_special: bool
    tours_count: int
    items: list["ScoringProgressItem"]
    total: int
    tour_times: list[TourTimeItem] = []
    tour_configs: list[TourConfigItem] = []


class AssignStaffRequest(BaseModel):
    """Assign a staff user to a competition."""
    user_id: UUID


class CompetitionStaffItem(BaseModel):
    """Staff member assigned to a competition."""
    user_id: UUID
    email: str
    role: UserRole
    assigned_at: datetime


class CompetitionStaffList(BaseModel):
    """List of staff assigned to a competition."""
    items: list[CompetitionStaffItem]
    total: int
