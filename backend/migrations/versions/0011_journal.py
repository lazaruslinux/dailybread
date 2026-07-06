"""Daily journal entries

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-06

Adds journal_entries: one private written entry per member per day (unique on
user_id + date_for). Strictly personal — never shown to other members — which
is why it lives in its own table rather than alongside the shared mood.
"""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "journal_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date_for", sa.Date(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "date_for", name="uq_journal_user_day"),
    )
    op.create_index("ix_journal_entries_user_id", "journal_entries", ["user_id"])
    op.create_index("ix_journal_entries_date_for", "journal_entries", ["date_for"])


def downgrade() -> None:
    op.drop_index("ix_journal_entries_date_for", table_name="journal_entries")
    op.drop_index("ix_journal_entries_user_id", table_name="journal_entries")
    op.drop_table("journal_entries")
