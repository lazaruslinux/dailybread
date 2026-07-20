"""Health-check fields on foods.

Four nullable columns the barcode health check reads: the raw label ingredient
string, added sugar per 100 of the base unit (alongside the macros), the Open
Food Facts additives_tags list comma-joined ("en:e102,en:e211" — Text on
purpose, never a JSON column), and the NOVA processing class (1-4). Custom foods
carry none of these; cache rows fill them in on a scan and heal on a rescan.

Revision ID: 0054
Revises: 0053
Create Date: 2026-07-20
"""
from alembic import op
import sqlalchemy as sa

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("foods", sa.Column("ingredients_text", sa.Text(), nullable=True))
    op.add_column("foods", sa.Column("added_sugar_g", sa.Float(), nullable=True))
    op.add_column("foods", sa.Column("additives", sa.Text(), nullable=True))
    op.add_column("foods", sa.Column("nova_group", sa.SmallInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("foods", "nova_group")
    op.drop_column("foods", "additives")
    op.drop_column("foods", "added_sugar_g")
    op.drop_column("foods", "ingredients_text")
