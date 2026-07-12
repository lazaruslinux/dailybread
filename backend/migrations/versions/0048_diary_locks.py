"""Lock in the day's calorie tracking.

A (member, date) pair: presence means the day is locked. The first lock of a
date pays +2 breadcrumbs through the ledger; the row itself carries no more
state than that.

Revision ID: 0048
Revises: 0047
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "diary_day_locks",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("date_for", sa.Date(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("diary_day_locks")
