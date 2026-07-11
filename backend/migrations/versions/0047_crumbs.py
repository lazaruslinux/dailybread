"""Breadcrumbs: the streak displays become one earned economy.

crumb_ledger holds every award (unique (user, source_key) makes each one
idempotent forever). share_verse_streak becomes share_level — the streak
number no longer crosses the village wall on its own; the level does, by the
same people's existing choice.

Revision ID: 0047
Revises: 0046
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crumb_ledger",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("family_id", sa.Integer(), sa.ForeignKey("families.id"), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date_for", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("source_key", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "source_key", name="uq_crumb_source"),
    )
    op.create_index("ix_crumb_ledger_family_id", "crumb_ledger", ["family_id"])
    op.create_index("ix_crumb_ledger_user_id", "crumb_ledger", ["user_id"])
    op.create_index("ix_crumb_ledger_date_for", "crumb_ledger", ["date_for"])
    op.alter_column("users", "share_verse_streak", new_column_name="share_level")


def downgrade() -> None:
    op.alter_column("users", "share_level", new_column_name="share_verse_streak")
    op.drop_index("ix_crumb_ledger_date_for", table_name="crumb_ledger")
    op.drop_index("ix_crumb_ledger_user_id", table_name="crumb_ledger")
    op.drop_index("ix_crumb_ledger_family_id", table_name="crumb_ledger")
    op.drop_table("crumb_ledger")
