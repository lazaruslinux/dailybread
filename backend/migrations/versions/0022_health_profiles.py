"""Health profiles, weigh-ins, and auto calorie targets

Revision ID: 0022
Revises: 0021
Create Date: 2026-07-08

health_profiles hold a member's optional health settings (birthdate, sex,
height, activity, goal); weight_entries log weigh-ins (one per member per
day). Together they feed the computed calorie target (app.health).
nutrition_targets gain a mode column: manual keeps the typed budget, auto
reads the computed one at request time. Existing rows stay manual.
"""
from alembic import op
import sqlalchemy as sa

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

sex = sa.Enum("male", "female", name="sex")
activity_level = sa.Enum(
    "sedentary", "light", "moderate", "active", "very_active", name="activity_level"
)
goal_type = sa.Enum("lose", "maintain", "gain", name="goal_type")
target_mode = sa.Enum("manual", "auto", name="target_mode")


def upgrade() -> None:
    op.create_table(
        "health_profiles",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("birthdate", sa.Date(), nullable=True),
        sa.Column("sex", sex, nullable=True),
        sa.Column("height_cm", sa.Float(), nullable=True),
        sa.Column("activity_level", activity_level, nullable=True),
        sa.Column("goal", goal_type, nullable=True),
        sa.Column("rate_lbs_per_week", sa.Float(), nullable=True),
        sa.Column("goal_weight_kg", sa.Float(), nullable=True),
    )

    op.create_table(
        "weight_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date_for", sa.Date(), nullable=False),
        sa.Column("weight_kg", sa.Float(), nullable=False),
        sa.Column("body_fat_pct", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "date_for"),
    )
    op.create_index("ix_weight_entries_user_id", "weight_entries", ["user_id"])
    op.create_index("ix_weight_entries_date_for", "weight_entries", ["date_for"])

    target_mode.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "nutrition_targets",
        sa.Column("mode", target_mode, nullable=False, server_default="manual"),
    )


def downgrade() -> None:
    op.drop_column("nutrition_targets", "mode")
    target_mode.drop(op.get_bind(), checkfirst=True)
    op.drop_table("weight_entries")
    op.drop_table("health_profiles")
    for e in (goal_type, activity_level, sex):
        e.drop(op.get_bind(), checkfirst=True)
