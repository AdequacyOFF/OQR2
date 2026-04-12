"""Participant model."""

import uuid
import datetime as dt
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base

if TYPE_CHECKING:
    from .registration import RegistrationModel
    from .user import UserModel
    from .institution import InstitutionModel


class ParticipantModel(Base):
    """Participant database model."""

    __tablename__ = "participants"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True
    )
    full_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True
    )
    school: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    grade: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        index=True
    )
    institution_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("institutions.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    institution_location: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    is_captain: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )
    dob: Mapped[Optional[dt.date]] = mapped_column(
        Date,
        nullable=True
    )
    position: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    military_rank: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    passport_series_number: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    passport_issued_by: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    passport_issued_date: Mapped[Optional[dt.date]] = mapped_column(Date, nullable=True)
    military_booklet_number: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    military_personal_number: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
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
    user: Mapped["UserModel"] = relationship(
        "UserModel",
        back_populates="participant",
        lazy="selectin"
    )
    institution: Mapped[Optional["InstitutionModel"]] = relationship(
        "InstitutionModel",
        back_populates="participants",
        lazy="selectin"
    )
    registrations: Mapped[list["RegistrationModel"]] = relationship(
        "RegistrationModel",
        back_populates="participant"
    )

    def __repr__(self) -> str:
        return f"<ParticipantModel(id={self.id}, full_name={self.full_name}, grade={self.grade})>"
