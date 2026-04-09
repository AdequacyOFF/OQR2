"""Add badge_photos table for storing uploaded badge photos in DB.

Revision ID: 010
Revises: 009
Create Date: 2026-04-09 19:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "badge_photos",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("normalized_key", sa.String(length=500), nullable=False),
        sa.Column("original_path", sa.String(length=500), nullable=True),
        sa.Column("content_type", sa.String(length=100), nullable=True),
        sa.Column("image_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_badge_photos_id"), "badge_photos", ["id"], unique=False)
    op.create_index(
        op.f("ix_badge_photos_normalized_key"),
        "badge_photos",
        ["normalized_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_badge_photos_normalized_key"), table_name="badge_photos")
    op.drop_index(op.f("ix_badge_photos_id"), table_name="badge_photos")
    op.drop_table("badge_photos")

