"""Saved Foods: bookmark a search or barcode result for quick re-use.

A family-scoped pin onto the foods table; the food row itself is the shared
cache row (or the family's custom food), so unpinning never loses nutrition
data a recipe or diary snapshot relies on.

Revision ID: 0049
Revises: 0048
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "saved_foods",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("family_id", sa.Integer(), sa.ForeignKey("families.id"), nullable=False),
        sa.Column(
            "food_id",
            sa.Integer(),
            sa.ForeignKey("foods.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "saved_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("family_id", "food_id", name="uq_saved_food"),
    )
    op.create_index("ix_saved_foods_family_id", "saved_foods", ["family_id"])


def downgrade() -> None:
    op.drop_index("ix_saved_foods_family_id", table_name="saved_foods")
    op.drop_table("saved_foods")
