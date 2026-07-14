"""Shared village events: pointers, per-family RSVPs, attendees, and the
columns that carry them.

village_events points at the organizer's own Item (the VillageRecipe pattern);
village_event_rsvps holds one changeable answer per (event, family); the
attendee rows name who from that family is coming. items.village_event_id
marks a MATERIALIZED COPY on an attendee family's board — ondelete CASCADE so
a dead event takes its copies with it. families.share_kid_avatars is the
parent-controlled "show our kids' photos to our villages" opt-in; items.location is
a general-purpose place field.

Revision ID: 0052
Revises: 0051
Create Date: 2026-07-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None

rsvp_status = sa.Enum("going", "maybe", "cant", name="rsvp_status")


def upgrade() -> None:
    op.create_table(
        "village_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "village_id",
            sa.Integer(),
            sa.ForeignKey("villages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "item_id",
            sa.Integer(),
            sa.ForeignKey("items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("family_id", sa.Integer(), sa.ForeignKey("families.id"), nullable=False),
        sa.Column(
            "shared_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("village_id", "item_id", name="uq_village_event"),
    )
    op.create_index("ix_village_events_village_id", "village_events", ["village_id"])
    op.create_index("ix_village_events_item_id", "village_events", ["item_id"])
    op.create_index("ix_village_events_family_id", "village_events", ["family_id"])

    # create_table creates the rsvp_status type itself; downgrade drops it
    # explicitly since drop_table leaves types behind.
    op.create_table(
        "village_event_rsvps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "event_id",
            sa.Integer(),
            sa.ForeignKey("village_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "family_id",
            sa.Integer(),
            sa.ForeignKey("families.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", rsvp_status, nullable=False),
        sa.Column(
            "set_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("event_id", "family_id", name="uq_event_rsvp_family"),
    )
    op.create_index("ix_village_event_rsvps_event_id", "village_event_rsvps", ["event_id"])
    op.create_index("ix_village_event_rsvps_family_id", "village_event_rsvps", ["family_id"])

    op.create_table(
        "village_event_attendees",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "rsvp_id",
            sa.Integer(),
            sa.ForeignKey("village_event_rsvps.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.UniqueConstraint("rsvp_id", "user_id", name="uq_event_attendee"),
    )
    op.create_index(
        "ix_village_event_attendees_rsvp_id", "village_event_attendees", ["rsvp_id"]
    )

    op.add_column(
        "families",
        sa.Column("share_kid_avatars", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("items", sa.Column("location", sa.String(length=120), nullable=True))
    op.add_column(
        "items",
        sa.Column(
            "village_event_id",
            sa.Integer(),
            sa.ForeignKey("village_events.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index("ix_items_village_event_id", "items", ["village_event_id"])


def downgrade() -> None:
    op.drop_index("ix_items_village_event_id", table_name="items")
    op.drop_column("items", "village_event_id")
    op.drop_column("items", "location")
    op.drop_column("families", "share_kid_avatars")
    op.drop_index("ix_village_event_attendees_rsvp_id", table_name="village_event_attendees")
    op.drop_table("village_event_attendees")
    op.drop_index("ix_village_event_rsvps_family_id", table_name="village_event_rsvps")
    op.drop_index("ix_village_event_rsvps_event_id", table_name="village_event_rsvps")
    op.drop_table("village_event_rsvps")
    rsvp_status.drop(op.get_bind(), checkfirst=True)
    op.drop_index("ix_village_events_family_id", table_name="village_events")
    op.drop_index("ix_village_events_item_id", table_name="village_events")
    op.drop_index("ix_village_events_village_id", table_name="village_events")
    op.drop_table("village_events")
