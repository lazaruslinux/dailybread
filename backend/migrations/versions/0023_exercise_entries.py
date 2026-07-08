"""Exercise log: workouts whose burn raises the day's energy target

Revision ID: 0023
Revises: 0022
Create Date: 2026-07-08

exercise_entries hold logged workouts (activity, effort, minutes) with the
calories burned snapshotted at log time (MET x latest weight x hours). The
diary adds a day's burn onto that day's energy target.
"""
from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

exercise_effort = sa.Enum("light", "moderate", "vigorous", name="exercise_effort")


def upgrade() -> None:
    op.create_table(
        "exercise_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("family_id", sa.Integer(), sa.ForeignKey("families.id"), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date_for", sa.Date(), nullable=False),
        sa.Column("time_of_day", sa.Time(), nullable=True),
        sa.Column("activity", sa.String(30), nullable=False),
        sa.Column("effort", exercise_effort, nullable=False),
        sa.Column("minutes", sa.Float(), nullable=False),
        sa.Column("kcal", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_exercise_entries_family_id", "exercise_entries", ["family_id"])
    op.create_index("ix_exercise_entries_user_id", "exercise_entries", ["user_id"])
    op.create_index("ix_exercise_entries_date_for", "exercise_entries", ["date_for"])


def downgrade() -> None:
    op.drop_table("exercise_entries")
    exercise_effort.drop(op.get_bind(), checkfirst=True)
