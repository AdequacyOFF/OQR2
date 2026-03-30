"""Create competition use case."""

from uuid import uuid4, UUID

from ....domain.entities import Competition
from ....domain.repositories import CompetitionRepository
from ....domain.value_objects import CompetitionStatus
from ...dto.competition_dto import CreateCompetitionDTO


class CreateCompetitionUseCase:
    """Use case for creating a new competition."""

    def __init__(self, competition_repository: CompetitionRepository):
        self.competition_repository = competition_repository

    async def execute(self, dto: CreateCompetitionDTO, created_by_user_id: UUID) -> Competition:
        """Create a new competition.

        Args:
            dto: Competition creation data
            created_by_user_id: ID of the user creating the competition

        Returns:
            Created competition entity

        Raises:
            ValueError: If validation fails
        """
        # Create competition entity with DRAFT status
        competition = Competition(
            id=uuid4(),
            name=dto.name,
            date=dto.date,
            registration_start=dto.registration_start,
            registration_end=dto.registration_end,
            variants_count=dto.variants_count,
            max_score=dto.max_score,
            is_special=dto.is_special,
            special_tours_count=dto.special_tours_count,
            special_tour_modes=dto.special_tour_modes,
            special_settings=dto.special_settings,
            status=CompetitionStatus.DRAFT,
            created_by=created_by_user_id
        )

        # Save to repository
        competition = await self.competition_repository.create(competition)

        return competition
