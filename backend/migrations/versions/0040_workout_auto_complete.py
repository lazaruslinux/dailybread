"""Routines can opt in to auto-completing from a member's synced workout

Revision ID: 0040
Revises: 0039
Create Date: 2026-07-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "items",
        sa.Column(
            "workout_auto_complete",
            sa.Boolean,
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("items", "workout_auto_complete")
