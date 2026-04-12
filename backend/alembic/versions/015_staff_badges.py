"""Add staff_badges table for non-participant badge generation.

Revision ID: 015
Revises: 014
Create Date: 2026-04-12 18:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "staff_badges",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("competition_id", sa.Uuid(), sa.ForeignKey("competitions.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=255), nullable=False),
        sa.Column("institution", sa.String(length=255), nullable=True),
        sa.Column("photo_content_type", sa.String(length=100), nullable=True),
        sa.Column("photo_bytes", sa.LargeBinary(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("staff_badges")
