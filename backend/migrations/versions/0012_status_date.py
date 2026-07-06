"""Daily status: date-stamp users.bio so it clears overnight

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-06

Adds users.status_date. The profile "status" (stored in users.bio) is now a
daily note like a mood: it shows only for the day it was set, and reads as no
status once the day rolls over. NULL means "not set today". Existing bios keep
their text but, with a NULL status_date, read as no status until re-set — which
is the intended fresh start.
"""
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("status_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "status_date")
