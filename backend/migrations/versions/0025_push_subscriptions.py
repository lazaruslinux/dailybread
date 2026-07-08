"""Web Push: device subscriptions and the sent-reminder log

Revision ID: 0025
Revises: 0024
Create Date: 2026-07-08

push_subscriptions holds each device's push endpoint + encryption keys;
reminder_log records which card/day pairs were already reminded so restarts
never double-send.
"""
from alembic import op
import sqlalchemy as sa

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("family_id", sa.Integer(), sa.ForeignKey("families.id"), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("endpoint", sa.Text(), nullable=False, unique=True),
        sa.Column("p256dh", sa.String(255), nullable=False),
        sa.Column("auth", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_push_subscriptions_family_id", "push_subscriptions", ["family_id"])
    op.create_index("ix_push_subscriptions_user_id", "push_subscriptions", ["user_id"])

    op.create_table(
        "reminder_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "item_id",
            sa.Integer(),
            sa.ForeignKey("items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date_for", sa.Date(), nullable=False),
        sa.UniqueConstraint("item_id", "date_for", name="uq_reminder_item_day"),
    )
    op.create_index("ix_reminder_log_item_id", "reminder_log", ["item_id"])


def downgrade() -> None:
    op.drop_table("reminder_log")
    op.drop_table("push_subscriptions")
