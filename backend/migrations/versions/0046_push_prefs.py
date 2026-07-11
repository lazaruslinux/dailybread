"""Per-kind push preferences on the member.

Only turned-off kinds are stored ({"midday": false}); a missing key or a NULL
column means on. Everyone therefore keeps exactly the notifications they had,
and future kinds arrive enabled without a backfill.

Revision ID: 0046
Revises: 0045
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("push_prefs", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "push_prefs")
