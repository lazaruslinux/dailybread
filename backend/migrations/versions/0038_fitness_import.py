"""The fitness layer: imported daily metrics, workouts, ingest tokens

Revision ID: 0038
Revises: 0037
Create Date: 2026-07-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingest_tokens",
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("token_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "fitness_daily",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("family_id", sa.Integer, sa.ForeignKey("families.id"), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date_for", sa.Date, nullable=False),
        sa.Column("metric", sa.String(30), nullable=False),
        sa.Column("value", sa.Float, nullable=False),
        sa.Column("unit", sa.String(20), nullable=False),
        sa.UniqueConstraint("user_id", "date_for", "metric"),
    )
    op.create_index("ix_fitness_daily_family_id", "fitness_daily", ["family_id"])
    op.create_index("ix_fitness_daily_user_id", "fitness_daily", ["user_id"])
    op.create_index("ix_fitness_daily_date_for", "fitness_daily", ["date_for"])
    op.create_table(
        "workouts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("family_id", sa.Integer, sa.ForeignKey("families.id"), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(64), nullable=True),
        sa.Column("activity", sa.String(80), nullable=False),
        sa.Column("started_at", sa.DateTime, nullable=False),
        sa.Column("ended_at", sa.DateTime, nullable=True),
        sa.Column("duration_s", sa.Float, nullable=True),
        sa.Column("kcal", sa.Float, nullable=True),
        sa.Column("distance_m", sa.Float, nullable=True),
        sa.Column("avg_hr", sa.Float, nullable=True),
        sa.Column("source", sa.String(20), nullable=False, server_default="apple"),
        sa.UniqueConstraint("user_id", "external_id"),
    )
    op.create_index("ix_workouts_family_id", "workouts", ["family_id"])
    op.create_index("ix_workouts_user_id", "workouts", ["user_id"])
    op.create_index("ix_workouts_started_at", "workouts", ["started_at"])


def downgrade() -> None:
    op.drop_table("workouts")
    op.drop_table("fitness_daily")
    op.drop_table("ingest_tokens")
