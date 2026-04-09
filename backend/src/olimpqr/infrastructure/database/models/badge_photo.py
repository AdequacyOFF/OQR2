"""Badge photo model (stored in database)."""

import uuid
from datetime import datetime

from sqlalchemy import LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class BadgePhotoModel(Base):
    """Photo mapped by normalized key for badge template token {{PHOTO}}."""

    __tablename__ = "badge_photos"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )
    normalized_key: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        unique=True,
        index=True,
    )
    original_path: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )
    content_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    image_bytes: Mapped[bytes] = mapped_column(
        LargeBinary,
        nullable=False,
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
        return f"<BadgePhotoModel(id={self.id}, normalized_key={self.normalized_key})>"

