"""Scheduled pushes grew from one to three: morning, midday, evening

Revision ID: 0028
Revises: 0027
Create Date: 2026-07-08

digest_log rows now carry which of the day's scheduled pushes they claim,
so the mid-day check and the evening check-in dedupe independently of the
morning digest. Existing rows are morning ones.
"""
from alembic import op
import sqlalchemy as sa

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "digest_log",
        sa.Column("kind", sa.String(10), nullable=False, server_default="morning"),
    )
    op.drop_constraint("uq_digest_user_day", "digest_log", type_="unique")
    op.create_unique_constraint(
        "uq_digest_user_day_kind", "digest_log", ["user_id", "date_for", "kind"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_digest_user_day_kind", "digest_log", type_="unique")
    op.create_unique_constraint("uq_digest_user_day", "digest_log", ["user_id", "date_for"])
    op.drop_column("digest_log", "kind")
