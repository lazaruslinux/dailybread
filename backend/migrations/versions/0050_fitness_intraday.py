"""Hourly fitness buckets for the time-of-day charts.

The daily totals in fitness_daily stay as they are; this adds a parallel
per-hour store for the metrics that read well by time of day (steps,
active_kcal, distance, hr). Re-imports upsert per (member, day, metric, hour),
so the exporter can resend windows safely, same as the daily table.

Revision ID: 0050
Revises: 0049
Create Date: 2026-07-13
"""
from alembic import op
import sqlalchemy as sa

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fitness_intraday",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("family_id", sa.Integer(), sa.ForeignKey("families.id"), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date_for", sa.Date(), nullable=False),
        sa.Column("metric", sa.String(length=30), nullable=False),
        sa.Column("hour", sa.Integer(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=False),
        sa.UniqueConstraint(
            "user_id", "date_for", "metric", "hour", name="uq_fitness_intraday"
        ),
    )
    op.create_index("ix_fitness_intraday_family_id", "fitness_intraday", ["family_id"])
    op.create_index("ix_fitness_intraday_user_id", "fitness_intraday", ["user_id"])
    op.create_index("ix_fitness_intraday_date_for", "fitness_intraday", ["date_for"])


def downgrade() -> None:
    op.drop_index("ix_fitness_intraday_date_for", table_name="fitness_intraday")
    op.drop_index("ix_fitness_intraday_user_id", table_name="fitness_intraday")
    op.drop_index("ix_fitness_intraday_family_id", table_name="fitness_intraday")
    op.drop_table("fitness_intraday")
