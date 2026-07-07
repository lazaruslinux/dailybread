"""Structured recipe ingredients; drop stored recipe macros

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-07

Recipes stop storing their own macros and free-text ingredients. Instead each
recipe has recipe_ingredients rows — a food plus an amount/unit — and its
nutrition is computed by scaling each food's per-100g macros. This drops the
old calories/protein_g/carbs_g/fat_g and the ingredients text from recipes;
that hand-entered data can't be mapped onto foods, so it does not carry over.
"""
from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recipe_ingredients",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "recipe_id",
            sa.Integer(),
            sa.ForeignKey("recipes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("food_id", sa.Integer(), sa.ForeignKey("foods.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("unit", sa.String(length=4), nullable=False, server_default="g"),
    )
    op.create_index("ix_recipe_ingredients_recipe_id", "recipe_ingredients", ["recipe_id"])
    op.create_index("ix_recipe_ingredients_food_id", "recipe_ingredients", ["food_id"])

    op.drop_column("recipes", "calories")
    op.drop_column("recipes", "protein_g")
    op.drop_column("recipes", "carbs_g")
    op.drop_column("recipes", "fat_g")
    op.drop_column("recipes", "ingredients")


def downgrade() -> None:
    # The old macro/ingredient columns come back empty; their data is gone.
    op.add_column("recipes", sa.Column("ingredients", sa.Text(), nullable=False, server_default=""))
    op.add_column("recipes", sa.Column("fat_g", sa.Integer(), nullable=True))
    op.add_column("recipes", sa.Column("carbs_g", sa.Integer(), nullable=True))
    op.add_column("recipes", sa.Column("protein_g", sa.Integer(), nullable=True))
    op.add_column("recipes", sa.Column("calories", sa.Integer(), nullable=True))

    op.drop_index("ix_recipe_ingredients_food_id", table_name="recipe_ingredients")
    op.drop_index("ix_recipe_ingredients_recipe_id", table_name="recipe_ingredients")
    op.drop_table("recipe_ingredients")
