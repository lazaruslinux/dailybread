"""A kind on every reminder claim, and a place to remember the version.

An appointment now gets two pushes on its day: the lead heads-up before it
starts, and a "Starting now" when it does. reminder_log claimed one row per
(item, day), which let the first push block the second, so the claim gains a
kind. Existing rows are all lead-time claims.

app_meta is server-wide key/value storage. It seeds app_version with the
version this migration upgrades FROM, so the first boot afterwards sees the
version move and announces the update to every parent.

Revision ID: 0057
Revises: 0056
Create Date: 2026-08-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None

# The version being upgraded away from, so the boot after this deploy is the
# one that announces the new one.
PREVIOUS_VERSION = "2.0.1"


def upgrade() -> None:
    op.add_column(
        "reminder_log",
        sa.Column("kind", sa.String(16), nullable=False, server_default="lead"),
    )
    op.drop_constraint("uq_reminder_item_day", "reminder_log", type_="unique")
    op.create_unique_constraint(
        "uq_reminder_item_day_kind", "reminder_log", ["item_id", "date_for", "kind"]
    )

    app_meta = op.create_table(
        "app_meta",
        sa.Column("key", sa.String(32), primary_key=True),
        sa.Column("value", sa.String(64), nullable=False),
    )
    op.bulk_insert(app_meta, [{"key": "app_version", "value": PREVIOUS_VERSION}])


def downgrade() -> None:
    op.drop_table("app_meta")
    op.drop_constraint("uq_reminder_item_day_kind", "reminder_log", type_="unique")
    # The narrower claim can't hold two rows for one day.
    op.execute("DELETE FROM reminder_log WHERE kind <> 'lead'")
    op.create_unique_constraint("uq_reminder_item_day", "reminder_log", ["item_id", "date_for"])
    op.drop_column("reminder_log", "kind")
