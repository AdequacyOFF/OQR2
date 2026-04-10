"""Scan-related Pydantic schemas."""

from pydantic import BaseModel, Field
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
    corrected_score: int = Field(..., ge=0, description="Corrected score value")
    attempt_id: Optional[UUID] = Field(None, description="Attempt to link if QR was not detected")


class VerifyScoreResponse(BaseModel):
    """Response after manual score verification."""
    scan_id: UUID
    attempt_id: UUID
    score: int
    verified_by: UUID


class ApplyScoreRequest(BaseModel):
    """Apply score to attempt."""
    score: int = Field(..., ge=0)


class AttemptResponse(BaseModel):
    """Attempt detail."""
    id: UUID
    registration_id: UUID
    variant_number: int
    status: str
    score_total: Optional[int]
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
    competition_id: UUID
    competition_name: str
    is_special: bool
    task_numbers: list[int] = Field(default_factory=list, description="Task numbers for this tour")


class TaskScoreItem(BaseModel):
    """Score for a single task."""
    task_number: int = Field(..., ge=1)
    score: int = Field(..., ge=0)


class QRScoreEntryRequest(BaseModel):
    """Submit per-task scores for a specific tour via QR-identified attempt."""
    attempt_id: UUID
    tour_number: int = Field(..., ge=1)
    task_scores: list[TaskScoreItem] = Field(..., min_length=1)
