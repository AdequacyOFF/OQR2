"""Admission-related Pydantic schemas."""

import datetime as dt
from pydantic import BaseModel, Field
from uuid import UUID


class VerifyEntryQRRequest(BaseModel):
    """Request to verify entry QR code."""
    token: str = Field(..., description="Raw token scanned from QR code")


class VerifyEntryQRResponse(BaseModel):
    """Response after verifying entry QR code."""
    registration_id: UUID
    participant_id: UUID | None = None
    participant_name: str
    participant_school: str
    participant_grade: int | None = None
    competition_name: str
    competition_id: UUID
    can_proceed: bool
    message: str
    institution_name: str | None = None
    institution_location: str | None = None
    is_captain: bool = False
    dob: dt.date | None = None
    position: str | None = None
    military_rank: str | None = None
    passport_series_number: str | None = None
    passport_issued_by: str | None = None
    passport_issued_date: dt.date | None = None
    military_booklet_number: str | None = None
    military_personal_number: str | None = None
    has_documents: bool = False

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "registration_id": "123e4567-e89b-12d3-a456-426614174000",
                "participant_name": "Иван Иванов",
                "participant_school": "Школа №1",
                "participant_grade": 10,
                "competition_name": "Олимпиада по математике",
                "competition_id": "123e4567-e89b-12d3-a456-426614174001",
                "can_proceed": True,
                "message": "Participant verified. Proceed with admission.",
                "institution_name": "Школа №1",
                "dob": "2010-05-15",
                "has_documents": True,
            }]
        }
    }


class ApproveAdmissionRequest(BaseModel):
    """Request to approve admission."""
    raw_entry_token: str = Field(..., description="Raw entry token for re-verification")


class ApproveAdmissionResponse(BaseModel):
    """Response after approving admission with answer sheet."""
    attempt_id: UUID
    variant_number: int
    pdf_url: str
    sheet_token: str
    room_name: str | None = None
    seat_number: int | None = None

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "attempt_id": "123e4567-e89b-12d3-a456-426614174000",
                "variant_number": 2,
                "pdf_url": "admission/sheets/123e4567.../download",
                "sheet_token": "abc123...",
                "room_name": "Ауд. 301",
                "seat_number": 5,
            }]
        }
    }
