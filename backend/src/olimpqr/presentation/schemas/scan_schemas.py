"""Scan-related Pydantic schemas."""

import datetime as dt
from pydantic import BaseModel, Field, field_validator
from uuid import UUID
from datetime import datetime
from typing import Optional


class ScanUploadResponse(BaseModel):
    """Response after uploading a scan."""
    scan_id: UUID
    task_id: str = Field(..., description="Celery task ID for tracking OCR progress")


class ScanResponse(BaseModel):
    """Full scan detail."""
    id: UUID
    attempt_id: Optional[UUID]
    answer_sheet_id: Optional[UUID] = None
    file_path: str
    ocr_score: Optional[int]
    ocr_confidence: Optional[float]
    ocr_raw_text: Optional[str]
    verified_by: Optional[UUID]
    uploaded_by: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ScanListResponse(BaseModel):
    """List of scans."""
    items: list[ScanResponse]
    total: int


class VerifyScoreRequest(BaseModel):
    """Manual score verification / correction."""
    corrected_score: float = Field(..., ge=0, description="Corrected score value")
    attempt_id: Optional[UUID] = Field(None, description="Attempt to link if QR was not detected")


class VerifyScoreResponse(BaseModel):
    """Response after manual score verification."""
    scan_id: UUID
    attempt_id: UUID
    score: float
    verified_by: UUID


class ApplyScoreRequest(BaseModel):
    """Apply score to attempt."""
    score: float = Field(..., ge=0)


class AttemptResponse(BaseModel):
    """Attempt detail."""
    id: UUID
    registration_id: UUID
    variant_number: int
    status: str
    score_total: Optional[float]
    confidence: Optional[float]
    pdf_file_path: Optional[str]
    task_scores: Optional[dict] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ResolveQRRequest(BaseModel):
    """Resolve QR token to attempt context for manual scoring."""
    sheet_token: str = Field(..., description="Raw QR token from A3-cover or answer sheet")


class ResolveQRResponse(BaseModel):
    """Resolved QR context for manual score entry."""
    attempt_id: UUID
    tour_number: Optional[int] = Field(None, description="Tour number extracted from QR (if A3-cover)")
    participant_name: str
    participant_school: Optional[str] = None
    institution_name: Optional[str] = None
    institution_location: Optional[str] = None
    is_captain: bool = False
    dob: Optional[dt.date] = None
    position: Optional[str] = None
    military_rank: Optional[str] = None
    passport_series_number: Optional[str] = None
    passport_issued_by: Optional[str] = None
    passport_issued_date: Optional[dt.date] = None
    military_booklet_number: Optional[str] = None
    military_personal_number: Optional[str] = None
    competition_id: UUID
    competition_name: str
    is_special: bool
    task_numbers: list[int] = Field(default_factory=list, description="Task numbers for this tour")
    tour_mode: Optional[str] = Field(None, description="Tour mode: individual / individual_captains / team")
    is_captains_task: bool = Field(False, description="True when QR encodes a captains task blank")
    cap_task_number: Optional[int] = Field(None, description="Captain task number (when is_captains_task=True)")
    captains_task_numbers: list[int] = Field(default_factory=list, description="Captain task numbers for this tour (when tour_mode=individual_captains)")


class TaskScoreItem(BaseModel):
    """Score for a single task."""
    task_number: int = Field(..., ge=1)
    score: float = Field(..., ge=0)


class QRScoreEntryRequest(BaseModel):
    """Submit per-task scores for a specific tour via QR-identified attempt."""
    attempt_id: UUID
    tour_number: int = Field(..., ge=1)
    task_scores: list[TaskScoreItem] = Field(..., min_length=1)
    tour_time: str | None = Field(None, description="Per-participant tour time in h.m.s or hh.mm.ss format")
    is_captains_task: bool = Field(False, description="When True, scores are stored as captain task bonus (excluded from personal total)")

    @field_validator("tour_time", mode="before")
    @classmethod
    def normalize_tour_time(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None
        parts = s.split(".")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            raise ValueError("tour_time must be in h.m.s or hh.mm.ss format")
        h, m, sec = (int(p) for p in parts)
        if not (0 <= h <= 99 and 0 <= m <= 59 and 0 <= sec <= 59):
            raise ValueError("tour_time has invalid time values")
        return f"{h:02d}.{m:02d}.{sec:02d}"
