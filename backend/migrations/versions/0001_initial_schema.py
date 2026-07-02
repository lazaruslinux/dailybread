"""Initial schema: users, items, completions, moods

Revision ID: 0001
Revises:
Create Date: 2026-07-02

"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

user_role = sa.Enum("parent", "child", name="user_role")
item_kind = sa.Enum("routine", "todo", "event", name="item_kind")
mood_level = sa.Enum("sunny", "partly", "cloudy", "rainy", "stormy", name="mood_level")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(50), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", user_role, nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("bio", sa.String(500), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    op.create_table(
        "items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", item_kind, nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("notes", sa.String(300), nullable=False, server_default=""),
        sa.Column(
            "assignee_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("time_of_day", sa.Time(), nullable=True),
        sa.Column("date_for", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "completions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "item_id",
            sa.Integer(),
            sa.ForeignKey("items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("date_for", sa.Date(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("item_id", "date_for", name="uq_completion_item_day"),
    )
    op.create_index("ix_completions_item_id", "completions", ["item_id"])
    op.create_index("ix_completions_date_for", "completions", ["date_for"])

    op.create_table(
        "moods",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("date_for", sa.Date(), nullable=False),
        sa.Column("level", mood_level, nullable=False),
        sa.Column("hidden", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "date_for", name="uq_mood_user_day"),
    )
    op.create_index("ix_moods_user_id", "moods", ["user_id"])
    op.create_index("ix_moods_date_for", "moods", ["date_for"])


def downgrade() -> None:
    op.drop_table("moods")
    op.drop_table("completions")
    op.drop_table("items")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
    mood_level.drop(op.get_bind())
    item_kind.drop(op.get_bind())
    user_role.drop(op.get_bind())
