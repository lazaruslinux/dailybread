"""Optional goal body fat percent alongside the goal weight

Revision ID: 0024
Revises: 0023
Create Date: 2026-07-08

A second, optional way to picture the goal. Informational only: the calorie
math and the at-goal flip stay driven by weight.
"""
from alembic import op
import sqlalchemy as sa

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "health_profiles", sa.Column("goal_body_fat_pct", sa.Float(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("health_profiles", "goal_body_fat_pct")
