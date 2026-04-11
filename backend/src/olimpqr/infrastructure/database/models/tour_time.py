"""Tour time model — stores scanner-recorded start/end times per tour per competition."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base

if TYPE_CHECKING:
    from .competition import CompetitionModel


class TourTimeModel(Base):
    """Records start and finish times for each tour of a competition."""

    __tablename__ = "tour_times"
    __table_args__ = (
        UniqueConstraint("competition_id", "tour_number", name="uq_tour_time"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )
    competition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tour_number: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("NOW()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("NOW()"),
        onupdate=datetime.utcnow,
    )

    competition: Mapped["CompetitionModel"] = relationship(
        "CompetitionModel",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<TourTimeModel(competition={self.competition_id}, tour={self.tour_number})>"
