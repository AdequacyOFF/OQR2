"""UserCompetitionAccess repository implementation."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.models import UserCompetitionAccessModel


class UserCompetitionAccessRepositoryImpl:
    """Manages staff access to specific competitions."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def assign(
        self,
        user_id: UUID,
        competition_id: UUID,
        assigned_by: UUID,
    ) -> UserCompetitionAccessModel:
        """Grant a user access to a competition. Idempotent."""
        existing = await self.get_by_user_and_competition(user_id, competition_id)
        if existing:
            return existing
        model = UserCompetitionAccessModel(
            id=uuid4(),
            user_id=user_id,
            competition_id=competition_id,
            assigned_by=assigned_by,
            assigned_at=datetime.utcnow(),
        )
        self.session.add(model)
        await self.session.flush()
        return model

    async def revoke(self, user_id: UUID, competition_id: UUID) -> bool:
        """Revoke a user's access to a competition. Returns True if a row was deleted."""
        result = await self.session.execute(
            delete(UserCompetitionAccessModel).where(
                UserCompetitionAccessModel.user_id == user_id,
                UserCompetitionAccessModel.competition_id == competition_id,
            )
        )
        await self.session.flush()
        return result.rowcount > 0

    async def get_by_user_and_competition(
        self,
        user_id: UUID,
        competition_id: UUID,
    ) -> UserCompetitionAccessModel | None:
        result = await self.session.execute(
            select(UserCompetitionAccessModel).where(
                UserCompetitionAccessModel.user_id == user_id,
                UserCompetitionAccessModel.competition_id == competition_id,
            )
        )
        return result.scalar_one_or_none()

    async def check_access(self, user_id: UUID, competition_id: UUID) -> bool:
        row = await self.get_by_user_and_competition(user_id, competition_id)
        return row is not None

    async def get_competition_ids_for_user(self, user_id: UUID) -> list[UUID]:
        result = await self.session.execute(
            select(UserCompetitionAccessModel.competition_id).where(
                UserCompetitionAccessModel.user_id == user_id
            )
        )
        return list(result.scalars().all())

    async def get_users_for_competition(
        self, competition_id: UUID
    ) -> list[UserCompetitionAccessModel]:
        result = await self.session.execute(
            select(UserCompetitionAccessModel).where(
                UserCompetitionAccessModel.competition_id == competition_id
            )
        )
        return list(result.scalars().all())
