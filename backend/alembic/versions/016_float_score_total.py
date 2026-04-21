"""Change score_total from Integer to Float to support fractional scores.

Revision ID: 016
Revises: 015
Create Date: 2026-04-21 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "attempts",
        "score_total",
        existing_type=sa.Integer(),
        type_=sa.Float(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "attempts",
        "score_total",
        existing_type=sa.Float(),
        type_=sa.Integer(),
        existing_nullable=True,
    )
