"""Multi-day cards and an end to recurrence.

Three changes to items: end_date is the last day a dated card covers (a trip,
an overnight stay), NULL meaning the single day date_for already names;
repeat_until is the last day a recurring card may land on, NULL meaning
forever (an "after N occurrences" end is resolved to a date before it is
stored); and notes grows to 1000 characters now that the form offers a real
multi-line box instead of a single-line field.

Revision ID: 0056
Revises: 0055
Create Date: 2026-07-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("items", sa.Column("end_date", sa.Date(), nullable=True))
    op.add_column("items", sa.Column("repeat_until", sa.Date(), nullable=True))
    op.alter_column(
        "items",
        "notes",
        existing_type=sa.String(300),
        type_=sa.String(1000),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "items",
        "notes",
        existing_type=sa.String(1000),
        type_=sa.String(300),
        existing_nullable=False,
    )
    op.drop_column("items", "repeat_until")
    op.drop_column("items", "end_date")
