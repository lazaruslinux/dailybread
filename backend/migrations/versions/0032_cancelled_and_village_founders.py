"""Cancelled occurrences and village founders

Revision ID: 0032
Revises: 0031
Create Date: 2026-07-09

Appointments and activities can now be CANCELLED (a resolved-but-not-done
mark on the completions slot), and villages remember their founding family,
which alone may delete the village outright. Existing villages adopt their
earliest member as founder.
"""
from alembic import op
import sqlalchemy as sa

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "completions",
        sa.Column("cancelled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "villages",
        sa.Column(
            "created_by_family_id",
            sa.Integer(),
            sa.ForeignKey("families.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.execute(
        """
        UPDATE villages v SET created_by_family_id = (
            SELECT vf.family_id FROM village_families vf
            WHERE vf.village_id = v.id
            ORDER BY vf.joined_at, vf.id LIMIT 1
        )
        WHERE v.created_by_family_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("villages", "created_by_family_id")
    op.drop_column("completions", "cancelled")
