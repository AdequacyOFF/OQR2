"""Competition model."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, Date, DateTime, Enum as SQLEnum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from olimpqr.domain.value_objects.competition_status import CompetitionStatus

from ..base import Base

if TYPE_CHECKING:
    from .registration import RegistrationModel
    from .user import UserModel


class CompetitionModel(Base):
    """Competition database model."""

    __tablename__ = "competitions"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True
    )
    date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True
    )
    registration_start: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        index=True
    )
    registration_end: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        index=True
    )
    variants_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )
    max_score: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )
    is_special: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        index=True,
    )
    special_tours_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    special_tour_modes: Mapped[list[str] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    special_settings: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )
    status: Mapped[CompetitionStatus] = mapped_column(
        SQLEnum(
            CompetitionStatus,
            name="competitionstatus",
            native_enum=True,
            create_type=False,
            values_callable=lambda e: [member.value for member in e],
        ),
        nullable=False,
        default=CompetitionStatus.DRAFT,
        index=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # Relationships
    creator: Mapped["UserModel"] = relationship(
        "UserModel",
        back_populates="competitions_created",
        foreign_keys=[created_by],
        lazy="selectin"
    )
    registrations: Mapped[list["RegistrationModel"]] = relationship(
        "RegistrationModel",
        back_populates="competition"
    )

    def __repr__(self) -> str:
        return f"<CompetitionModel(id={self.id}, name={self.name}, status={self.status})>"
