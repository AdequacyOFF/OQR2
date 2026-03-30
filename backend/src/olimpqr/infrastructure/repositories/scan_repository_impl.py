"""Scan repository implementation."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import List

from ...domain.entities import Scan
from ...domain.repositories import ScanRepository
from ..database.models import ScanModel


class ScanRepositoryImpl(ScanRepository):
    """SQLAlchemy implementation of ScanRepository."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, entity: Scan) -> Scan:
        """Create a new scan."""
        model = ScanModel(
            id=entity.id,
            attempt_id=entity.attempt_id,
            answer_sheet_id=entity.answer_sheet_id,
            file_path=entity.file_path,
            ocr_score=entity.ocr_score,
            ocr_confidence=entity.ocr_confidence,
            ocr_raw_text=entity.ocr_raw_text,
            verified_by=entity.verified_by,
            uploaded_by=entity.uploaded_by,
            created_at=entity.created_at,
            updated_at=entity.updated_at
        )
        self.session.add(model)
        await self.session.flush()
        return entity

    async def get_by_id(self, entity_id: UUID) -> Scan | None:
        """Get scan by ID."""
        result = await self.session.execute(
            select(ScanModel).where(ScanModel.id == entity_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_entity(model)

    async def get_all(self, skip: int = 0, limit: int = 100) -> List[Scan]:
        """Get all scans with pagination."""
        result = await self.session.execute(
            select(ScanModel)
            .offset(skip)
            .limit(limit)
            .order_by(ScanModel.created_at.desc())
        )
        models = result.scalars().all()
        return [self._to_entity(model) for model in models]

    async def update(self, entity: Scan) -> Scan:
        """Update an existing scan."""
        result = await self.session.execute(
            select(ScanModel).where(ScanModel.id == entity.id)
        )
        model = result.scalar_one_or_none()
        if not model:
            raise ValueError(f"Скан с id {entity.id} не найден")

        model.ocr_score = entity.ocr_score
        model.ocr_confidence = entity.ocr_confidence
        model.ocr_raw_text = entity.ocr_raw_text
        model.answer_sheet_id = entity.answer_sheet_id
        model.verified_by = entity.verified_by
        model.updated_at = entity.updated_at

        await self.session.flush()
        return entity

    async def delete(self, entity_id: UUID) -> bool:
        """Delete a scan."""
        result = await self.session.execute(
            select(ScanModel).where(ScanModel.id == entity_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return False

        await self.session.delete(model)
        await self.session.flush()
        return True

    async def get_by_attempt(self, attempt_id: UUID) -> List[Scan]:
        """Get all scans for an attempt."""
        result = await self.session.execute(
            select(ScanModel)
            .where(ScanModel.attempt_id == attempt_id)
            .order_by(ScanModel.created_at.asc())
        )
        models = result.scalars().all()
        return [self._to_entity(model) for model in models]

    async def get_unverified(self, skip: int = 0, limit: int = 100) -> List[Scan]:
        """Get scans that haven't been manually verified."""
        result = await self.session.execute(
            select(ScanModel)
            .where(ScanModel.verified_by.is_(None))
            .offset(skip)
            .limit(limit)
            .order_by(ScanModel.created_at.asc())
        )
        models = result.scalars().all()
        return [self._to_entity(model) for model in models]

    def _to_entity(self, model: ScanModel) -> Scan:
        """Convert SQLAlchemy model to domain entity."""
        return Scan(
            id=model.id,
            attempt_id=model.attempt_id,
            answer_sheet_id=model.answer_sheet_id,
            file_path=model.file_path,
            ocr_score=model.ocr_score,
            ocr_confidence=model.ocr_confidence,
            ocr_raw_text=model.ocr_raw_text,
            verified_by=model.verified_by,
            uploaded_by=model.uploaded_by,
            created_at=model.created_at,
            updated_at=model.updated_at
        )
