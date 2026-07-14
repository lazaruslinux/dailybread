"""Per-member notification history for the Inbox in the You tab.

One row per recipient per event (board changes, dinner lock-ins, workouts,
approvals, crumb earns). Written independently of push config, capped per
member on insert, cleared in bulk by the read-all endpoint.

Revision ID: 0051
Revises: 0050
Create Date: 2026-07-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inbox_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("family_id", sa.Integer(), sa.ForeignKey("families.id"), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_inbox_entries_family_id", "inbox_entries", ["family_id"])
    op.create_index("ix_inbox_entries_user_id", "inbox_entries", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_inbox_entries_user_id", table_name="inbox_entries")
    op.drop_index("ix_inbox_entries_family_id", table_name="inbox_entries")
    op.drop_table("inbox_entries")
