"""Multiple assignees per card

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-04

Replaces items.assignee_id (one member, or NULL for the whole family) with an
item_assignees join table so a card can be for several members at once. An
empty set of rows now means "whole family". Existing single assignments are
carried over one-to-one; whole-family cards (assignee_id NULL) simply get no
rows, which is the new way of saying the same thing.
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "item_assignees",
        sa.Column(
            "item_id",
            sa.Integer(),
            sa.ForeignKey("items.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    # Carry existing assignments across. NULL assignee_id (whole family) makes
    # no row, which is exactly how "whole family" is expressed from now on.
    op.execute(
        "INSERT INTO item_assignees (item_id, user_id) "
        "SELECT id, assignee_id FROM items WHERE assignee_id IS NOT NULL"
    )

    op.drop_column("items", "assignee_id")


def downgrade() -> None:
    # Lossy by nature: a card with several assignees keeps only its lowest
    # user id when collapsing back to a single column.
    op.add_column(
        "items",
        sa.Column(
            "assignee_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.execute(
        "UPDATE items SET assignee_id = ("
        "SELECT min(user_id) FROM item_assignees WHERE item_assignees.item_id = items.id)"
    )
    op.drop_table("item_assignees")
