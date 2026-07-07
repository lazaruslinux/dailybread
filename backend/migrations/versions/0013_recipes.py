"""Family recipe box

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-06

Adds the recipes table: a saved family recipe with its ingredients, steps, and
per-serving nutrition (entered by the cook, nullable until worked out). The week
meal planner (a later migration) points meals at these so choosing a night's
dinner is just picking a recipe.
"""
from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recipes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("family_id", sa.Integer(), sa.ForeignKey("families.id"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("servings", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("calories", sa.Integer(), nullable=True),
        sa.Column("protein_g", sa.Integer(), nullable=True),
        sa.Column("carbs_g", sa.Integer(), nullable=True),
        sa.Column("fat_g", sa.Integer(), nullable=True),
        sa.Column("ingredients", sa.Text(), nullable=False, server_default=""),
        sa.Column("steps", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_recipes_family_id", "recipes", ["family_id"])


def downgrade() -> None:
    op.drop_index("ix_recipes_family_id", table_name="recipes")
    op.drop_table("recipes")
