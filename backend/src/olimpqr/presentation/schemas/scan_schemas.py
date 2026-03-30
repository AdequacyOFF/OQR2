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
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
