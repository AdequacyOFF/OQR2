"""Badge template model (stored in database, one per competition)."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, JSON, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class BadgeTemplateModel(Base):
    """Visual badge template for a competition, rendered via ReportLab."""

    __tablename__ = "badge_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )
    competition_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    # JSON structure: {width_mm, height_mm, background_w_mm, background_h_mm, elements: [...]}
    config_json: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    background_image_bytes: Mapped[bytes | None] = mapped_column(
        LargeBinary,
        nullable=True,
    )
    print_per_page: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=4,
        server_default="4",
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    def __repr__(self) -> str:
        return f"<BadgeTemplateModel(id={self.id}, competition_id={self.competition_id})>"
