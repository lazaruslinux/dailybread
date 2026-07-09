"""Village recipes remember who shared them

Revision ID: 0035
Revises: 0034
Create Date: 2026-07-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "village_recipes",
        sa.Column(
            "shared_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("village_recipes", "shared_by_id")
