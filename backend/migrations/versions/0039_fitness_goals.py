"""Per-member fitness ring goals; NULL means the recommended defaults

Revision ID: 0039
Revises: 0038
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("goal_steps", sa.Integer, nullable=True))
    op.add_column("users", sa.Column("goal_active_kcal", sa.Integer, nullable=True))
    op.add_column("users", sa.Column("goal_exercise_min", sa.Integer, nullable=True))


def downgrade() -> None:
    op.drop_column("users", "goal_exercise_min")
    op.drop_column("users", "goal_active_kcal")
    op.drop_column("users", "goal_steps")
