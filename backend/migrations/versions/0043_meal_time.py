"""Dinner gets a clock: an optional time on the day's meal row

Revision ID: 0043
Revises: 0042
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("meals", sa.Column("time_of_day", sa.Time, nullable=True))


def downgrade() -> None:
    op.drop_column("meals", "time_of_day")
