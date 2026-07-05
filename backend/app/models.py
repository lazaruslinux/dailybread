import datetime as dt
import enum

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Time,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Role(str, enum.Enum):
    """A family member is either a parent (admin) or a child."""

    parent = "parent"
    child = "child"


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Family(Base):
    """One household. Every piece of data in the app belongs to exactly one,
    and nothing is ever visible across the boundary."""

    __tablename__ = "families"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # NULL only for a freshly created "new household" account that hasn't run
    # its create-your-family wizard yet; such accounts can't touch any data.
    family_id: Mapped[int | None] = mapped_column(
        ForeignKey("families.id"), nullable=True, index=True
    )
    # Login name, unique and indexed for fast lookups.
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(100))
    # Argon2 hash, never the raw password.
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(SAEnum(Role, name="user_role"), default=Role.child)
    # Can this user manage their own family (add/edit/remove members)? Defaults
    # follow role at creation (parent -> True, child -> False), overridable.
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    # The single "server admin" for the whole install: the only account allowed
    # to invite new households onto the instance. Set once, on the bootstrap
    # account; everyone else is False. Distinct from is_admin, which is
    # family-scoped board management.
    is_owner: Mapped[bool] = mapped_column(Boolean, default=False)
    # Short "about me" for the profile page. Owner-editable only.
    bio: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ItemKind(str, enum.Enum):
    """The four kinds of cards on the board."""

    routine = "routine"  # repeats on a schedule, no single date (brush teeth, soccer)
    task = "task"  # one-off; an optional "due by" date/time (call the dentist)
    activity = "activity"  # a time block you spend on a day (gym, study) — date+time
    appointment = "appointment"  # a fixed commitment (dentist, meeting) — date+time


class RepeatType(str, enum.Enum):
    """How a routine recurs. Only routines carry one; every other kind is NULL.

    weekly: on chosen weekdays (repeat_days), optionally every N weeks.
    monthly: on a day-of-month (repeat_month_day), optionally every N months.
    A plain daily routine is weekly with all seven weekdays selected.
    """

    weekly = "weekly"
    monthly = "monthly"


class Visibility(str, enum.Enum):
    """Who can SEE a card, which is separate from who is assigned to DO it.

    private: the owner and anyone assigned (a card with no assignees is then
    the owner's alone). family: the whole household can see it for awareness,
    but only assignees check it off; non-assignees see it read-only and can
    filter it off their own board. Distinct from shared_to_feed, the future
    cross-household feed axis."""

    private = "private"
    family = "family"


# Who is assigned to DO a card: the people responsible for it, who check it
# off (per-person for routines). This is separate from Visibility, which is who
# can SEE it. An empty list means the owner is the one responsible. If a member
# is deleted their rows here cascade away.
item_assignees = Table(
    "item_assignees",
    Base.metadata,
    Column("item_id", ForeignKey("items.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), index=True)
    # The member who created the card; the anchor for "my own board". SET NULL
    # on delete so a card survives its owner's removal (it falls back to a
    # family-owned card in the visibility check rather than disappearing).
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    kind: Mapped[ItemKind] = mapped_column(SAEnum(ItemKind, name="item_kind"))
    title: Mapped[str] = mapped_column(String(120))
    notes: Mapped[str] = mapped_column(String(300), default="")

    # Who can SEE this card. New cards are private (the owner plus anyone
    # assigned); family puts it on the whole household's board for awareness.
    visibility: Mapped[Visibility] = mapped_column(
        SAEnum(Visibility, name="item_visibility"), default=Visibility.private
    )
    # Future in-instance cross-household feed (Phase E). Not surfaced yet;
    # defaults follow kind at creation (activities shareable, others private).
    shared_to_feed: Mapped[bool] = mapped_column(Boolean, default=False)

    # Who is assigned to do this card (responsible, checks it off). Empty means
    # the owner. Ordered by id so the avatars render in a stable order.
    assignees: Mapped[list[User]] = relationship(
        secondary=item_assignees, order_by=User.id
    )

    # --- recurrence (routines only; NULL on every other kind) -----------------
    # A routine has no single date_for; these say when it recurs instead.
    repeat_type: Mapped[RepeatType | None] = mapped_column(
        SAEnum(RepeatType, name="repeat_type"), nullable=True
    )
    # Weekly: a 7-bit weekday mask, Monday = bit 0 ... Sunday = bit 6. All seven
    # bits (127) is a plain daily routine.
    repeat_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Repeat every N weeks (weekly) or N months (monthly). 1 = every one.
    repeat_interval: Mapped[int] = mapped_column(Integer, default=1)
    # Reference date that phases "every N" so it knows which week/month is "on".
    # Falls back to created_at's date when NULL.
    repeat_anchor: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    # Monthly: the day of the month (1-31), clamped to the month's last day.
    repeat_month_day: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # When during the day (routines and events; tasks usually have none).
    time_of_day: Mapped[dt.time | None] = mapped_column(Time, nullable=True)
    # Which day (tasks and events). Routines leave this NULL and use recurrence.
    date_for: Mapped[dt.date | None] = mapped_column(Date, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Completion(Base):
    """One check-off of an item on a given day, by a given member.

    Routines are per-person: each assignee gets their own row per occurrence
    they complete, so one kid checking "brush teeth" does not mark it done for
    the others, and streaks are computed per member. Tasks and events keep a
    single shared check (any member's tap completes it for everyone). The
    constraint is one row per (item, member, day), which allows the several
    per-member rows a shared routine needs on a single day.
    """

    __tablename__ = "completions"
    __table_args__ = (
        UniqueConstraint("item_id", "user_id", "date_for", name="uq_completion_item_user_day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    # Who tapped it. Kept for "done by mom" touches later; SET NULL on delete
    # so history survives account removal.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    date_for: Mapped[dt.date] = mapped_column(Date, index=True)
    completed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class GroceryList(Base):
    """A named store (Walmart, Safeway, ...) the family shops at.

    Items that belong to no store live on the built-in "General" list, which
    is just list_id NULL — it needs no row here and can never be deleted.
    """

    __tablename__ = "grocery_lists"

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), index=True)
    name: Mapped[str] = mapped_column(String(60))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class GroceryItem(Base):
    """One line on the family's shared grocery list.

    Deliberately minimal: no assignee, no date. Checked items stay on the
    list (struck through in the UI) until a parent clears them, which
    forgives mis-taps in the store aisle.
    """

    __tablename__ = "grocery_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), index=True)
    title: Mapped[str] = mapped_column(String(120))
    checked: Mapped[bool] = mapped_column(Boolean, default=False)
    # Which store this belongs to. NULL = the General list. If a store is
    # removed its items fall back to General instead of disappearing.
    list_id: Mapped[int | None] = mapped_column(
        ForeignKey("grocery_lists.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class MoodLevel(str, enum.Enum):
    """Five-step mood scale rendered as weather in the UI (sun to storm)."""

    sunny = "sunny"
    partly = "partly"
    cloudy = "cloudy"
    rainy = "rainy"
    stormy = "stormy"


class Mood(Base):
    """A member's mood for one day. Others can see it unless hidden is set."""

    __tablename__ = "moods"
    __table_args__ = (UniqueConstraint("user_id", "date_for", name="uq_mood_user_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date_for: Mapped[dt.date] = mapped_column(Date, index=True)
    level: Mapped[MoodLevel] = mapped_column(SAEnum(MoodLevel, name="mood_level"))
    # Owner's choice: keep today's mood to themselves.
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
