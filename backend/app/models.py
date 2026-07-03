import datetime as dt
import enum

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, Time, UniqueConstraint
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
    # Can this user see the admin dashboard? Defaults follow role at creation
    # (parent -> True, child -> False) but are overridable per account.
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    # Short "about me" for the profile page. Owner-editable only.
    bio: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ItemKind(str, enum.Enum):
    """The three kinds of cards on the board."""

    routine = "routine"  # repeats every day (brush teeth, morning walk)
    todo = "todo"  # one-off, optionally dated (call the dentist)
    event = "event"  # scheduled block on a specific day (team standup)


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), index=True)
    kind: Mapped[ItemKind] = mapped_column(SAEnum(ItemKind, name="item_kind"))
    title: Mapped[str] = mapped_column(String(120))
    notes: Mapped[str] = mapped_column(String(300), default="")

    # Who this is for. NULL means the whole family. If the member is deleted,
    # their items fall back to "everyone" instead of disappearing.
    assignee_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    assignee: Mapped[User | None] = relationship(User, foreign_keys=[assignee_id])

    # When during the day (routines and events; todos usually have none).
    time_of_day: Mapped[dt.time | None] = mapped_column(Time, nullable=True)
    # Which day (todos and events). Routines leave this NULL: they are daily.
    date_for: Mapped[dt.date | None] = mapped_column(Date, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Completion(Base):
    """One check-off of an item on a given day.

    Routines get one row per day they were done, which is what streaks are
    computed from. Todos and events get a single row on the day they were
    checked. One completion per item per day, enforced by the constraint.
    """

    __tablename__ = "completions"
    __table_args__ = (UniqueConstraint("item_id", "date_for", name="uq_completion_item_day"),)

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
