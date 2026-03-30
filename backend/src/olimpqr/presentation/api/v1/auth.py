"""Authentication API endpoints."""

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from ....infrastructure.security.rate_limiter import limiter
from ....infrastructure.database import get_db
from ....infrastructure.repositories import UserRepositoryImpl, ParticipantRepositoryImpl
from ....application.use_cases.auth import RegisterUserUseCase, LoginUserUseCase
from ....application.dto import RegisterUserDTO, LoginUserDTO
from ...schemas import RegisterRequest, LoginRequest, AuthResponse, UserResponse
from ...dependencies import get_current_active_user
from ....domain.entities import User


router = APIRouter()


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("3/minute")
async def register(
    request: Request,
    response: Response,
    body: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Register a new participant user.

    Public registration is only available for participants.
    Staff users (admitter, scanner, admin) must be created by admins.

    - **email**: User email (must be unique)
    - **password**: Password (min 8 characters)
    - **full_name**: Full name (required)
    - **school**: School name (required)
    - **grade**: School grade 1-12 (required)

    Returns JWT access token and user information.
    Rate limited to 3 requests per minute.
    """
    try:
        # Create repositories
        user_repository = UserRepositoryImpl(db)
        participant_repository = ParticipantRepositoryImpl(db)

        # Create use case
        use_case = RegisterUserUseCase(user_repository, participant_repository)

        # Create DTO - role is always PARTICIPANT for public registration
        from ....domain.value_objects import UserRole
        dto = RegisterUserDTO(
            email=body.email,
            password=body.password,
            role=UserRole.PARTICIPANT,
            full_name=body.full_name,
            school=body.school,
            grade=body.grade,
            institution_id=body.institution_id,
            institution_location=body.institution_location,
            is_captain=body.is_captain,
            dob=body.dob,
        )

        # Execute use case
        result = await use_case.execute(dto)

        # Return response
        return AuthResponse(
            access_token=result.access_token,
            token_type=result.token_type,
            user_id=result.user_id,
            email=result.email,
            role=result.role
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/login", response_model=AuthResponse)
@limiter.limit("5/minute")
async def login(
    request: Request,
    response: Response,
    body: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)]
):
    """Login with email and password.

    - **email**: User email
    - **password**: User password

    Returns JWT access token and user information.
    Rate limited to 5 requests per minute.
    """
    try:
        # Create repository
        user_repository = UserRepositoryImpl(db)

        # Create use case
        use_case = LoginUserUseCase(user_repository)

        # Create DTO
        dto = LoginUserDTO(
            email=body.email,
            password=body.password
        )

        # Execute use case
        result = await use_case.execute(dto)

        # Return response
        return AuthResponse(
            access_token=result.access_token,
            token_type=result.token_type,
            user_id=result.user_id,
            email=result.email,
            role=result.role
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"}
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: Annotated[User, Depends(get_current_active_user)]
):
    """Get current authenticated user information.

    Requires valid JWT token in Authorization header.
    """
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        role=current_user.role,
        is_active=current_user.is_active
    )
