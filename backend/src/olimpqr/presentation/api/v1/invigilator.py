"""Invigilator API endpoints."""

from typing import Annotated, Any
from uuid import UUID, uuid4
import re
from urllib.parse import parse_qs, unquote, urlparse
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
from ....infrastructure.docx import WordTemplateGenerator
from ....domain.value_objects import UserRole, SheetKind
from ....domain.services import TokenService
from ....domain.entities import User, AnswerSheet
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
    IssueSpecialExtraSheetRequest,
    EventItem,
    AttemptEventsResponse,
    ResolveSheetTokenRequest,
    ResolveSheetTokenResponse,
    SpecialTourOption,
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
ATTEMPT_TOKEN_PATTERN = re.compile(
    r"attempt[:/](?P<attempt_id>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})",
    re.IGNORECASE,
)
ATTEMPT_TOKEN_LEGACY_PATTERN = re.compile(
    r"^(?P<attempt_id>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})(?=[:/]|$)",
    re.IGNORECASE,
)
MODE_LABELS = {
    "individual": "Индивидуальный",
    "individual_captains": "Индивидуальный (капитаны отдельно)",
    "team": "Командный",
}


def _normalize_sheet_token(raw_token: str) -> str:
    """Normalize scanned token from laser/camera scanners."""
    token = (raw_token or "").strip().strip('"').strip("'")
    token = token.replace("\ufeff", "").replace("\u200b", "").strip()
    if not token:
        return ""

    parsed = urlparse(token)
    if parsed.scheme in {"http", "https"}:
        query = parse_qs(parsed.query)
        for key in ("sheet_token", "token", "qr", "data"):
            values = query.get(key)
            if values and values[0].strip():
                return unquote(values[0]).strip()

        path_value = unquote(parsed.path).strip()
        if "attempt:" in path_value.lower() or "attempt/" in path_value.lower():
            return path_value.strip("/")

        tail = unquote(parsed.path.rsplit("/", 1)[-1]).strip()
        if tail:
            return tail

    return unquote(token).strip()


def _extract_attempt_id_from_token(token: str) -> UUID | None:
    """Try to extract attempt UUID from direct special-blank QR payloads."""
    match = ATTEMPT_TOKEN_PATTERN.search(token)
    if not match:
        # Backward compatibility:
        # old special templates encoded token as "<attempt_id>:tour:...".
        match = ATTEMPT_TOKEN_LEGACY_PATTERN.search(token)
    if not match:
        return None
    try:
        return UUID(match.group("attempt_id"))
    except ValueError:
        return None


def _extract_special_tours(competition) -> list[dict[str, Any]]:
    """Extract normalized special tours config from competition settings."""
    if not competition or not getattr(competition, "is_special", False):
        return []

    allowed_modes = {"individual", "individual_captains", "team"}
    settings_payload = competition.special_settings or {}
    raw_tours = settings_payload.get("tours")

    normalized: list[dict[str, Any]] = []
    if isinstance(raw_tours, list):
        for idx, item in enumerate(raw_tours, start=1):
            if not isinstance(item, dict):
                continue
            tour_number = int(item.get("tour_number") or idx)
            mode = str(item.get("mode") or "individual").strip()
            if mode not in allowed_modes:
                mode = "individual"
            task_numbers = item.get("task_numbers") or item.get("tasks") or [1]
            tasks: list[int] = []
            for task in task_numbers:
                try:
                    val = int(task)
                    if val > 0:
                        tasks.append(val)
                except Exception:  # noqa: BLE001
                    continue
            if not tasks:
                tasks = [1]
            normalized.append(
                {
                    "tour_number": tour_number,
                    "mode": mode,
                    "task_numbers": sorted(set(tasks)),
                }
            )

    if normalized:
        return normalized

    tours_count = int(getattr(competition, "special_tours_count", 0) or 1)
    modes = getattr(competition, "special_tour_modes", None) or []
    fallback: list[dict[str, Any]] = []
    for idx in range(tours_count):
        mode = str(modes[idx]) if idx < len(modes) else "individual"
        if mode not in allowed_modes:
            mode = "individual"
        fallback.append(
            {
                "tour_number": idx + 1,
                "mode": mode,
                "task_numbers": [1],
            }
        )
    return fallback


def _resolve_mode_label(mode: str) -> str:
    return MODE_LABELS.get(mode, mode)


def _compute_next_special_extra_index(
    sheets: list[AnswerSheet],
    attempt_id: UUID,
    tour_number: int,
    task_number: int,
) -> int:
    """Compute next extra-sheet index for one attempt/tour/task."""
    prefix = f"sheets/special_extra/{attempt_id}/tour_{tour_number}/task_{task_number}/extra_"
    max_index = 0

    for sheet in sheets:
        if sheet.kind != SheetKind.EXTRA or not sheet.pdf_file_path:
            continue
        path = sheet.pdf_file_path
        if not path.startswith(prefix):
            continue
        suffix = path[len(prefix):]
        raw_number = suffix.split("_", 1)[0]
        try:
            number = int(raw_number)
        except ValueError:
            continue
        max_index = max(max_index, number)

    return max_index + 1


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


@router.post("/special-extra-sheet/download")
async def issue_special_extra_sheet_and_download(
    request_body: IssueSpecialExtraSheetRequest,
    current_user: Annotated[User, Depends(require_role(UserRole.INVIGILATOR, UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Issue special olympiad extra sheet and download as DOCX."""
    from ....infrastructure.database.models import RegistrationModel

    attempt_repo = AttemptRepositoryImpl(db)
    sheet_repo = AnswerSheetRepositoryImpl(db)
    attempt = await attempt_repo.get_by_id(request_body.attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="Попытка не найдена")

    stmt = (
        select(RegistrationModel)
        .where(RegistrationModel.id == attempt.registration_id)
        .options(selectinload(RegistrationModel.competition))
    )
    result = await db.execute(stmt)
    registration = result.scalar_one_or_none()
    competition = registration.competition if registration else None
    if not competition:
        raise HTTPException(status_code=404, detail="Не найдено соревнование для попытки")
    if not competition.is_special:
        raise HTTPException(status_code=400, detail="Этот формат доп.бланка доступен только для особой олимпиады")

    tours = _extract_special_tours(competition)
    selected_tour = next(
        (item for item in tours if int(item.get("tour_number", 0)) == request_body.tour_number),
        None,
    )
    if not selected_tour:
        raise HTTPException(status_code=400, detail="Указанный тур не найден в настройках олимпиады")

    allowed_tasks = selected_tour.get("task_numbers", [])
    if request_body.task_number not in allowed_tasks:
        raise HTTPException(status_code=400, detail="Указанное задание не найдено в выбранном туре")

    existing_sheets = await sheet_repo.get_by_attempt(attempt.id)
    extra_index = _compute_next_special_extra_index(
        existing_sheets,
        attempt_id=attempt.id,
        tour_number=request_body.tour_number,
        task_number=request_body.task_number,
    )

    token_service = TokenService(settings.hmac_secret_key)
    sheet_token = token_service.generate_token(size_bytes=settings.qr_token_size_bytes)

    answer_sheet = AnswerSheet(
        id=uuid4(),
        attempt_id=attempt.id,
        sheet_token_hash=sheet_token.hash,
        kind=SheetKind.EXTRA,
    )

    object_name = (
        f"sheets/special_extra/{attempt.id}/tour_{request_body.tour_number}/"
        f"task_{request_body.task_number}/extra_{extra_index}_{answer_sheet.id}.docx"
    )

    mode_label = _resolve_mode_label(str(selected_tour.get("mode") or "individual"))
    tour_task_value = f"{request_body.tour_number}/{request_body.task_number}/{extra_index}"
    word_generator = WordTemplateGenerator()
    docx_bytes = word_generator.generate_answer_blank(
        qr_payload=sheet_token.raw,
        tour_number=request_body.tour_number,
        task_number=request_body.task_number,
        mode=mode_label,
        tour_task=tour_task_value,
    )

    storage = MinIOStorage()
    storage.upload_file(
        bucket=settings.minio_bucket_sheets,
        object_name=object_name,
        data=docx_bytes,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    answer_sheet.pdf_file_path = object_name
    await sheet_repo.create(answer_sheet)

    filename = f"extra_t{request_body.tour_number}_task{request_body.task_number}_{extra_index}.docx"
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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
    normalized_token = _normalize_sheet_token(request_body.sheet_token)
    if not normalized_token:
        raise HTTPException(status_code=400, detail="Пустой QR-токен")

    sheet_repo = AnswerSheetRepositoryImpl(db)
    attempt_repo = AttemptRepositoryImpl(db)
    attempt = None
    answer_sheet = None

    # 1) Direct token format for Word templates: attempt:<attempt_id>:...
    # Also accepts wrapped forms (URL/path/extra prefix chars).
    direct_attempt_id = _extract_attempt_id_from_token(normalized_token)
    if direct_attempt_id:
        attempt = await attempt_repo.get_by_id(direct_attempt_id)

    # 2) Standard hashed token format (legacy + primary/extra sheets).
    if not attempt:
        token_service = TokenService(settings.hmac_secret_key)
        token_hash = token_service.hash_token(normalized_token).value
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

    is_special_competition = bool(getattr(registration.competition, "is_special", False))
    special_tours_payload = None
    if is_special_competition:
        special_tours_payload = [
            SpecialTourOption(
                tour_number=int(item["tour_number"]),
                mode=str(item["mode"]),
                task_numbers=[int(v) for v in item["task_numbers"]],
            )
            for item in _extract_special_tours(registration.competition)
        ]

    participant = registration.participant
    institution_name = None
    if participant.institution_id:
        from ....infrastructure.database.models import InstitutionModel

        inst_result = await db.execute(
            select(InstitutionModel).where(InstitutionModel.id == participant.institution_id)
        )
        inst_row = inst_result.scalar_one_or_none()
        if inst_row:
            institution_name = inst_row.name

    return ResolveSheetTokenResponse(
        attempt_id=attempt.id,
        answer_sheet_id=answer_sheet.id if answer_sheet else None,
        participant_name=participant.full_name,
        participant_school=participant.school,
        institution_name=institution_name,
        institution_location=participant.institution_location,
        is_captain=participant.is_captain,
        dob=participant.dob,
        position=participant.position,
        military_rank=participant.military_rank,
        passport_series_number=participant.passport_series_number,
        passport_issued_by=participant.passport_issued_by,
        passport_issued_date=participant.passport_issued_date,
        military_booklet_number=participant.military_booklet_number,
        military_personal_number=participant.military_personal_number,
        competition_id=registration.competition.id,
        competition_name=registration.competition.name,
        is_special_competition=is_special_competition,
        special_tours=special_tours_payload,
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
    """Download answer sheet file by answer_sheet_id."""
    repo = AnswerSheetRepositoryImpl(db)
    sheet = await repo.get_by_id(answer_sheet_id)
    if not sheet:
        raise HTTPException(status_code=404, detail="Бланк не найден")
    if not sheet.pdf_file_path:
        raise HTTPException(status_code=404, detail="PDF файл для бланка не найден")

    storage = MinIOStorage()
    try:
        file_bytes = storage.download_file(
            bucket=settings.minio_bucket_sheets,
            object_name=sheet.pdf_file_path,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=404, detail=f"Не удалось скачать PDF: {exc}")

    if sheet.pdf_file_path and sheet.pdf_file_path.lower().endswith(".docx"):
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        filename = f"answer_sheet_{answer_sheet_id}.docx"
    else:
        media_type = "application/pdf"
        filename = f"answer_sheet_{answer_sheet_id}.pdf"

    return Response(
        content=file_bytes,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
