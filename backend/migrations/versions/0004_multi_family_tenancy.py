"""Multi-family tenancy

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-03

Adds the families table and a family_id on users, items, grocery_lists, and
grocery_items. An already-running single-family install is folded into one
default family named "Home" so nothing existing moves or disappears; the
NOT NULL constraints go on only after that backfill.
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

_SCOPED = ("items", "grocery_lists", "grocery_items")


def upgrade() -> None:
    op.create_table(
        "families",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # users.family_id stays nullable permanently: NULL marks a new-household
    # account that hasn't run its create-your-family wizard yet.
    op.add_column(
        "users",
        sa.Column("family_id", sa.Integer(), sa.ForeignKey("families.id"), nullable=True),
    )
    op.create_index("ix_users_family_id", "users", ["family_id"])

    for table in _SCOPED:
        op.add_column(
            table,
            sa.Column("family_id", sa.Integer(), sa.ForeignKey("families.id"), nullable=True),
        )
        op.create_index(f"ix_{table}_family_id", table, ["family_id"])

    # Backfill: if this install already has users, they are one household.
    bind = op.get_bind()
    has_users = bind.execute(sa.text("SELECT 1 FROM users LIMIT 1")).scalar()
    if has_users:
        family_id = bind.execute(
            sa.text("INSERT INTO families (name, created_at) VALUES ('Home', now()) RETURNING id")
        ).scalar()
        for table in ("users", *_SCOPED):
            bind.execute(
                sa.text(f"UPDATE {table} SET family_id = :fid"), {"fid": family_id}
            )

    # Data tables must always belong to a family; only users may float.
    for table in _SCOPED:
        op.alter_column(table, "family_id", nullable=False)


def downgrade() -> None:
    for table in ("users", *_SCOPED):
        op.drop_index(f"ix_{table}_family_id", table_name=table)
        op.drop_column(table, "family_id")
    op.drop_table("families")
