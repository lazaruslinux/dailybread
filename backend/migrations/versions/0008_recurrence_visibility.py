"""Recurrence, ownership/visibility, and per-person completion

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-05

Three changes that land together because they all reshape the items and
completions tables:

1. Recurrence. Routines stop meaning "every day, forever" and gain a schedule
   (weekly on chosen days, every N weeks, or monthly on a day-of-month).
   Existing routines are backfilled as weekly / all seven days / interval 1, so
   they keep behaving exactly as before on deploy.

2. Ownership + visibility. Items gain an owner (the creator) and a household
   visibility (personal / assigned / family). New cards will default to
   personal, but every EXISTING card is backfilled to family so nothing
   disappears from anyone's board on deploy; owner is set to the family's first
   parent.

3. Per-person completion. The completions unique constraint moves from
   (item, day) to (item, member, day) so each assignee can check a shared
   routine independently. Existing rows already satisfy the finer constraint
   (there was at most one per item/day), so no data needs cleaning first.
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- enum types -----------------------------------------------------------
    op.execute("CREATE TYPE item_visibility AS ENUM ('private', 'family')")
    op.execute("CREATE TYPE repeat_type AS ENUM ('weekly', 'monthly')")

    visibility = sa.Enum("private", "family", name="item_visibility", create_type=False)
    repeat = sa.Enum("weekly", "monthly", name="repeat_type", create_type=False)

    # --- ownership ------------------------------------------------------------
    op.add_column(
        "items",
        sa.Column(
            "owner_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_items_owner_id", "items", ["owner_id"])
    # Give every existing card an owner: the family's first parent (lowest id),
    # falling back to the family's first member if a family somehow has none.
    op.execute(
        "UPDATE items i SET owner_id = ("
        "  SELECT u.id FROM users u WHERE u.family_id = i.family_id "
        "  ORDER BY (u.role = 'parent') DESC, u.id LIMIT 1)"
    )

    # --- visibility -----------------------------------------------------------
    op.add_column("items", sa.Column("visibility", visibility, nullable=True))
    # Preserve today's behavior: every existing card is whole-family visible.
    op.execute("UPDATE items SET visibility = 'family'")
    op.alter_column("items", "visibility", nullable=False, server_default="private")

    # --- future feed flag (Phase E; not surfaced yet) -------------------------
    op.add_column(
        "items",
        sa.Column("shared_to_feed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute("UPDATE items SET shared_to_feed = true WHERE kind = 'activity'")

    # --- recurrence -----------------------------------------------------------
    op.add_column("items", sa.Column("repeat_type", repeat, nullable=True))
    op.add_column("items", sa.Column("repeat_days", sa.Integer(), nullable=True))
    op.add_column(
        "items",
        sa.Column("repeat_interval", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column("items", sa.Column("repeat_anchor", sa.Date(), nullable=True))
    op.add_column("items", sa.Column("repeat_month_day", sa.Integer(), nullable=True))
    # Existing routines become plain daily routines (all seven weekday bits).
    op.execute(
        "UPDATE items SET repeat_type = 'weekly', repeat_days = 127, "
        "repeat_anchor = (created_at AT TIME ZONE 'UTC')::date WHERE kind = 'routine'"
    )

    # --- per-person completion ------------------------------------------------
    op.drop_constraint("uq_completion_item_day", "completions", type_="unique")
    op.create_unique_constraint(
        "uq_completion_item_user_day", "completions", ["item_id", "user_id", "date_for"]
    )


def downgrade() -> None:
    # Per-person completion back to one shared check. Lossy: if a shared routine
    # was completed by several members on a day, collapsing to (item, day) would
    # collide, so drop all but the earliest per item/day first.
    op.execute(
        "DELETE FROM completions c USING completions d "
        "WHERE c.item_id = d.item_id AND c.date_for = d.date_for AND c.id > d.id"
    )
    op.drop_constraint("uq_completion_item_user_day", "completions", type_="unique")
    op.create_unique_constraint(
        "uq_completion_item_day", "completions", ["item_id", "date_for"]
    )

    op.drop_column("items", "repeat_month_day")
    op.drop_column("items", "repeat_anchor")
    op.drop_column("items", "repeat_interval")
    op.drop_column("items", "repeat_days")
    op.drop_column("items", "repeat_type")
    op.drop_column("items", "shared_to_feed")
    op.drop_column("items", "visibility")
    op.drop_index("ix_items_owner_id", table_name="items")
    op.drop_column("items", "owner_id")

    op.execute("DROP TYPE repeat_type")
    op.execute("DROP TYPE item_visibility")
