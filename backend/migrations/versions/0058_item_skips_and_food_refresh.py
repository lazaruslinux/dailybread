"""Skipped occurrences of a repeating card, and an age stamp on cached foods.

Outlook's "open this occurrence": one day of a repeating appointment can be
deleted outright, or detached into its own standalone card. Either way the date
is carved out of the series, and item_skips is that record - the single thing
every surface (board, calendar, reminder loop, digest) consults before drawing
or reminding about a day.

foods.fetched_at is when a shared cache row's nutrition was last pulled from
its source. Sources fix their own data (Open Food Facts corrected a syrup whose
energy was per 100 g beside carbs per 100 mL) and our cache rows never refetched,
so the mistake served forever. Deliberately NOT backfilled: NULL reads as
unknown-age, which counts as stale, so every existing row refreshes on its next
scan - which is also what fills in the other new column.

foods.density_g_per_ml is what a millilitre of the food weighs, read off labels
that state a serving both ways ("1 tbsp (21 g)"). It lets the diary log a food
in any unit, weight or volume, and convert honestly; NULL means the label never
said and water is assumed.

Revision ID: 0058
Revises: 0057
Create Date: 2026-08-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "item_skips",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "item_id",
            sa.Integer(),
            sa.ForeignKey("items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date_for", sa.Date(), nullable=False),
        sa.UniqueConstraint("item_id", "date_for", name="uq_item_skip_day"),
    )
    op.create_index("ix_item_skips_item_id", "item_skips", ["item_id"])

    op.add_column("foods", sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("foods", sa.Column("density_g_per_ml", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("foods", "density_g_per_ml")
    op.drop_column("foods", "fetched_at")
    op.drop_index("ix_item_skips_item_id", table_name="item_skips")
    op.drop_table("item_skips")
