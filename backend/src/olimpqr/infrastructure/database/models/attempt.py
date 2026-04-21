"""Attempt model."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Enum as SQLEnum, Float, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from olimpqr.domain.value_objects.attempt_status import AttemptStatus

from ..base import Base

if TYPE_CHECKING:
    from .registration import RegistrationModel
    from .scan import ScanModel


class AttemptModel(Base):
    """Attempt database model."""

    __tablename__ = "attempts"
    __table_args__ = (
        Index("ix_attempts_registration_status", "registration_id", "status"),
        Index("ix_attempts_sheet_token", "sheet_token_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    registration_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("registrations.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    variant_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )
    sheet_token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True
    )
    status: Mapped[AttemptStatus] = mapped_column(
        SQLEnum(
            AttemptStatus,
            name="attemptstatus",
            native_enum=True,
            create_type=False,
            values_callable=lambda e: [member.value for member in e],
        ),
        nullable=False,
        default=AttemptStatus.PRINTED,
        index=True
    )
    score_total: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )
    confidence: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )
    pdf_file_path: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True
    )
    task_scores: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True
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
    registration: Mapped["RegistrationModel"] = relationship(
        "RegistrationModel",
        back_populates="attempts",
        lazy="selectin"
    )
    scans: Mapped[list["ScanModel"]] = relationship(
        "ScanModel",
        back_populates="attempt",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<AttemptModel(id={self.id}, registration_id={self.registration_id}, variant={self.variant_number}, status={self.status})>"
