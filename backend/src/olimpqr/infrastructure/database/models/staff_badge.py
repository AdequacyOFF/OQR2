"""Staff badge model — non-participant badge entries."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class StaffBadgeModel(Base):
    __tablename__ = "staff_badges"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4, index=True)
    competition_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("competitions.id", ondelete="CASCADE"), nullable=True, index=True,
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(255), nullable=False)
    institution: Mapped[str | None] = mapped_column(String(255), nullable=True)
    photo_content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    photo_bytes: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
