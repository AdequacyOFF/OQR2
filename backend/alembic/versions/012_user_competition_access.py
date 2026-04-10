"""Add user_competition_access table and task_scores to attempts.

Revision ID: 012
Revises: 011
Create Date: 2026-04-10 14:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_competition_access",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("competition_id", sa.Uuid(), nullable=False),
        sa.Column("assigned_by", sa.Uuid(), nullable=True),
        sa.Column("assigned_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["competition_id"], ["competitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "competition_id", name="uq_user_competition_access"),
    )
    op.create_index(
        "ix_user_competition_access_user_id",
        "user_competition_access",
        ["user_id"],
    )
    op.create_index(
        "ix_user_competition_access_competition_id",
        "user_competition_access",
        ["competition_id"],
    )

    op.add_column(
        "attempts",
        sa.Column("task_scores", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("attempts", "task_scores")
    op.drop_index("ix_user_competition_access_competition_id", table_name="user_competition_access")
    op.drop_index("ix_user_competition_access_user_id", table_name="user_competition_access")
    op.drop_table("user_competition_access")
