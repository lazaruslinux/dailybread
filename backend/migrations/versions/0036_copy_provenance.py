"""Copies remember where they came from

Revision ID: 0036
Revises: 0035
Create Date: 2026-07-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("recipes", sa.Column("provenance", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("recipes", "provenance")
