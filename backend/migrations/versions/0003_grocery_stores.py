"""Per-store grocery lists

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-03

"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "grocery_lists",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    # Existing items keep list_id NULL, which is the General list: nothing
    # the family already wrote down moves or disappears.
    op.add_column(
        "grocery_items",
        sa.Column(
            "list_id",
            sa.Integer(),
            sa.ForeignKey("grocery_lists.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("grocery_items", "list_id")
    op.drop_table("grocery_lists")
