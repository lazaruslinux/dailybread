"""Verse check-offs and reading streaks, strictly opt-in

Revision ID: 0044
Revises: 0043
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("verse_streak_enabled", sa.Boolean, nullable=False, server_default="false"),
    )
    op.add_column(
        "users",
        sa.Column("share_verse_streak", sa.Boolean, nullable=False, server_default="false"),
    )
    op.create_table(
        "verse_checks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("date_for", sa.Date, nullable=False, index=True),
        sa.Column("verse_idx", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "date_for", "verse_idx", name="uq_verse_check"),
    )


def downgrade() -> None:
    op.drop_table("verse_checks")
    op.drop_column("users", "share_verse_streak")
    op.drop_column("users", "verse_streak_enabled")
