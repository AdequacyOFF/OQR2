"""UserCompetitionAccess model."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base

if TYPE_CHECKING:
    from .competition import CompetitionModel
    from .user import UserModel


class UserCompetitionAccessModel(Base):
    """Grants a staff user access to a specific competition."""

    __tablename__ = "user_competition_access"
    __table_args__ = (
        UniqueConstraint("user_id", "competition_id", name="uq_user_competition_access"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    competition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    # Relationships
    user: Mapped["UserModel"] = relationship(
        "UserModel",
        foreign_keys=[user_id],
        lazy="selectin",
    )
    competition: Mapped["CompetitionModel"] = relationship(
        "CompetitionModel",
        foreign_keys=[competition_id],
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<UserCompetitionAccessModel(user_id={self.user_id}, competition_id={self.competition_id})>"
