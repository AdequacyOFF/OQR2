"""Update competition use case."""

from datetime import datetime
from uuid import UUID

from ....domain.entities import Competition
from ....domain.repositories import CompetitionRepository
from ...dto.competition_dto import UpdateCompetitionDTO


class UpdateCompetitionUseCase:
    """Use case for updating a competition."""

    def __init__(self, competition_repository: CompetitionRepository):
        self.competition_repository = competition_repository

    async def execute(self, competition_id: UUID, dto: UpdateCompetitionDTO) -> Competition:
        """Update a competition.

        Args:
            competition_id: Competition ID
            dto: Update data

        Returns:
            Updated competition entity

        Raises:
            ValueError: If competition not found or validation fails
        """
        # Get existing competition
        competition = await self.competition_repository.get_by_id(competition_id)
        if not competition:
            raise ValueError(f"Олимпиада с id {competition_id} не найдена")

        # Update fields if provided
        if dto.name is not None:
            competition.name = dto.name
        if dto.date is not None:
            competition.date = dto.date
        if dto.registration_start is not None:
            competition.registration_start = dto.registration_start
        if dto.registration_end is not None:
            competition.registration_end = dto.registration_end
        if dto.variants_count is not None:
            competition.variants_count = dto.variants_count
        if dto.max_score is not None:
            competition.max_score = dto.max_score
        if dto.is_special is not None:
            competition.is_special = dto.is_special
            if dto.is_special is False:
                competition.special_tours_count = None
                competition.special_tour_modes = None
                competition.special_settings = None
        if dto.special_tours_count is not None:
            competition.special_tours_count = dto.special_tours_count
        if dto.special_tour_modes is not None:
            competition.special_tour_modes = dto.special_tour_modes
        if dto.special_settings is not None:
            competition.special_settings = dto.special_settings

        # Update timestamp
        competition.updated_at = datetime.utcnow()

        # Validate the updated entity
        competition.__post_init__()

        # Save to repository
        competition = await self.competition_repository.update(competition)

        return competition
