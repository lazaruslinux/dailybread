"""Food database cache + custom foods

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-06

Adds the foods table: per-100g nutrition for a food, either cached from USDA
FoodData Central / Open Food Facts (family_id NULL = shared across the install)
or a family's own custom entry (family_id set). Recipe ingredients reference
these; a recipe's nutrition is computed by scaling each ingredient's amount.
"""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

food_source = sa.Enum("usda", "off", "custom", name="food_source")


def upgrade() -> None:
    bind = op.get_bind()
    food_source.create(bind, checkfirst=True)
    op.create_table(
        "foods",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("family_id", sa.Integer(), sa.ForeignKey("families.id"), nullable=True),
        sa.Column("source", food_source, nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("brand", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("calories", sa.Float(), nullable=True),
        sa.Column("protein_g", sa.Float(), nullable=True),
        sa.Column("carbs_g", sa.Float(), nullable=True),
        sa.Column("fat_g", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_foods_family_id", "foods", ["family_id"])
    op.create_index("ix_foods_source_id", "foods", ["source_id"])


def downgrade() -> None:
    op.drop_index("ix_foods_source_id", table_name="foods")
    op.drop_index("ix_foods_family_id", table_name="foods")
    op.drop_table("foods")
    food_source.drop(op.get_bind(), checkfirst=True)
