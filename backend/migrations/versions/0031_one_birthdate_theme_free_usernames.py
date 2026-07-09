"""One birthdate per member, stored themes, invitee-chosen usernames

Revision ID: 0031
Revises: 0030
Create Date: 2026-07-09

Three review items in one: users.birthdate becomes the single birthdate
(backfilled from health_profiles.birthdate, which is then dropped — the
health profile now reads/writes the user's), users gain a stored theme
preference that follows the account across devices, and signup invites stop
pre-claiming a username (the invitee picks their own at redemption).
"""
from alembic import op
import sqlalchemy as sa

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The admin-set users.birthdate wins where both exist (it was the
    # deliberate, parent-entered one); the health profile's fills the gaps.
    op.execute(
        """
        UPDATE users SET birthdate = hp.birthdate
        FROM health_profiles hp
        WHERE hp.user_id = users.id
          AND users.birthdate IS NULL
          AND hp.birthdate IS NOT NULL
        """
    )
    op.drop_column("health_profiles", "birthdate")

    op.add_column("users", sa.Column("theme", sa.String(8), nullable=True))

    op.drop_index("ix_signup_invites_username", table_name="signup_invites")
    op.drop_constraint("signup_invites_username_key", "signup_invites", type_="unique")
    op.drop_column("signup_invites", "username")


def downgrade() -> None:
    op.add_column(
        "signup_invites", sa.Column("username", sa.String(50), nullable=True)
    )
    op.create_unique_constraint(
        "signup_invites_username_key", "signup_invites", ["username"]
    )
    op.create_index("ix_signup_invites_username", "signup_invites", ["username"])
    op.drop_column("users", "theme")
    op.add_column("health_profiles", sa.Column("birthdate", sa.Date(), nullable=True))
