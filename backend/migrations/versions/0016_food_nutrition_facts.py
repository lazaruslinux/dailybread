"""Full Nutrition Facts label + named servings for foods

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-07

Extends foods with the rest of the Nutrition Facts label (saturated/trans fat,
cholesterol, sodium, fiber, sugar) alongside the calories + base macros from
0014, and adds a food_servings table so a food can carry several named
real-world portions (Cronometer-style). Nutrition stays per-100g; a serving's
gram weight is what converts a portion to those values.
"""
from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

# per-100g; cholesterol/sodium in mg (as labels print), the rest in grams.
_NEW_COLS = (
    "saturated_fat_g",
    "trans_fat_g",
    "cholesterol_mg",
    "sodium_mg",
    "fiber_g",
    "sugar_g",
)


def upgrade() -> None:
    for col in _NEW_COLS:
        op.add_column("foods", sa.Column(col, sa.Float(), nullable=True))
    op.create_table(
        "food_servings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "food_id",
            sa.Integer(),
            sa.ForeignKey("foods.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("grams", sa.Float(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_food_servings_food_id", "food_servings", ["food_id"])


def downgrade() -> None:
    op.drop_index("ix_food_servings_food_id", table_name="food_servings")
    op.drop_table("food_servings")
    for col in reversed(_NEW_COLS):
        op.drop_column("foods", col)
