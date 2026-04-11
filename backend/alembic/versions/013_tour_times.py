"""Add tour_times table for scanner-recorded tour start/end times.

Revision ID: 013
Revises: 012
Create Date: 2026-04-11 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tour_times",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("competition_id", sa.Uuid(), nullable=False),
        sa.Column("tour_number", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["competition_id"], ["competitions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("competition_id", "tour_number", name="uq_tour_time"),
    )
    op.create_index(
        "ix_tour_times_competition_id",
        "tour_times",
        ["competition_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_tour_times_competition_id", table_name="tour_times")
    op.drop_table("tour_times")
