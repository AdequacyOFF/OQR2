"""Profile API endpoints for participants."""

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ....infrastructure.database import get_db
from ....infrastructure.repositories import ParticipantRepositoryImpl
from ....domain.value_objects import UserRole
from ....domain.entities import User
from ...schemas.profile_schemas import (
    ParticipantProfileResponse,
    UpdateProfileRequest
)
from ...dependencies import require_role


router = APIRouter()


@router.get("", response_model=ParticipantProfileResponse)
async def get_my_profile(
    current_user: Annotated[User, Depends(require_role(UserRole.PARTICIPANT))],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Get current participant's profile.

    Requires participant role.
    Returns participant profile with all personal information.
    """
    # Get participant by user_id
    participant_repo = ParticipantRepositoryImpl(db)
    participant = await participant_repo.get_by_user_id(current_user.id)

    if not participant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Профиль участника не найден"
        )

    return ParticipantProfileResponse(
        id=participant.id,
        user_id=participant.user_id,
        full_name=participant.full_name,
        school=participant.school,
        grade=participant.grade,
        institution_id=participant.institution_id,
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
        created_at=participant.created_at,
        updated_at=participant.updated_at
    )


@router.put("", response_model=ParticipantProfileResponse)
async def update_my_profile(
    request: UpdateProfileRequest,
    current_user: Annotated[User, Depends(require_role(UserRole.PARTICIPANT))],
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Update current participant's profile.

    Requires participant role.
    Allows updating full_name, school, and grade.
    """
    # Get participant by user_id
    participant_repo = ParticipantRepositoryImpl(db)
    participant = await participant_repo.get_by_user_id(current_user.id)

    if not participant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Профиль участника не найден"
        )

    # Update profile using entity method
    try:
        participant.update_profile(
            full_name=request.full_name,
            school=request.school,
            grade=request.grade,
            institution_location=request.institution_location,
            is_captain=request.is_captain,
            dob=request.dob,
            position=request.position,
            military_rank=request.military_rank,
            passport_series_number=request.passport_series_number,
            passport_issued_by=request.passport_issued_by,
            passport_issued_date=request.passport_issued_date,
            military_booklet_number=request.military_booklet_number,
            military_personal_number=request.military_personal_number,
        )

        # Save to database
        updated_participant = await participant_repo.update(participant)

        return ParticipantProfileResponse(
            id=updated_participant.id,
            user_id=updated_participant.user_id,
            full_name=updated_participant.full_name,
            school=updated_participant.school,
            grade=updated_participant.grade,
            institution_id=updated_participant.institution_id,
            institution_location=updated_participant.institution_location,
            is_captain=updated_participant.is_captain,
            dob=updated_participant.dob,
            position=updated_participant.position,
            military_rank=updated_participant.military_rank,
            passport_series_number=updated_participant.passport_series_number,
            passport_issued_by=updated_participant.passport_issued_by,
            passport_issued_date=updated_participant.passport_issued_date,
            military_booklet_number=updated_participant.military_booklet_number,
            military_personal_number=updated_participant.military_personal_number,
            created_at=updated_participant.created_at,
            updated_at=updated_participant.updated_at
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
