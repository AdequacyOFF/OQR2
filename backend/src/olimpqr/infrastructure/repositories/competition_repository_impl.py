"""Competition repository implementation."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import List

from ...domain.entities import Competition
from ...domain.repositories import CompetitionRepository
from ...domain.value_objects import CompetitionStatus
from ..database.models import CompetitionModel


class CompetitionRepositoryImpl(CompetitionRepository):
    """SQLAlchemy implementation of CompetitionRepository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, entity: Competition) -> Competition:
        """Create a new competition."""
        model = CompetitionModel(
            id=entity.id,
            name=entity.name,
            date=entity.date,
            registration_start=entity.registration_start,
            registration_end=entity.registration_end,
            variants_count=entity.variants_count,
            max_score=entity.max_score,
            is_special=entity.is_special,
            special_tours_count=entity.special_tours_count,
            special_tour_modes=entity.special_tour_modes,
            special_settings=entity.special_settings,
            status=entity.status,
            created_by=entity.created_by,
            created_at=entity.created_at,
            updated_at=entity.updated_at
        )
        self.session.add(model)
        await self.session.flush()
        return entity

    async def get_by_id(self, entity_id: UUID) -> Competition | None:
        """Get competition by ID."""
        result = await self.session.execute(
            select(CompetitionModel).where(CompetitionModel.id == entity_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_entity(model)

    async def get_all(self, skip: int = 0, limit: int = 100) -> List[Competition]:
        """Get all competitions with pagination."""
        result = await self.session.execute(
            select(CompetitionModel)
            .offset(skip)
            .limit(limit)
            .order_by(CompetitionModel.date.desc())
        )
        models = result.scalars().all()
        return [self._to_entity(model) for model in models]

    async def update(self, entity: Competition) -> Competition:
        """Update an existing competition."""
        result = await self.session.execute(
            select(CompetitionModel).where(CompetitionModel.id == entity.id)
        )
        model = result.scalar_one_or_none()
        if not model:
            raise ValueError(f"Олимпиада с id {entity.id} не найдена")

        model.name = entity.name
        model.date = entity.date
        model.registration_start = entity.registration_start
        model.registration_end = entity.registration_end
        model.variants_count = entity.variants_count
        model.max_score = entity.max_score
        model.is_special = entity.is_special
        model.special_tours_count = entity.special_tours_count
        model.special_tour_modes = entity.special_tour_modes
        model.special_settings = entity.special_settings
        model.status = entity.status
        model.updated_at = entity.updated_at

        await self.session.flush()
        return entity

    async def delete(self, entity_id: UUID) -> bool:
        """Delete a competition."""
        result = await self.session.execute(
            select(CompetitionModel).where(CompetitionModel.id == entity_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return False

        await self.session.delete(model)
        await self.session.flush()
        return True

    async def get_by_status(self, status: CompetitionStatus, skip: int = 0, limit: int = 100) -> List[Competition]:
        """Get competitions by status."""
        result = await self.session.execute(
            select(CompetitionModel)
            .where(CompetitionModel.status == status)
            .offset(skip)
            .limit(limit)
            .order_by(CompetitionModel.date.desc())
        )
        models = result.scalars().all()
        return [self._to_entity(model) for model in models]

    async def get_published(self, skip: int = 0, limit: int = 100) -> List[Competition]:
        """Get published competitions."""
        result = await self.session.execute(
            select(CompetitionModel)
            .where(CompetitionModel.status == CompetitionStatus.PUBLISHED)
            .offset(skip)
            .limit(limit)
            .order_by(CompetitionModel.date.desc())
        )
        models = result.scalars().all()
        return [self._to_entity(model) for model in models]

    def _to_entity(self, model: CompetitionModel) -> Competition:
        """Convert SQLAlchemy model to domain entity."""
        return Competition(
            id=model.id,
            name=model.name,
            date=model.date,
            registration_start=model.registration_start,
            registration_end=model.registration_end,
            variants_count=model.variants_count,
            max_score=model.max_score,
            is_special=model.is_special,
            special_tours_count=model.special_tours_count,
            special_tour_modes=model.special_tour_modes,
            special_settings=model.special_settings,
            status=model.status,
            created_by=model.created_by,
            created_at=model.created_at,
            updated_at=model.updated_at
        )
