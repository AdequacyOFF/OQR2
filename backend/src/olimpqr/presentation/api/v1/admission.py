"""Admission API endpoints (Admitter role)."""

from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ....infrastructure.database import get_db
from ....infrastructure.repositories import (
    EntryTokenRepositoryImpl,
    RegistrationRepositoryImpl,
    ParticipantRepositoryImpl,
    CompetitionRepositoryImpl,
    AttemptRepositoryImpl,
    AuditLogRepositoryImpl,
    AnswerSheetRepositoryImpl,
    InstitutionRepositoryImpl,
    DocumentRepositoryImpl,
    RoomRepositoryImpl,
    SeatAssignmentRepositoryImpl,
)
from ....infrastructure.storage import MinIOStorage
from ....infrastructure.pdf import SheetGenerator
from ....domain.services import TokenService
from ....domain.value_objects import UserRole
from ....domain.entities import User
from ....application.use_cases.admission import (
    VerifyEntryQRUseCase,
    ApproveAdmissionUseCase,
)
from ...schemas.admission_schemas import (
    VerifyEntryQRRequest,
    VerifyEntryQRResponse,
    ApproveAdmissionRequest,
    ApproveAdmissionResponse,
)
from ...dependencies import require_role
from ....config import settings

router = APIRouter()


@router.post("/verify", response_model=VerifyEntryQRResponse)
async def verify_entry_qr(
    request_body: VerifyEntryQRRequest,
    current_user: Annotated[User, Depends(require_role(UserRole.ADMITTER, UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Verify an entry QR code scanned by admitter.

    Returns participant and competition info for confirmation.
    Does NOT consume the token — call /approve to do that.
    """
    try:
        use_case = VerifyEntryQRUseCase(
            token_service=TokenService(settings.hmac_secret_key),
            entry_token_repository=EntryTokenRepositoryImpl(db),
            registration_repository=RegistrationRepositoryImpl(db),
            participant_repository=ParticipantRepositoryImpl(db),
            competition_repository=CompetitionRepositoryImpl(db),
            institution_repository=InstitutionRepositoryImpl(db),
            document_repository=DocumentRepositoryImpl(db),
        )
        result = await use_case.execute(request_body.token)

        return VerifyEntryQRResponse(
            registration_id=result.registration_id,
            participant_id=result.participant_id,
            participant_name=result.participant_name,
            participant_school=result.participant_school,
            participant_grade=result.participant_grade,
            competition_name=result.competition_name,
            competition_id=result.competition_id,
            can_proceed=result.can_proceed,
            message=result.message,
            institution_name=result.institution_name,
            institution_location=result.institution_location,
            is_captain=result.is_captain,
            dob=result.dob,
            position=result.position,
            military_rank=result.military_rank,
            passport_series_number=result.passport_series_number,
            passport_issued_by=result.passport_issued_by,
            passport_issued_date=result.passport_issued_date,
            military_booklet_number=result.military_booklet_number,
            military_personal_number=result.military_personal_number,
            has_documents=result.has_documents,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/{registration_id}/approve", response_model=ApproveAdmissionResponse, status_code=status.HTTP_201_CREATED)
async def approve_admission(
    registration_id: UUID,
    request_body: ApproveAdmissionRequest,
    request: Request,
    current_user: Annotated[User, Depends(require_role(UserRole.ADMITTER, UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Approve admission: consume entry token, generate answer sheet PDF.

    This is a one-time operation — the entry token becomes invalid after.
    Returns PDF download URL and sheet token.
    """
    try:
        use_case = ApproveAdmissionUseCase(
            token_service=TokenService(settings.hmac_secret_key),
            entry_token_repository=EntryTokenRepositoryImpl(db),
            registration_repository=RegistrationRepositoryImpl(db),
            competition_repository=CompetitionRepositoryImpl(db),
            attempt_repository=AttemptRepositoryImpl(db),
            audit_log_repository=AuditLogRepositoryImpl(db),
            answer_sheet_repository=AnswerSheetRepositoryImpl(db),
            storage=MinIOStorage(),
            sheet_generator=SheetGenerator(),
            room_repository=RoomRepositoryImpl(db),
            seat_assignment_repository=SeatAssignmentRepositoryImpl(db),
            participant_repository=ParticipantRepositoryImpl(db),
        )
        result = await use_case.execute(
            registration_id=registration_id,
            raw_entry_token=request_body.raw_entry_token,
            admitter_user_id=current_user.id,
            ip_address=request.client.host if request.client else None,
        )

        return ApproveAdmissionResponse(
            attempt_id=result.attempt_id,
            variant_number=result.variant_number,
            pdf_url=result.pdf_url,
            sheet_token=result.sheet_token,
            room_name=result.room_name,
            seat_number=result.seat_number,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/sheets/{attempt_id}/download")
async def download_answer_sheet(
    attempt_id: UUID,
    current_user: Annotated[User, Depends(require_role(UserRole.ADMITTER, UserRole.ADMIN, UserRole.INVIGILATOR))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Download answer sheet PDF by proxying through backend."""
    try:
        attempt_repo = AttemptRepositoryImpl(db)
        attempt = await attempt_repo.get_by_id(attempt_id)

        if not attempt:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Попытка не найдена",
            )

        if not attempt.pdf_file_path:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="PDF файл не найден для этой попытки",
            )

        storage = MinIOStorage()
        pdf_bytes = storage.download_file(
            bucket=settings.minio_bucket_sheets,
            object_name=attempt.pdf_file_path,
        )

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=answer_sheet_{attempt_id}.pdf"
            },
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Не удалось скачать PDF: {str(e)}",
        )
