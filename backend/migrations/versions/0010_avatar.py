"""Avatar photo timestamp on users

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-05

Adds users.avatar_updated_at: NULL means the member has no uploaded photo (the
UI draws generated initials instead); a timestamp means a photo exists and also
serves as the cache-busting version for its fixed image URL. The image bytes
live on disk under MEDIA_ROOT, not in the database.
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("avatar_updated_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "avatar_updated_at")
