"""Event start/end times and all-day appointments

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-05

Turns a card's single time into a start/end pair and adds an all-day flag, so
activities and appointments behave like calendar events (a From and a To), and
an appointment can be all-day with no times. Existing rows keep their start
(time_of_day) with a NULL end and all_day = false; they stay valid until next
edited, at which point the new per-kind rules apply.
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("items", sa.Column("end_time", sa.Time(), nullable=True))
    op.add_column(
        "items",
        sa.Column("all_day", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("items", "all_day")
    op.drop_column("items", "end_time")
