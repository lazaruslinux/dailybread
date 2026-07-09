"""Dinner voting: candidates and one vote per member per night

Revision ID: 0033
Revises: 0032
Create Date: 2026-07-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dinner_options",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("family_id", sa.Integer(), sa.ForeignKey("families.id"), nullable=False),
        sa.Column("date_for", sa.Date(), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column(
            "recipe_id", sa.Integer(), sa.ForeignKey("recipes.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_dinner_options_family_id", "dinner_options", ["family_id"])
    op.create_index("ix_dinner_options_date_for", "dinner_options", ["date_for"])

    op.create_table(
        "dinner_votes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("family_id", sa.Integer(), sa.ForeignKey("families.id"), nullable=False),
        sa.Column("date_for", sa.Date(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "option_id",
            sa.Integer(),
            sa.ForeignKey("dinner_options.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("family_id", "date_for", "user_id", name="uq_dinner_vote_night"),
    )
    op.create_index("ix_dinner_votes_family_id", "dinner_votes", ["family_id"])
    op.create_index("ix_dinner_votes_date_for", "dinner_votes", ["date_for"])
    op.create_index("ix_dinner_votes_option_id", "dinner_votes", ["option_id"])


def downgrade() -> None:
    op.drop_table("dinner_votes")
    op.drop_table("dinner_options")
