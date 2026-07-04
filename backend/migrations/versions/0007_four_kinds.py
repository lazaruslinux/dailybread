"""Four card kinds

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-04

Grows the item_kind enum from three kinds to four: routine stays, todo is
renamed task, and event splits into activity and appointment. Existing event
rows map to appointment (the ones in the wild are meetings). Done as a
type-swap rather than ALTER TYPE ... ADD VALUE so the whole thing runs inside
one transaction (a freshly added enum value can't be used in the same
transaction it's created in).
"""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE TYPE item_kind_new AS ENUM ('routine', 'task', 'activity', 'appointment')")
    op.execute(
        "ALTER TABLE items ALTER COLUMN kind TYPE item_kind_new USING ("
        "CASE kind::text "
        "WHEN 'todo' THEN 'task' "
        "WHEN 'event' THEN 'appointment' "
        "ELSE kind::text "
        "END::item_kind_new)"
    )
    op.execute("DROP TYPE item_kind")
    op.execute("ALTER TYPE item_kind_new RENAME TO item_kind")


def downgrade() -> None:
    # Lossy: activities collapse back into events alongside appointments, since
    # the old enum had no activity concept.
    op.execute("CREATE TYPE item_kind_old AS ENUM ('routine', 'todo', 'event')")
    op.execute(
        "ALTER TABLE items ALTER COLUMN kind TYPE item_kind_old USING ("
        "CASE kind::text "
        "WHEN 'task' THEN 'todo' "
        "WHEN 'activity' THEN 'event' "
        "WHEN 'appointment' THEN 'event' "
        "ELSE kind::text "
        "END::item_kind_old)"
    )
    op.execute("DROP TYPE item_kind")
    op.execute("ALTER TYPE item_kind_old RENAME TO item_kind")
