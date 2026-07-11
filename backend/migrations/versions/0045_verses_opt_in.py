"""Daily verses become the opt-in itself: receiving them includes the streak

Existing members have lived with the verse card since day one, so they stay
opted in; only accounts created after this start dark and choose in the tour
(or later in You).

Revision ID: 0045
Revises: 0044
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("users", "verse_streak_enabled", new_column_name="verses_enabled")
    op.execute(sa.text("UPDATE users SET verses_enabled = true"))


def downgrade() -> None:
    op.alter_column("users", "verses_enabled", new_column_name="verse_streak_enabled")
