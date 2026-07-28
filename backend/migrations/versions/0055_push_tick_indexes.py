"""Indexes for the every-minute push-tick queries.

The past-due pass scans items by date and the digest dedup scans digest_log
by (day, kind) several times a minute, forever; both were sequential scans
that only get slower as the tables grow. The main reminder-tick query still
seq-scans because its OR branch on repeat_type defeats any date index; that
scan is cheap and deliberately left alone.

Revision ID: 0055
Revises: 0054
Create Date: 2026-07-27
"""
from alembic import op

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_items_date_for", "items", ["date_for"])
    op.create_index("ix_digest_log_day_kind", "digest_log", ["date_for", "kind"])


def downgrade() -> None:
    op.drop_index("ix_digest_log_day_kind", table_name="digest_log")
    op.drop_index("ix_items_date_for", table_name="items")
