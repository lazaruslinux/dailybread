"""Food base unit (mass or volume)

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-07

Adds foods.base_unit so a food can be measured by weight ("g", the default and
what every existing food is) or by volume ("ml", for liquids a parent enters by
millilitres). Nutrition is stored per 100 of this unit; recipe amounts in mL/
fl oz/cup/tbsp/tsp convert to it without ever needing a density. Existing rows
backfill to "g", so nothing changes for solids.
"""
from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "foods",
        sa.Column("base_unit", sa.String(length=2), nullable=False, server_default="g"),
    )


def downgrade() -> None:
    op.drop_column("foods", "base_unit")
