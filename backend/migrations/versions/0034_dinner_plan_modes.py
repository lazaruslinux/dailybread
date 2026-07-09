"""Dinner plan: four standing modes replace custom ballots

Revision ID: 0034
Revises: 0033
Create Date: 2026-07-09

The dinner question becomes a standing four-way pick (self-serve, homemade,
go out, delivery) with a short detail and an optional recipe on homemade.
Dynamic per-night options go away; existing votes (preview-only data) are
cleared rather than migrated.
"""
from alembic import op
import sqlalchemy as sa

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None

dinner_choice = sa.Enum(
    "self_serve", "homemade", "go_out", "delivery", name="dinner_choice"
)


def upgrade() -> None:
    op.execute("DELETE FROM dinner_votes")
    dinner_choice.create(op.get_bind(), checkfirst=True)
    op.drop_column("dinner_votes", "option_id")
    op.add_column("dinner_votes", sa.Column("choice", dinner_choice, nullable=False))
    op.add_column(
        "dinner_votes",
        sa.Column("detail", sa.String(30), nullable=False, server_default=""),
    )
    op.add_column(
        "dinner_votes",
        sa.Column(
            "recipe_id",
            sa.Integer(),
            sa.ForeignKey("recipes.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.drop_table("dinner_options")


def downgrade() -> None:
    raise NotImplementedError("the custom-ballot dinner vote is gone for good")
