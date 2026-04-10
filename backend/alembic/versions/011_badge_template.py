"""Add badge_templates table for online badge editor templates.

Revision ID: 011
Revises: 010
Create Date: 2026-04-10 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "badge_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("competition_id", sa.Uuid(), nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("background_image_bytes", sa.LargeBinary(), nullable=True),
        sa.Column("print_per_page", sa.Integer(), server_default="4", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["competition_id"], ["competitions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_badge_templates_id"), "badge_templates", ["id"], unique=False)
    op.create_index(
        op.f("ix_badge_templates_competition_id"),
        "badge_templates",
        ["competition_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_badge_templates_competition_id"), table_name="badge_templates")
    op.drop_index(op.f("ix_badge_templates_id"), table_name="badge_templates")
    op.drop_table("badge_templates")
