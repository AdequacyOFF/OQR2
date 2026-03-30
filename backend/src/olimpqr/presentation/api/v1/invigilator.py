"""Invigilator API endpoints."""

from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ....infrastructure.database import get_db
from ....infrastructure.repositories import (
    ParticipantEventRepositoryImpl,
    AttemptRepositoryImpl,
    AnswerSheetRepositoryImpl,
)
from ....infrastructure.storage import MinIOStorage
from ....infrastructure.pdf import SheetGenerator
from ....domain.value_objects import UserRole
from ....domain.services import TokenService
from ....domain.entities import User
from ....application.use_cases.invigilator import (
    RecordEventUseCase,
    IssueExtraSheetUseCase,
    GetAttemptEventsUseCase,
)
from ...schemas.invigilator_schemas import (
    RecordEventRequest,
    RecordEventResponse,
    IssueExtraSheetRequest,
    IssueExtraSheetResponse,
    EventItem,
    AttemptEventsResponse,
    ResolveSheetTokenRequest,
    ResolveSheetTokenResponse,
    AttemptSheetItem,
    AttemptSheetsResponse,
    SearchSheetItem,
    SearchSheetsResponse,
    SearchParticipantItem,
    SearchParticipantsResponse,
)
from ...dependencies import require_role
from ....config import settings

router = APIRouter()


@router.post("/events", response_model=RecordEventResponse, status_code=status.HTTP_201_CREATED)
async def record_event(
    request_body: RecordEventRequest,
    current_user: Annotated[User, Depends(require_role(UserRole.INVIGILATOR, UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Record a participant event (invigilator)."""
    try:
        use_case = RecordEventUseCase(
            event_repository=ParticipantEventRepositoryImpl(db),
            attempt_repository=AttemptRepositoryImpl(db),
        )
        result = await use_case.execute(
            attempt_id=request_body.attempt_id,
            event_type=request_body.event_type,
            recorded_by=current_user.id,
            timestamp=request_body.timestamp,
        )
        return RecordEventResponse(
            id=result.id,
            attempt_id=result.attempt_id,
            event_type=result.event_type,
            timestamp=result.timestamp,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/extra-sheet", response_model=IssueExtraSheetResponse, status_code=status.HTTP_201_CREATED)
async def issue_extra_sheet(
    request_body: IssueExtraSheetRequest,
    current_user: Annotated[User, Depends(require_role(UserRole.INVIGILATOR, UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Issue an extra answer sheet for an attempt (invigilator)."""
    try:
        use_case = IssueExtraSheetUseCase(
            answer_sheet_repository=AnswerSheetRepositoryImpl(db),
            attempt_repository=AttemptRepositoryImpl(db),
            token_service=TokenService(settings.hmac_secret_key),
            sheet_generator=SheetGenerator(),
            storage=MinIOStorage(),
        )
        result = await use_case.execute(attempt_id=request_body.attempt_id)
        return IssueExtraSheetResponse(
            answer_sheet_id=result.answer_sheet_id,
            sheet_token=result.sheet_token,
            pdf_url=result.pdf_url,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.get("/attempt/{attempt_id}/events", response_model=AttemptEventsResponse)
async def get_attempt_events(
    attempt_id: UUID,
    current_user: Annotated[User, Depends(require_role(UserRole.INVIGILATOR, UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get all events for an attempt (invigilator)."""
    use_case = GetAttemptEventsUseCase(
        event_repository=ParticipantEventRepositoryImpl(db),
    )
    results = await use_case.execute(attempt_id=attempt_id)
    return AttemptEventsResponse(
        events=[
            EventItem(
                id=e.id,
                attempt_id=e.attempt_id,
                event_type=e.event_type,
                timestamp=e.timestamp,
                recorded_by=e.recorded_by,
            )
            for e in results
        ]
    )


@router.get("/attempt/{attempt_id}/sheets", response_model=AttemptSheetsResponse)
async def get_attempt_sheets(
    attempt_id: UUID,
    current_user: Annotated[User, Depends(require_role(UserRole.INVIGILATOR, UserRole.ADMIN, UserRole.SCANNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get all answer sheets for an attempt."""
    repo = AnswerSheetRepositoryImpl(db)
    sheets = await repo.get_by_attempt(attempt_id)
    return AttemptSheetsResponse(
        sheets=[
            AttemptSheetItem(
                id=s.id,
                kind=s.kind.value,
                created_at=s.created_at,
                pdf_file_path=s.pdf_file_path,
            )
            for s in sheets
        ]
    )


@router.post("/resolve-sheet-token", response_model=ResolveSheetTokenResponse)
async def resolve_sheet_token(
    request_body: ResolveSheetTokenRequest,
    current_user: Annotated[User, Depends(require_role(UserRole.INVIGILATOR, UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Resolve raw sheet token to attempt + participant context."""
    sheet_repo = AnswerSheetRepositoryImpl(db)
    attempt_repo = AttemptRepositoryImpl(db)
    attempt = None
    answer_sheet = None

    # 1) New direct token format for Word templates: attempt:<attempt_id>:...
    if request_body.sheet_token.startswith("attempt:"):
        parts = request_body.sheet_token.split(":")
        if len(parts) >= 2:
            try:
                parsed_attempt_id = UUID(parts[1])
                attempt = await attempt_repo.get_by_id(parsed_attempt_id)
            except ValueError:
                attempt = None

    # 2) Standard hashed token format (legacy + primary/extra sheets).
    if not attempt:
        token_service = TokenService(settings.hmac_secret_key)
        token_hash = token_service.hash_token(request_body.sheet_token).value
        answer_sheet = await sheet_repo.get_by_token_hash(token_hash)
        if answer_sheet:
            attempt = await attempt_repo.get_by_id(answer_sheet.attempt_id)
        else:
            # Backward compatibility with old attempts where token is stored only in attempts.
            attempt = await attempt_repo.get_by_sheet_token_hash(token_hash)

    # For direct attempt:<id> tokens answer_sheet may be absent.
    if answer_sheet and not attempt:
        attempt = await attempt_repo.get_by_id(answer_sheet.attempt_id)
    if not answer_sheet and attempt:
        answer_sheet = await sheet_repo.get_primary_by_attempt(attempt.id)

    if not attempt:
        raise HTTPException(status_code=404, detail="Бланк по этому токену не найден")

    from ....infrastructure.database.models import (
        RegistrationModel,
        ParticipantModel,
        CompetitionModel,
    )

    stmt = (
        select(RegistrationModel)
        .where(RegistrationModel.id == attempt.registration_id)
        .options(
            selectinload(RegistrationModel.participant),
            selectinload(RegistrationModel.competition),
        )
    )
    result = await db.execute(stmt)
    registration = result.scalar_one_or_none()

    if not registration or not registration.participant or not registration.competition:
        raise HTTPException(status_code=404, detail="Не удалось найти контекст участника")

    return ResolveSheetTokenResponse(
        attempt_id=attempt.id,
        answer_sheet_id=answer_sheet.id if answer_sheet else None,
        participant_name=registration.participant.full_name,
        competition_id=registration.competition.id,
        competition_name=registration.competition.name,
    )


@router.get("/search-sheets", response_model=SearchSheetsResponse)
async def search_sheets(
    current_user: Annotated[User, Depends(require_role(UserRole.INVIGILATOR, UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
    q: str = Query(..., min_length=2, description="Participant full name search query"),
    competition_id: UUID | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    """Search answer sheets by participant full name."""
    from ....infrastructure.database.models import (
        AnswerSheetModel,
        AttemptModel,
        RegistrationModel,
        ParticipantModel,
        CompetitionModel,
    )

    stmt = (
        select(
            AnswerSheetModel.id.label("answer_sheet_id"),
            AnswerSheetModel.kind.label("kind"),
            AnswerSheetModel.created_at.label("created_at"),
            AttemptModel.id.label("attempt_id"),
            ParticipantModel.full_name.label("participant_name"),
            CompetitionModel.id.label("competition_id"),
            CompetitionModel.name.label("competition_name"),
        )
        .join(AttemptModel, AnswerSheetModel.attempt_id == AttemptModel.id)
        .join(RegistrationModel, AttemptModel.registration_id == RegistrationModel.id)
        .join(ParticipantModel, RegistrationModel.participant_id == ParticipantModel.id)
        .join(CompetitionModel, RegistrationModel.competition_id == CompetitionModel.id)
        .where(ParticipantModel.full_name.ilike(f"%{q.strip()}%"))
        .order_by(ParticipantModel.full_name.asc(), AnswerSheetModel.created_at.desc())
        .limit(limit)
    )

    if competition_id:
        stmt = stmt.where(CompetitionModel.id == competition_id)

    result = await db.execute(stmt)
    rows = result.all()

    return SearchSheetsResponse(
        items=[
            SearchSheetItem(
                participant_name=row.participant_name,
                competition_id=row.competition_id,
                competition_name=row.competition_name,
                attempt_id=row.attempt_id,
                answer_sheet_id=row.answer_sheet_id,
                kind=row.kind.value if hasattr(row.kind, "value") else str(row.kind),
                created_at=row.created_at,
            )
            for row in rows
        ]
    )


@router.get("/search-participants", response_model=SearchParticipantsResponse)
async def search_participants(
    current_user: Annotated[User, Depends(require_role(UserRole.INVIGILATOR, UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
    q: str = Query(..., min_length=2, description="Participant full name search query"),
    competition_id: UUID | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    """Search participants with attempts for issuing extra sheets."""
    from ....infrastructure.database.models import (
        AttemptModel,
        CompetitionModel,
        ParticipantModel,
        RegistrationModel,
        SeatAssignmentModel,
        RoomModel,
    )

    stmt = (
        select(
            ParticipantModel.id.label("participant_id"),
            ParticipantModel.full_name.label("participant_name"),
            CompetitionModel.id.label("competition_id"),
            CompetitionModel.name.label("competition_name"),
            AttemptModel.id.label("attempt_id"),
            RoomModel.name.label("room_name"),
            SeatAssignmentModel.seat_number.label("seat_number"),
        )
        .join(RegistrationModel, RegistrationModel.participant_id == ParticipantModel.id)
        .join(CompetitionModel, CompetitionModel.id == RegistrationModel.competition_id)
        .join(AttemptModel, AttemptModel.registration_id == RegistrationModel.id)
        .outerjoin(SeatAssignmentModel, SeatAssignmentModel.registration_id == RegistrationModel.id)
        .outerjoin(RoomModel, RoomModel.id == SeatAssignmentModel.room_id)
        .where(ParticipantModel.full_name.ilike(f"%{q.strip()}%"))
        .order_by(ParticipantModel.full_name.asc(), CompetitionModel.date.desc())
        .limit(limit)
    )

    if competition_id:
        stmt = stmt.where(CompetitionModel.id == competition_id)

    result = await db.execute(stmt)
    rows = result.all()

    sheet_repo = AnswerSheetRepositoryImpl(db)
    items: list[SearchParticipantItem] = []
    for row in rows:
        primary_sheet = await sheet_repo.get_primary_by_attempt(row.attempt_id)
        items.append(
            SearchParticipantItem(
                participant_id=row.participant_id,
                participant_name=row.participant_name,
                competition_id=row.competition_id,
                competition_name=row.competition_name,
                attempt_id=row.attempt_id,
                room_name=row.room_name,
                seat_number=row.seat_number,
                primary_answer_sheet_id=primary_sheet.id if primary_sheet else None,
            )
        )

    return SearchParticipantsResponse(items=items)


@router.get("/answer-sheet/{answer_sheet_id}/download")
async def download_answer_sheet(
    answer_sheet_id: UUID,
    current_user: Annotated[User, Depends(require_role(UserRole.INVIGILATOR, UserRole.ADMIN, UserRole.SCANNER))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Download answer sheet PDF file by answer_sheet_id."""
    repo = AnswerSheetRepositoryImpl(db)
    sheet = await repo.get_by_id(answer_sheet_id)
    if not sheet:
        raise HTTPException(status_code=404, detail="Бланк не найден")
    if not sheet.pdf_file_path:
        raise HTTPException(status_code=404, detail="PDF файл для бланка не найден")

    storage = MinIOStorage()
    try:
        pdf_bytes = storage.download_file(
            bucket=settings.minio_bucket_sheets,
            object_name=sheet.pdf_file_path,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=404, detail=f"Не удалось скачать PDF: {exc}")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="answer_sheet_{answer_sheet_id}.pdf"',
        },
    )
