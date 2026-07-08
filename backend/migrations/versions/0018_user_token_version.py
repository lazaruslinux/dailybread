"""User token version (session invalidation on password change)

Revision ID: 0018
Revises: 0017
Create Date: 2026-07-07

Adds users.token_version. Session JWTs carry the version they were minted
under ("ver" claim); a request whose token version doesn't match the account's
current one is refused. Changing or resetting a password bumps the version,
which is what actually ends that account's existing sessions — the JWTs are
stateless and would otherwise stay valid for their full sliding lifetime.
Existing rows backfill to 0, and tokens minted before this change (no "ver"
claim) read as version 0, so nobody is logged out by the migration itself.
"""
from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("users", "token_version")
