"""Kid mode: birthdates and parent-approved check-offs

Revision ID: 0026
Revises: 0025
Create Date: 2026-07-08

users.birthdate lets the app tell minors from grown children (no birthdate =
minor, the safe default). completions gains pending/approved_by_id so a
minor's check-off can wait for a parent to make it official: approval promotes
the same row in place, keeping the (item, user, day) uniqueness intact.
"""
from alembic import op
import sqlalchemy as sa

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("birthdate", sa.Date(), nullable=True))
    op.add_column(
        "completions",
        sa.Column("pending", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "completions",
        sa.Column(
            "approved_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("completions", "approved_by_id")
    op.drop_column("completions", "pending")
    op.drop_column("users", "birthdate")
