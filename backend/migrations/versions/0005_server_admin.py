"""Server admin (instance owner)

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-04

Adds users.is_owner: the single "server admin" for the whole install, as
distinct from a family/parent admin (is_admin). Only the owner may invite new
households onto the instance. The bootstrap account is the owner; on an
existing install the earliest account (the original bootstrap) is backfilled
as owner so nothing needs re-setup.
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_owner", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # The original bootstrap account is the instance owner. On an existing
    # install that's the lowest user id; a fresh install has no rows to touch.
    bind = op.get_bind()
    bind.execute(
        sa.text("UPDATE users SET is_owner = true WHERE id = (SELECT min(id) FROM users)")
    )
    # Drop the server_default so the flag is set explicitly by the app going
    # forward (bootstrap sets it True, every other account leaves it False).
    op.alter_column("users", "is_owner", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "is_owner")
