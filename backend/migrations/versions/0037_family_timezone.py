"""Families keep their own clock

Revision ID: 0037
Revises: 0036
Create Date: 2026-07-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("families", sa.Column("timezone", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("families", "timezone")
