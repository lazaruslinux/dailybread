"""Signup invites: code-based onboarding onto the install

Revision ID: 0030
Revises: 0029
Create Date: 2026-07-09

The server owner mints a short-lived invite code carrying the invitee's name
and username; redeeming it on the sign-in screen creates the account (invitee
picks their own password) and leads into the create-your-family wizard.
Replaces the owner typing a temporary password for new households.
"""
from alembic import op
import sqlalchemy as sa

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "signup_invites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("username", sa.String(50), nullable=False, unique=True),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column(
            "invited_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_signup_invites_code_hash", "signup_invites", ["code_hash"])
    op.create_index("ix_signup_invites_username", "signup_invites", ["username"])


def downgrade() -> None:
    op.drop_index("ix_signup_invites_username", table_name="signup_invites")
    op.drop_index("ix_signup_invites_code_hash", table_name="signup_invites")
    op.drop_table("signup_invites")
