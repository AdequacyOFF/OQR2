"""Add passport / military booklet fields to participants for special olympiad imports.

Revision ID: 014
Revises: 013
Create Date: 2026-04-12 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("participants", sa.Column("position", sa.String(length=255), nullable=True))
    op.add_column("participants", sa.Column("military_rank", sa.String(length=255), nullable=True))
    op.add_column("participants", sa.Column("passport_series_number", sa.String(length=64), nullable=True))
    op.add_column("participants", sa.Column("passport_issued_by", sa.String(length=512), nullable=True))
    op.add_column("participants", sa.Column("passport_issued_date", sa.Date(), nullable=True))
    op.add_column("participants", sa.Column("military_booklet_number", sa.String(length=64), nullable=True))
    op.add_column("participants", sa.Column("military_personal_number", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("participants", "military_personal_number")
    op.drop_column("participants", "military_booklet_number")
    op.drop_column("participants", "passport_issued_date")
    op.drop_column("participants", "passport_issued_by")
    op.drop_column("participants", "passport_series_number")
    op.drop_column("participants", "military_rank")
    op.drop_column("participants", "position")
