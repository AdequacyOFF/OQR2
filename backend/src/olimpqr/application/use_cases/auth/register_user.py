"""Register user use case."""

from uuid import uuid4

from ....domain.entities import User, Participant
from ....domain.repositories import UserRepository, ParticipantRepository
from ....domain.value_objects import UserRole
from ....infrastructure.security import hash_password, create_access_token
from ...dto import RegisterUserDTO, AuthResponseDTO


class RegisterUserUseCase:
    """Use case for registering a new user."""

    def __init__(
        self,
        user_repository: UserRepository,
        participant_repository: ParticipantRepository | None = None
    ):
        self.user_repository = user_repository
        self.participant_repository = participant_repository

    async def execute(self, dto: RegisterUserDTO) -> AuthResponseDTO:
        """Register a new user.

        Args:
            dto: Registration data

        Returns:
            Authentication response with access token

        Raises:
            ValueError: If email already exists or validation fails
        """
        # Check if email already exists
        if await self.user_repository.exists_by_email(dto.email):
            raise ValueError(f"Пользователь с email {dto.email} уже существует")

        # Validate participant-specific fields
        if dto.role == UserRole.PARTICIPANT:
            if not dto.full_name or not dto.school:
                raise ValueError("Для регистрации участника требуется ФИО и учебное учреждение")
            if dto.grade is not None and not (1 <= dto.grade <= 12):
                raise ValueError("Класс должен быть от 1 до 12")

        # Hash password
        password_hash = hash_password(dto.password)

        # Create user entity
        user = User(
            id=uuid4(),
            email=dto.email,
            password_hash=password_hash,
            role=dto.role,
            is_active=True
        )

        # Save user
        user = await self.user_repository.create(user)

        # Create participant profile if role is PARTICIPANT
        if dto.role == UserRole.PARTICIPANT and self.participant_repository:
            participant = Participant(
                id=uuid4(),
                user_id=user.id,
                full_name=dto.full_name,
                school=dto.school,
                grade=dto.grade,
                institution_id=dto.institution_id,
                institution_location=dto.institution_location,
                is_captain=dto.is_captain,
                dob=dto.dob,
            )
            await self.participant_repository.create(participant)

        # Generate JWT token
        access_token = create_access_token(
            user_id=user.id,
            email=user.email,
            role=user.role
        )

        return AuthResponseDTO(
            access_token=access_token,
            token_type="bearer",
            user_id=user.id,
            email=user.email,
            role=user.role
        )
