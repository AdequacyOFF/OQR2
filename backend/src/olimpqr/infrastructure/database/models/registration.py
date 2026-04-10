"""Registration model."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SQLEnum, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from olimpqr.domain.value_objects.registration_status import RegistrationStatus

from ..base import Base

if TYPE_CHECKING:
    from .attempt import AttemptModel
    from .competition import CompetitionModel
    from .entry_token import EntryTokenModel
    from .participant import ParticipantModel


class RegistrationModel(Base):
    """Registration database model."""

    __tablename__ = "registrations"
    __table_args__ = (
        UniqueConstraint("participant_id", "competition_id", name="uq_participant_competition"),
        Index("ix_registrations_participant_status", "participant_id", "status"),
        Index("ix_registrations_competition_status", "competition_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    participant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("participants.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    competition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    status: Mapped[RegistrationStatus] = mapped_column(
        SQLEnum(
            RegistrationStatus,
            name="registrationstatus",
            native_enum=True,
            create_type=False,
            values_callable=lambda e: [member.value for member in e],
        ),
        nullable=False,
        default=RegistrationStatus.PENDING,
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
    participant: Mapped["ParticipantModel"] = relationship(
        "ParticipantModel",
        back_populates="registrations",
        lazy="selectin"
    )
    competition: Mapped["CompetitionModel"] = relationship(
        "CompetitionModel",
        back_populates="registrations",
        lazy="selectin"
    )
    entry_token: Mapped["EntryTokenModel"] = relationship(
        "EntryTokenModel",
        back_populates="registration",
        uselist=False,
        passive_deletes=True,
    )
    attempts: Mapped[list["AttemptModel"]] = relationship(
        "AttemptModel",
        back_populates="registration",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<RegistrationModel(id={self.id}, participant_id={self.participant_id}, competition_id={self.competition_id}, status={self.status})>"
