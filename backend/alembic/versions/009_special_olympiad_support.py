"""Add special olympiad settings and participant captain/location fields.

Revision ID: 009
Revises: 008
Create Date: 2026-03-30 16:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # competitions
    op.add_column(
        "competitions",
        sa.Column("is_special", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "competitions",
        sa.Column("special_tours_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "competitions",
        sa.Column("special_tour_modes", sa.JSON(), nullable=True),
    )
    op.add_column(
        "competitions",
        sa.Column("special_settings", sa.JSON(), nullable=True),
    )

    # participants
    op.add_column(
        "participants",
        sa.Column("institution_location", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "participants",
        sa.Column("is_captain", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("participants", "is_captain")
    op.drop_column("participants", "institution_location")

    op.drop_column("competitions", "special_settings")
    op.drop_column("competitions", "special_tour_modes")
    op.drop_column("competitions", "special_tours_count")
    op.drop_column("competitions", "is_special")

