"""Shared village foods and custom-food folders.

village_foods mirrors village_recipes: a pointer at the owning family's custom
food (their edits show live on the shelf), and "save a copy" is what puts an
independent snapshot in another family's kitchen. foods.folder is a family's
own optional filing label for a custom food (NULL for cache rows and unfiled
custom foods); it never crosses the family wall.

Revision ID: 0053
Revises: 0052
Create Date: 2026-07-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "village_foods",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "village_id",
            sa.Integer(),
            sa.ForeignKey("villages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "food_id",
            sa.Integer(),
            sa.ForeignKey("foods.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Owner family denormalized at share time (a food never changes
        # families): attribution without a join, one-query cleanup on leave.
        sa.Column(
            "family_id", sa.Integer(), sa.ForeignKey("families.id"), nullable=False
        ),
        sa.Column(
            "shared_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("village_id", "food_id", name="uq_village_food"),
    )
    op.create_index("ix_village_foods_village_id", "village_foods", ["village_id"])
    op.create_index("ix_village_foods_food_id", "village_foods", ["food_id"])
    op.create_index("ix_village_foods_family_id", "village_foods", ["family_id"])

    op.add_column("foods", sa.Column("folder", sa.String(length=60), nullable=True))


def downgrade() -> None:
    op.drop_column("foods", "folder")
    op.drop_index("ix_village_foods_family_id", table_name="village_foods")
    op.drop_index("ix_village_foods_food_id", table_name="village_foods")
    op.drop_index("ix_village_foods_village_id", table_name="village_foods")
    op.drop_table("village_foods")
