"""Nutrition diary: personal food logging and per-member targets

Revision ID: 0021
Revises: 0020
Create Date: 2026-07-08

diary_entries hold what one member ate: a snapshot of the served nutrition
computed at log time, with soft references (SET NULL) back to the food or
recipe it came from, so deleting those never rewrites a logged day.
nutrition_targets hold each member's own calorie budget and protein/carbs/fat
percentage split; members without a row use the app default.
"""
from alembic import op
import sqlalchemy as sa

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

diary_slot = sa.Enum("breakfast", "lunch", "dinner", "snack", name="diary_slot")


def upgrade() -> None:
    op.create_table(
        "diary_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("family_id", sa.Integer(), sa.ForeignKey("families.id"), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date_for", sa.Date(), nullable=False),
        sa.Column("slot", diary_slot, nullable=False),
        sa.Column("time_of_day", sa.Time(), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("brand", sa.String(120), nullable=False, server_default=""),
        sa.Column(
            "food_id",
            sa.Integer(),
            sa.ForeignKey("foods.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "recipe_id",
            sa.Integer(),
            sa.ForeignKey("recipes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(4), nullable=False, server_default="g"),
        sa.Column("label", sa.String(60), nullable=True),
        sa.Column("calories", sa.Float(), nullable=True),
        sa.Column("protein_g", sa.Float(), nullable=True),
        sa.Column("carbs_g", sa.Float(), nullable=True),
        sa.Column("fat_g", sa.Float(), nullable=True),
        sa.Column("saturated_fat_g", sa.Float(), nullable=True),
        sa.Column("trans_fat_g", sa.Float(), nullable=True),
        sa.Column("cholesterol_mg", sa.Float(), nullable=True),
        sa.Column("sodium_mg", sa.Float(), nullable=True),
        sa.Column("fiber_g", sa.Float(), nullable=True),
        sa.Column("sugar_g", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_diary_entries_family_id", "diary_entries", ["family_id"])
    op.create_index("ix_diary_entries_user_id", "diary_entries", ["user_id"])
    op.create_index("ix_diary_entries_date_for", "diary_entries", ["date_for"])
    op.create_index("ix_diary_entries_food_id", "diary_entries", ["food_id"])
    op.create_index("ix_diary_entries_recipe_id", "diary_entries", ["recipe_id"])

    op.create_table(
        "nutrition_targets",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("calories", sa.Integer(), nullable=False, server_default="2000"),
        sa.Column("protein_pct", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("carbs_pct", sa.Integer(), nullable=False, server_default="40"),
        sa.Column("fat_pct", sa.Integer(), nullable=False, server_default="30"),
    )


def downgrade() -> None:
    op.drop_table("nutrition_targets")
    op.drop_table("diary_entries")
    diary_slot.drop(op.get_bind(), checkfirst=True)
