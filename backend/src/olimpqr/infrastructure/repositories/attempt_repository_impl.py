"""Attempt repository implementation."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import List

from ...domain.entities import Attempt
from ...domain.repositories import AttemptRepository
from ...domain.value_objects import TokenHash
from ..database.models import AttemptModel, RegistrationModel


class AttemptRepositoryImpl(AttemptRepository):
    """SQLAlchemy implementation of AttemptRepository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, entity: Attempt) -> Attempt:
        """Create a new attempt."""
        model = AttemptModel(
            id=entity.id,
            registration_id=entity.registration_id,
            variant_number=entity.variant_number,
            sheet_token_hash=entity.sheet_token_hash.value,
            status=entity.status,
            score_total=entity.score_total,
            confidence=entity.confidence,
            pdf_file_path=entity.pdf_file_path,
            task_scores=entity.task_scores,
            created_at=entity.created_at,
            updated_at=entity.updated_at
        )
        self.session.add(model)
        await self.session.flush()
        return entity

    async def get_by_id(self, entity_id: UUID) -> Attempt | None:
        """Get attempt by ID."""
        result = await self.session.execute(
            select(AttemptModel).where(AttemptModel.id == entity_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_entity(model)

    async def get_all(self, skip: int = 0, limit: int = 100) -> List[Attempt]:
        """Get all attempts with pagination."""
        result = await self.session.execute(
            select(AttemptModel)
            .offset(skip)
            .limit(limit)
            .order_by(AttemptModel.created_at.desc())
        )
        models = result.scalars().all()
        return [self._to_entity(model) for model in models]

    async def update(self, entity: Attempt) -> Attempt:
        """Update an existing attempt."""
        result = await self.session.execute(
            select(AttemptModel).where(AttemptModel.id == entity.id)
        )
        model = result.scalar_one_or_none()
        if not model:
            raise ValueError(f"Попытка с id {entity.id} не найдена")

        model.status = entity.status
        model.score_total = entity.score_total
        model.confidence = entity.confidence
        model.pdf_file_path = entity.pdf_file_path
        model.task_scores = entity.task_scores
        model.updated_at = entity.updated_at

        await self.session.flush()
        return entity

    async def delete(self, entity_id: UUID) -> bool:
        """Delete an attempt."""
        result = await self.session.execute(
            select(AttemptModel).where(AttemptModel.id == entity_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return False

        await self.session.delete(model)
        await self.session.flush()
        return True

    async def get_by_sheet_token_hash(self, sheet_token_hash: str) -> Attempt | None:
        """Get attempt by sheet token hash."""
        result = await self.session.execute(
            select(AttemptModel).where(AttemptModel.sheet_token_hash == sheet_token_hash)
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_entity(model)

    async def get_by_registration(self, registration_id: UUID) -> Attempt | None:
        """Get attempt by registration ID."""
        result = await self.session.execute(
            select(AttemptModel).where(AttemptModel.registration_id == registration_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_entity(model)

    async def get_by_competition(self, competition_id: UUID, skip: int = 0, limit: int = 1000) -> List[Attempt]:
        """Get all attempts for a competition."""
        result = await self.session.execute(
            select(AttemptModel)
            .join(RegistrationModel, AttemptModel.registration_id == RegistrationModel.id)
            .where(RegistrationModel.competition_id == competition_id)
            .offset(skip)
            .limit(limit)
            .order_by(AttemptModel.created_at.asc())
        )
        models = result.scalars().all()
        return [self._to_entity(model) for model in models]

    def _to_entity(self, model: AttemptModel) -> Attempt:
        """Convert SQLAlchemy model to domain entity."""
        return Attempt(
            id=model.id,
            registration_id=model.registration_id,
            variant_number=model.variant_number,
            sheet_token_hash=TokenHash(value=model.sheet_token_hash),
            status=model.status,
            score_total=model.score_total,
            confidence=model.confidence,
            pdf_file_path=model.pdf_file_path,
            task_scores=model.task_scores,
            created_at=model.created_at,
            updated_at=model.updated_at
        )
