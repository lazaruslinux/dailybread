"""Opt-in: watch active calories count toward the day's food budget

Revision ID: 0041
Revises: 0040
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "count_watch_kcal",
            sa.Boolean,
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "count_watch_kcal")
