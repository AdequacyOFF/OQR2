"""Participant repository implementation."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import List

from ...domain.entities import Participant
from ...domain.repositories import ParticipantRepository
from ..database.models import ParticipantModel


class ParticipantRepositoryImpl(ParticipantRepository):
    """SQLAlchemy implementation of ParticipantRepository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, entity: Participant) -> Participant:
        """Create a new participant."""
        model = ParticipantModel(
            id=entity.id,
            user_id=entity.user_id,
            full_name=entity.full_name,
            school=entity.school,
            grade=entity.grade,
            institution_id=entity.institution_id,
            institution_location=entity.institution_location,
            is_captain=entity.is_captain,
            dob=entity.dob,
            created_at=entity.created_at,
            updated_at=entity.updated_at
        )
        self.session.add(model)
        await self.session.flush()
        return entity

    async def get_by_id(self, entity_id: UUID) -> Participant | None:
        """Get participant by ID."""
        result = await self.session.execute(
            select(ParticipantModel).where(ParticipantModel.id == entity_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_entity(model)

    async def get_all(self, skip: int = 0, limit: int = 100) -> List[Participant]:
        """Get all participants with pagination."""
        result = await self.session.execute(
            select(ParticipantModel)
            .offset(skip)
            .limit(limit)
            .order_by(ParticipantModel.created_at.desc())
        )
        models = result.scalars().all()
        return [self._to_entity(model) for model in models]

    async def update(self, entity: Participant) -> Participant:
        """Update an existing participant."""
        result = await self.session.execute(
            select(ParticipantModel).where(ParticipantModel.id == entity.id)
        )
        model = result.scalar_one_or_none()
        if not model:
            raise ValueError(f"Участник с id {entity.id} не найден")

        model.full_name = entity.full_name
        model.school = entity.school
        model.grade = entity.grade
        model.institution_id = entity.institution_id
        model.institution_location = entity.institution_location
        model.is_captain = entity.is_captain
        model.dob = entity.dob
        model.updated_at = entity.updated_at

        await self.session.flush()
        return entity

    async def delete(self, entity_id: UUID) -> bool:
        """Delete a participant."""
        result = await self.session.execute(
            select(ParticipantModel).where(ParticipantModel.id == entity_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return False

        await self.session.delete(model)
        await self.session.flush()
        return True

    async def get_by_user_id(self, user_id: UUID) -> Participant | None:
        """Get participant by user ID."""
        result = await self.session.execute(
            select(ParticipantModel).where(ParticipantModel.user_id == user_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_entity(model)

    def _to_entity(self, model: ParticipantModel) -> Participant:
        """Convert SQLAlchemy model to domain entity."""
        return Participant(
            id=model.id,
            user_id=model.user_id,
            full_name=model.full_name,
            school=model.school,
            grade=model.grade,
            institution_id=model.institution_id,
            institution_location=model.institution_location,
            is_captain=model.is_captain,
            dob=model.dob,
            created_at=model.created_at,
            updated_at=model.updated_at
        )
