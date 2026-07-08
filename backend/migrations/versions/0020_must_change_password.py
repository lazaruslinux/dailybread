"""Forced password change after an admin reset

Revision ID: 0020
Revises: 0019
Create Date: 2026-07-08

Adds users.must_change_password. An admin resetting a member's password now
hands over a generated one and sets this flag; until the member picks their
own password the flag locks their session down to the change-password flow.
Existing rows backfill to false, so nobody is affected by the migration.
"""
from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("users", "must_change_password")
