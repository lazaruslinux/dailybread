"""Villages: private circles of linked families

Revision ID: 0029
Revises: 0028
Create Date: 2026-07-09

Adds villages (with a hashed one-time invite code), village_families
(membership, a family can belong to several), village_recipes (the shared
shelf), and users.village_presence (per-member opt-in to share mood/status
across the village). Nothing is backfilled: every install starts with no
villages and every member opted out.
"""
from alembic import op
import sqlalchemy as sa

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "villages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        # SHA-256 hex of the one active invite code; NULL when none is live.
        sa.Column("invite_code_hash", sa.String(64), nullable=True),
        sa.Column("invite_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "village_families",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "village_id",
            sa.Integer(),
            sa.ForeignKey("villages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "family_id",
            sa.Integer(),
            sa.ForeignKey("families.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("village_id", "family_id", name="uq_village_family"),
    )
    op.create_index("ix_village_families_village_id", "village_families", ["village_id"])
    op.create_index("ix_village_families_family_id", "village_families", ["family_id"])

    op.create_table(
        "village_recipes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "village_id",
            sa.Integer(),
            sa.ForeignKey("villages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "recipe_id",
            sa.Integer(),
            sa.ForeignKey("recipes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Owner family denormalized at share time (a recipe never changes
        # families): attribution without a join, one-query cleanup on leave.
        sa.Column(
            "family_id", sa.Integer(), sa.ForeignKey("families.id"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("village_id", "recipe_id", name="uq_village_recipe"),
    )
    op.create_index("ix_village_recipes_village_id", "village_recipes", ["village_id"])
    op.create_index("ix_village_recipes_recipe_id", "village_recipes", ["recipe_id"])
    op.create_index("ix_village_recipes_family_id", "village_recipes", ["family_id"])

    op.add_column(
        "users",
        sa.Column(
            "village_presence",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "village_presence")
    op.drop_index("ix_village_recipes_family_id", table_name="village_recipes")
    op.drop_index("ix_village_recipes_recipe_id", table_name="village_recipes")
    op.drop_index("ix_village_recipes_village_id", table_name="village_recipes")
    op.drop_table("village_recipes")
    op.drop_index("ix_village_families_family_id", table_name="village_families")
    op.drop_index("ix_village_families_village_id", table_name="village_families")
    op.drop_table("village_families")
    op.drop_table("villages")
