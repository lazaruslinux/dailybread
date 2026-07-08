"""Meals: the family's planned menu

Revision ID: 0019
Revises: 0018
Create Date: 2026-07-07

One row per (family, date, slot): a saved recipe or a free-text title. The
slot enum carries breakfast/lunch/dinner from day one even though the UI
plans dinner only, so widening later is not a schema change. recipe_id is
ON DELETE SET NULL — removing a recipe un-plans the nights that used it
without deleting the rows.
"""
from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "meals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("family_id", sa.Integer(), sa.ForeignKey("families.id"), nullable=False),
        sa.Column("date_for", sa.Date(), nullable=False),
        # The inline Enum creates the pg type on table create; don't also
        # .create() it separately (the double-create gotcha from 0014).
        sa.Column(
            "slot",
            sa.Enum("breakfast", "lunch", "dinner", name="meal_slot"),
            nullable=False,
        ),
        sa.Column(
            "recipe_id",
            sa.Integer(),
            sa.ForeignKey("recipes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("custom_title", sa.String(length=120), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("family_id", "date_for", "slot", name="uq_meal_family_day_slot"),
    )
    op.create_index("ix_meals_family_id", "meals", ["family_id"])
    op.create_index("ix_meals_date_for", "meals", ["date_for"])


def downgrade() -> None:
    op.drop_index("ix_meals_date_for", table_name="meals")
    op.drop_index("ix_meals_family_id", table_name="meals")
    op.drop_table("meals")
    op.execute("DROP TYPE meal_slot")
