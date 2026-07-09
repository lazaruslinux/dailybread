"""Morning digest: the sent-log that keeps it to one per member per day

Revision ID: 0027
Revises: 0026
Create Date: 2026-07-08

digest_log claims a (member, day) pair the first morning tick that handles
them, so restarts and racing ticks never send a second good-morning.
"""
from alembic import op
import sqlalchemy as sa

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "digest_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date_for", sa.Date(), nullable=False),
        sa.UniqueConstraint("user_id", "date_for", name="uq_digest_user_day"),
    )
    op.create_index("ix_digest_log_user_id", "digest_log", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_digest_log_user_id", table_name="digest_log")
    op.drop_table("digest_log")
