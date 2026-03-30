"""Competition API endpoints."""

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from ....infrastructure.database import get_db
from ....infrastructure.repositories import CompetitionRepositoryImpl
from ....application.use_cases.competitions import (
    CreateCompetitionUseCase,
    GetCompetitionUseCase,
    ListCompetitionsUseCase,
    UpdateCompetitionUseCase,
    DeleteCompetitionUseCase,
    ChangeCompetitionStatusUseCase
)
from ....application.dto.competition_dto import CreateCompetitionDTO, UpdateCompetitionDTO
from ...schemas.competition_schemas import (
    CreateCompetitionRequest,
    UpdateCompetitionRequest,
    CompetitionResponse,
    CompetitionListResponse
)
from ...dependencies import require_role, get_current_active_user
from ....domain.entities import User
from ....domain.value_objects import UserRole, CompetitionStatus


router = APIRouter()


@router.post("", response_model=CompetitionResponse, status_code=status.HTTP_201_CREATED)
async def create_competition(
    request: CreateCompetitionRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(UserRole.ADMIN))]
):
    """Create a new competition.

    **Admin only**

    - **name**: Competition name (min 3 characters)
    - **date**: Competition date
    - **registration_start**: When registration opens
    - **registration_end**: When registration closes
    - **variants_count**: Number of test variants (min 1)
    - **max_score**: Maximum possible score (min 1)

    Competition is created with status DRAFT.
    """
    try:
        # Create repository and use case
        repository = CompetitionRepositoryImpl(db)
        use_case = CreateCompetitionUseCase(repository)

        # Create DTO
        dto = CreateCompetitionDTO(
            name=request.name,
            date=request.date,
            registration_start=request.registration_start,
            registration_end=request.registration_end,
            variants_count=request.variants_count,
            max_score=request.max_score,
            is_special=request.is_special,
            special_tours_count=request.special_tours_count,
            special_tour_modes=request.special_tour_modes,
            special_settings=request.special_settings,
        )

        # Execute use case
        competition = await use_case.execute(dto, current_user.id)

        # Return response
        return CompetitionResponse.from_entity(competition)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("", response_model=CompetitionListResponse)
async def list_competitions(
    db: Annotated[AsyncSession, Depends(get_db)],
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    status_filter: CompetitionStatus | None = Query(None, description="Filter by status")
):
    """List competitions with optional status filter.

    **Public endpoint**

    Query parameters:
    - **skip**: Number of records to skip (default: 0)
    - **limit**: Maximum number of records (default: 100, max: 1000)
    - **status_filter**: Optional status filter (draft, registration_open, in_progress, checking, published)
    """
    try:
        # Create repository and use case
        repository = CompetitionRepositoryImpl(db)
        use_case = ListCompetitionsUseCase(repository)

        # Execute use case
        competitions = await use_case.execute(
            skip=skip,
            limit=limit,
            status_filter=status_filter
        )

        # Return response
        return CompetitionListResponse(
            competitions=[CompetitionResponse.from_entity(c) for c in competitions],
            total=len(competitions)
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/{competition_id}", response_model=CompetitionResponse)
async def get_competition(
    competition_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Get competition by ID.

    **Public endpoint**
    """
    try:
        # Create repository and use case
        repository = CompetitionRepositoryImpl(db)
        use_case = GetCompetitionUseCase(repository)

        # Execute use case
        competition = await use_case.execute(competition_id)

        if not competition:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Олимпиада с id {competition_id} не найдена"
            )

        # Return response
        return CompetitionResponse.from_entity(competition)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.put("/{competition_id}", response_model=CompetitionResponse)
async def update_competition(
    competition_id: UUID,
    request: UpdateCompetitionRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(UserRole.ADMIN))]
):
    """Update competition.

    **Admin only**

    All fields are optional. Only provided fields will be updated.
    """
    try:
        # Create repository and use case
        repository = CompetitionRepositoryImpl(db)
        use_case = UpdateCompetitionUseCase(repository)

        # Create DTO
        dto = UpdateCompetitionDTO(
            name=request.name,
            date=request.date,
            registration_start=request.registration_start,
            registration_end=request.registration_end,
            variants_count=request.variants_count,
            max_score=request.max_score,
            is_special=request.is_special,
            special_tours_count=request.special_tours_count,
            special_tour_modes=request.special_tour_modes,
            special_settings=request.special_settings,
        )

        # Execute use case
        competition = await use_case.execute(competition_id, dto)

        # Return response
        return CompetitionResponse.from_entity(competition)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{competition_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_competition(
    competition_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(UserRole.ADMIN))]
):
    """Delete competition.

    **Admin only**
    """
    try:
        # Create repository and use case
        repository = CompetitionRepositoryImpl(db)
        use_case = DeleteCompetitionUseCase(repository)

        # Execute use case
        deleted = await use_case.execute(competition_id)

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Олимпиада с id {competition_id} не найдена"
            )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{competition_id}/open-registration", response_model=CompetitionResponse)
async def open_registration(
    competition_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(UserRole.ADMIN))]
):
    """Open registration for competition.

    **Admin only**

    Transitions competition from DRAFT to REGISTRATION_OPEN status.
    """
    try:
        # Create repository and use case
        repository = CompetitionRepositoryImpl(db)
        use_case = ChangeCompetitionStatusUseCase(repository)

        # Execute use case
        competition = await use_case.execute(competition_id, CompetitionStatus.REGISTRATION_OPEN)

        # Return response
        return CompetitionResponse.from_entity(competition)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{competition_id}/start", response_model=CompetitionResponse)
async def start_competition(
    competition_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(UserRole.ADMIN))]
):
    """Start competition (begin admission).

    **Admin only**

    Transitions competition from REGISTRATION_OPEN to IN_PROGRESS status.
    """
    try:
        # Create repository and use case
        repository = CompetitionRepositoryImpl(db)
        use_case = ChangeCompetitionStatusUseCase(repository)

        # Execute use case
        competition = await use_case.execute(competition_id, CompetitionStatus.IN_PROGRESS)

        # Return response
        return CompetitionResponse.from_entity(competition)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{competition_id}/start-checking", response_model=CompetitionResponse)
async def start_checking(
    competition_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(UserRole.ADMIN))]
):
    """Start checking phase (all submissions in, begin scoring).

    **Admin only**

    Transitions competition from IN_PROGRESS to CHECKING status.
    """
    try:
        # Create repository and use case
        repository = CompetitionRepositoryImpl(db)
        use_case = ChangeCompetitionStatusUseCase(repository)

        # Execute use case
        competition = await use_case.execute(competition_id, CompetitionStatus.CHECKING)

        # Return response
        return CompetitionResponse.from_entity(competition)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{competition_id}/publish", response_model=CompetitionResponse)
async def publish_results(
    competition_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(UserRole.ADMIN))]
):
    """Publish competition results.

    **Admin only**

    Transitions competition from CHECKING to PUBLISHED status.
    """
    try:
        # Create repository and use case
        repository = CompetitionRepositoryImpl(db)
        use_case = ChangeCompetitionStatusUseCase(repository)

        # Execute use case
        competition = await use_case.execute(competition_id, CompetitionStatus.PUBLISHED)

        # Return response
        return CompetitionResponse.from_entity(competition)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
