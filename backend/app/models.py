import datetime as dt
import enum

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Table,
    Text,
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
    # IANA zone name ("America/Phoenix"). Reminders, digests, and anything
    # else schedule-shaped run on this clock. NULL = the server's own clock
    # (see app.clock), which is right whenever everyone lives where the
    # server does.
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Parent-controlled, family-wide: show OUR KIDS' photos (and first names)
    # to the family's villages — event attendee lists and the avatar route's
    # village crack. Off (the default) means other families only ever see a
    # bare first-initial circle per kid, no name, no photo. One switch for
    # all kids, present and future; parents' faces always cross the wall.
    share_kid_avatars: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Village(Base):
    """A named circle of linked families — the one deliberate, narrow opening
    in the family wall. Membership is invitation-only: there is no directory,
    no search, and a village you don't belong to 404s like it doesn't exist.
    What crosses the wall is tiny and explicit (a shared recipe shelf and
    opt-in mood/status); boards, kitchens, and calendars never do.

    The invite code is stored only as a SHA-256 hash: a database read never
    exposes a live door key, so the plaintext exists exactly once, in the
    response that minted it. One active code per village; a join consumes it."""

    __tablename__ = "villages"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    # The founding family: the only one whose admins may DELETE the village
    # (anyone may leave). SET NULL survives that family's removal.
    created_by_family_id: Mapped[int | None] = mapped_column(
        ForeignKey("families.id", ondelete="SET NULL"), nullable=True
    )
    invite_code_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    invite_expires_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class VillageFamily(Base):
    """One family's membership in one village. A family may belong to several
    villages; each pairing exists at most once."""

    __tablename__ = "village_families"
    __table_args__ = (
        UniqueConstraint("village_id", "family_id", name="uq_village_family"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    village_id: Mapped[int] = mapped_column(
        ForeignKey("villages.id", ondelete="CASCADE"), index=True
    )
    family_id: Mapped[int] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), index=True
    )
    joined_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class SignupInvite(Base):
    """A pending invitation onto the install itself. The server owner mints
    one with the invitee's name; the invitee redeems the code on the sign-in
    screen, chooses their own username and password, and lands in the
    create-your-family wizard — invites found NEW households, they never join
    an existing family. Codes live 48 hours (matching village codes; they're
    redeemable by anonymous visitors, so only their hash is stored)."""

    __tablename__ = "signup_invites"

    id: Mapped[int] = mapped_column(primary_key=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # The invitee picks their own username (and can adjust this name) at
    # redemption; the invite carries only who it's meant for.
    display_name: Mapped[str] = mapped_column(String(100))
    invited_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class VillageRecipe(Base):
    """One recipe shared onto one village's shelf. The row is a pointer, not a
    copy: the owning family's recipe stays theirs, and "save a copy" (not this
    table) is what puts an independent snapshot in another family's kitchen.

    family_id is the owner denormalized at share time (a recipe never changes
    families), buying attribution without a join and a one-query cleanup of a
    family's shares when it leaves the village."""

    __tablename__ = "village_recipes"
    __table_args__ = (
        UniqueConstraint("village_id", "recipe_id", name="uq_village_recipe"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    village_id: Mapped[int] = mapped_column(
        ForeignKey("villages.id", ondelete="CASCADE"), index=True
    )
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), index=True
    )
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), index=True)
    # The parent who shared it, for "Shared by Alex from Team Jam".
    shared_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class VillageFood(Base):
    """One custom food shared onto one village's shelf. The row is a pointer, not
    a copy: the owning family's food stays theirs, and "save a copy" (not this
    table) is what puts an independent snapshot in another family's kitchen.

    family_id is the owner denormalized at share time (a food never changes
    families), buying attribution without a join and a one-query cleanup of a
    family's shares when it leaves the village."""

    __tablename__ = "village_foods"
    __table_args__ = (
        UniqueConstraint("village_id", "food_id", name="uq_village_food"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    village_id: Mapped[int] = mapped_column(
        ForeignKey("villages.id", ondelete="CASCADE"), index=True
    )
    food_id: Mapped[int] = mapped_column(
        ForeignKey("foods.id", ondelete="CASCADE"), index=True
    )
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), index=True)
    # The parent who shared it, for "Shared by Alex from Team Jam".
    shared_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class RsvpStatus(str, enum.Enum):
    going = "going"
    maybe = "maybe"
    cant = "cant"


class VillageEvent(Base):
    """One activity/appointment shared onto a village. A pointer at the
    organizer's own Item (the VillageRecipe pattern) — attendee families never
    read that row directly; RSVPing "going" MATERIALIZES an independent Item
    copy on their board (items.village_event_id marks those copies).
    family_id is the organizer denormalized at share time."""

    __tablename__ = "village_events"
    __table_args__ = (
        UniqueConstraint("village_id", "item_id", name="uq_village_event"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    village_id: Mapped[int] = mapped_column(
        ForeignKey("villages.id", ondelete="CASCADE"), index=True
    )
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), index=True
    )
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), index=True)
    shared_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class VillageEventRsvp(Base):
    """One family's changeable answer to a village event: either parent may
    set or overwrite it (the DinnerVote upsert, but family-grained). The
    organizer's family never has a row — hosting is implicit."""

    __tablename__ = "village_event_rsvps"
    __table_args__ = (
        UniqueConstraint("event_id", "family_id", name="uq_event_rsvp_family"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("village_events.id", ondelete="CASCADE"), index=True
    )
    family_id: Mapped[int] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[RsvpStatus] = mapped_column(SAEnum(RsvpStatus, name="rsvp_status"))
    set_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class VillageEventAttendee(Base):
    """Who from an RSVPed family is coming — village-facing headcount only,
    never assignees on any card. Tracked for "going" answers; replaced whole
    on every RSVP write. How a member RENDERS across the wall is decided at
    read time (parents by name+face; kids only by initial unless their
    family's share_kid_avatars switch is on)."""

    __tablename__ = "village_event_attendees"
    __table_args__ = (
        UniqueConstraint("rsvp_id", "user_id", name="uq_event_attendee"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    rsvp_id: Mapped[int] = mapped_column(
        ForeignKey("village_event_rsvps.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))


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
    # The member's short daily "status" for the profile page ("How are you
    # doing?"). Owner-editable only, and shown to others only for the day it was
    # set: status_date holds that day, and anything older reads as no status,
    # so a status clears itself overnight the way a mood does.
    bio: Mapped[str] = mapped_column(String(500), default="")
    status_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    # When the member last set an avatar photo. NULL means no photo (fall back
    # to generated initials); the value also doubles as a cache-busting version
    # for the image URL, since the file path itself is fixed per user id.
    avatar_updated_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Bumped whenever the password changes. Session tokens record the version
    # they were issued under and a stale one is refused, so resetting a
    # password really does log that account out everywhere — sessions are
    # stateless JWTs and would otherwise ride out their whole lifetime.
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Set when an admin resets this account to a generated password. Until its
    # owner picks their own (which clears it), the session can reach only the
    # change-password flow — the generated password is a hand-off, not a life.
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    # Optional, informational (kid mode follows role — see is_minor). The ONE
    # birthdate per member: the admin sheet and the health profile both read
    # and write this same column (HealthProfile.birthdate is a property view).
    birthdate: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    # The member's chosen color scheme ("light"/"dark"), so a preference
    # follows the account onto any device. NULL = never picked (client default).
    theme: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # Cross-family presence: has this member elected to share their mood and
    # daily status with the family's villages? Off by default. Minors are
    # excluded from village presence server-side regardless of this flag.
    village_presence: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    # Personal daily targets behind the Fitness rings. NULL = the app-wide
    # recommended default (routers.fitness.DEFAULT_GOALS), so a fresh account
    # starts on the standard public-health numbers without storing them.
    goal_steps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    goal_active_kcal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    goal_exercise_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Opt-in: the member receives the daily verses at all — the Home card,
    # the check-offs, and the reading streak come as one package. Off by
    # default for new accounts; the welcome tour (and You) offers it.
    verses_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    # Opt-in: the member's LEVEL (and crumb total, in the mini profile) shows
    # to village members. Replaced share_verse_streak when streak numbers
    # folded into the breadcrumb economy; family always sees the level.
    share_level: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    # Opt-in: the watch's WORKOUT calories raise the day's food budget — only
    # deliberate workouts, never the all-day active total (the calorie
    # target's activity level already covers baseline movement). The diary
    # takes the LARGER of the workout sum and the manual exercise log for a
    # day, never the sum of both — a logged run is the same run the watch
    # tracked, so adding them would count it twice.
    count_watch_kcal: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    # Per-kind push preferences, e.g. {"midday": false}. Only turned-OFF kinds
    # are stored; a missing key (or NULL column) means ON, so new notification
    # kinds arrive enabled for everyone without a backfill. The valid kinds
    # live in app.push.PREF_KINDS; app.push.wants() reads this.
    push_prefs: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    @property
    def is_minor(self) -> bool:
        """Kid mode follows the role, nothing else: a Child account gets the
        shepherded experience — no nutrition/health area, only their own slice
        of the board, check-offs that wait for a parent, and a mood/status/
        journal only parents see. A child account is usually a surface parents
        track a kid THROUGH rather than an account the kid signs into, so
        there's no age-based unlock; if a member should have full access, give
        them the parent role. (Age drove this before 2026-07-09; birthdate is
        informational now.)"""
        return self.role == Role.child


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
    notes: Mapped[str] = mapped_column(String(1000), default="")

    # Who can SEE this card. private is the owner plus anyone assigned; family
    # puts it on the whole household's board. The API creates cards family by
    # default (_resolve_visibility) and the client opts a card out.
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
    # The last day the repeat may land on. NULL is "no end". An "after N
    # occurrences" end is resolved into this date when the card is saved, so
    # the engine only ever answers to a date.
    repeat_until: Mapped[dt.date | None] = mapped_column(Date, nullable=True)

    # Start time (the "From"). Activities and appointments need one (unless the
    # appointment is all-day); routines and tasks may leave it NULL.
    time_of_day: Mapped[dt.time | None] = mapped_column(Time, nullable=True)
    # End time (the "To"), for the event kinds that span a block. NULL on
    # routines, tasks, and all-day appointments.
    end_time: Mapped[dt.time | None] = mapped_column(Time, nullable=True)
    # An all-day appointment: a date with no times (Outlook's "all day").
    all_day: Mapped[bool] = mapped_column(Boolean, default=False)
    # Which day (tasks and events). Routines leave this NULL and use recurrence.
    # Indexed: the reminder loop scans by date several times a minute, forever.
    date_for: Mapped[dt.date | None] = mapped_column(Date, nullable=True, index=True)
    # The last day a multi-day card covers (a trip, an overnight stay). NULL is
    # the single day date_for already names; never set on a repeating card.
    end_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)

    # Where it happens, free text ("Riverside Park"). Any kind may carry one;
    # the UI offers it on activities and appointments.
    location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Set ONLY on a materialized copy of a village event living on an attendee
    # family's board: locks the card against local edit (the organizer manages
    # it; changing the RSVP is how it leaves) and dies with the event (CASCADE).
    # The organizer's own source card keeps this NULL. use_alter breaks the
    # items<->village_events FK cycle at create_all time; both dialects still
    # get the CASCADE (SQLite renders use_alter FKs inline and conftest turns
    # FKs on). Code paths delete copies EXPLICITLY anyway — the notify lists
    # need collecting before rows vanish, and the cascade racing the ORM's own
    # DELETE is why organizer-deletes log a benign rowcount SAWarning.
    village_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("village_events.id", ondelete="CASCADE", use_alter=True),
        nullable=True,
        index=True,
    )

    # Routines only, and INERT since the completion rework: the flag is still
    # stored and echoed back, but a synced workout no longer checks anything
    # off. Kept as a column (with its validator) so nothing needs a migration.
    workout_auto_complete: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )

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
    # True marks a CANCELLED occurrence (appointments/activities): the slot is
    # resolved — no reminders, no digest — but it reads "called off", never
    # "done". Same (item, member, day) slot a completion would occupy.
    cancelled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    date_for: Mapped[dt.date] = mapped_column(Date, index=True)
    completed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    # A minor's check-off starts pending and only counts once a parent makes it
    # official — approval promotes this same row (pending -> False, stamp
    # approved_by_id) rather than inserting a second one, so the unique
    # (item, member, day) constraint keeps holding. Rejecting deletes the row.
    pending: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    approved_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


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


class Recipe(Base):
    """A saved family recipe: what it is, how to make it, and its nutrition per
    serving. The week planner points meals at these, so choosing a night's
    dinner is just picking one — the ingredients were entered once.

    Nutrition isn't stored: it's computed by scaling each ingredient's food
    (per-100g macros) by its amount, then dividing by servings. Ingredients are
    structured rows (a food + how much of it), so "add to the grocery list" and
    macro totals both fall out of the same data instead of parsing free text."""

    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    servings: Mapped[int] = mapped_column(Integer, default=1)
    steps: Mapped[str] = mapped_column(Text, default="")
    # Set once when the recipe was adopted from a village share: "Copy of X
    # shared by Alex from Team Jam on Jul 9, 8:42 PM". Display-only — the
    # copy itself stays fully independent.
    provenance: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    # The ingredient lines, in the order the cook entered them. Deleting a recipe
    # takes its lines with it (delete-orphan here, ON DELETE CASCADE in the DB).
    ingredients: Mapped[list["RecipeIngredient"]] = relationship(
        cascade="all, delete-orphan",
        order_by="RecipeIngredient.position",
        back_populates="recipe",
    )

    # Shelf entries in any villages this recipe is shared to. Deleting the
    # recipe unshares it everywhere (saved copies are independent rows and
    # survive; see routers/villages.py).
    village_shares: Mapped[list["VillageRecipe"]] = relationship(
        cascade="all, delete-orphan"
    )


# A food is measured in one of two families: mass (base unit gram) or volume
# (base unit millilitre). We never convert between them — that needs the food's
# density, which the databases don't give us. Instead a food declares its base
# unit (Food.base_unit) and its nutrition is stored per 100 of that base, so a
# liquid labelled in mL never has to pretend it knows its weight.
MASS_UNITS: dict[str, float] = {"g": 1.0, "oz": 28.3495, "lb": 453.592}
VOLUME_UNITS: dict[str, float] = {
    "ml": 1.0,
    "floz": 29.5735,
    "cup": 236.588,
    "tbsp": 14.7868,
    "tsp": 4.92892,
}
# How many base units (g or mL) one of each unit is. Every token is <=4 chars,
# so the stored `unit` column stays String(4).
UNIT_TO_BASE: dict[str, float] = {**MASS_UNITS, **VOLUME_UNITS}
# Back-compat alias: earlier code (and mirrors) referred to GRAMS_PER_UNIT.
GRAMS_PER_UNIT = MASS_UNITS


def base_unit_of(unit: str) -> str:
    """The base unit ("g" or "ml") a measurement unit belongs to."""
    return "ml" if unit in VOLUME_UNITS else "g"


class RecipeIngredient(Base):
    """One line of a recipe: a food and how much of it. The amount is stored in
    the unit the cook typed (g/oz/lb for a solid, mL/fl oz/cup/tbsp/tsp for a
    liquid) for honest redisplay; the base amount (grams or millilitres) that the
    nutrition math uses is derived from it via UNIT_TO_BASE."""

    __tablename__ = "recipe_ingredients"

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(
        ForeignKey("recipes.id", ondelete="CASCADE"), index=True
    )
    food_id: Mapped[int] = mapped_column(ForeignKey("foods.id"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    unit: Mapped[str] = mapped_column(String(4), default="g")

    recipe: Mapped[Recipe] = relationship(back_populates="ingredients")
    food: Mapped["Food"] = relationship()

    @property
    def base_amount(self) -> float:
        """Amount in the food's base unit (grams or millilitres)."""
        return self.amount * UNIT_TO_BASE.get(self.unit, 1.0)

    # Legacy name kept for callers that predate volume support; for a volume food
    # this is millilitres, not grams. Prefer base_amount.
    grams = base_amount


class FoodSource(str, enum.Enum):
    """Where a food's nutrition came from."""

    usda = "usda"  # USDA FoodData Central (generic + branded)
    off = "off"  # Open Food Facts (barcodes)
    custom = "custom"  # a family's own entry for something the databases lack


class MealSlot(str, enum.Enum):
    breakfast = "breakfast"
    lunch = "lunch"
    dinner = "dinner"


class Meal(Base):
    """One planned meal on the family menu: a saved recipe, or a free-text
    title for nights that aren't a recipe ("Leftovers", "Pizza out"). The UI
    plans dinner only for now; the slot column is already here so breakfast
    and lunch cost a UI change later, not a migration."""

    __tablename__ = "meals"
    __table_args__ = (
        UniqueConstraint("family_id", "date_for", "slot", name="uq_meal_family_day_slot"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), index=True)
    date_for: Mapped[dt.date] = mapped_column(Date, index=True)
    slot: Mapped[MealSlot] = mapped_column(
        SAEnum(MealSlot, name="meal_slot"), default=MealSlot.dinner
    )
    # Losing a recipe shouldn't wipe the week's plan row itself: the FK goes
    # NULL and the night simply reads unplanned again.
    recipe_id: Mapped[int | None] = mapped_column(
        ForeignKey("recipes.id", ondelete="SET NULL"), nullable=True
    )
    custom_title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # When dinner happens, independent of what it is. A row may carry ONLY a
    # time (recipe and title both NULL) — "dinner's at 5" is a real plan even
    # before anyone knows what's cooking — so "planned" checks must look at
    # the pick fields, never at row existence.
    time_of_day: Mapped[dt.time | None] = mapped_column(Time, nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    recipe: Mapped["Recipe | None"] = relationship()


class DinnerChoice(str, enum.Enum):
    """The four standing dinner modes. The nightly decision is rarely "which
    recipe" — it's "are we cooking at all"."""

    self_serve = "self_serve"  # everyone fends for themselves
    homemade = "homemade"  # cooked at home (optionally a saved recipe)
    go_out = "go_out"  # a restaurant (typed detail)
    delivery = "delivery"  # ordered in (typed detail)


class DinnerVote(Base):
    """One member's standing pick for a night's dinner mode, with an optional
    short detail ("Chipotle") or, for homemade, a recipe. One changeable vote
    per member per night, kids included - their votes are advisory because
    only a parent can lock the plan in. Locking sets the normal meal row and
    leaves these untouched, so unlocking brings the votes right back."""

    __tablename__ = "dinner_votes"
    __table_args__ = (
        UniqueConstraint("family_id", "date_for", "user_id", name="uq_dinner_vote_night"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), index=True)
    date_for: Mapped[dt.date] = mapped_column(Date, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    choice: Mapped[DinnerChoice] = mapped_column(SAEnum(DinnerChoice, name="dinner_choice"))
    detail: Mapped[str] = mapped_column(String(30), default="")
    recipe_id: Mapped[int | None] = mapped_column(
        ForeignKey("recipes.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Food(Base):
    """A food with per-100g nutrition, used as a recipe ingredient. Rows are
    either cached from USDA/OFF on first use (family_id NULL = shared across the
    install) or a family's own custom entry (family_id set). Recipes reference
    these and compute their totals by scaling each ingredient's amount."""

    __tablename__ = "foods"

    id: Mapped[int] = mapped_column(primary_key=True)
    # NULL for a shared cache row (a USDA/OFF food anyone can reuse); set for a
    # family's custom food, which only that family sees.
    family_id: Mapped[int | None] = mapped_column(
        ForeignKey("families.id"), nullable=True, index=True
    )
    source: Mapped[FoodSource] = mapped_column(SAEnum(FoodSource, name="food_source"))
    # The FDC id (usda) or barcode (off); NULL for custom foods.
    source_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    brand: Mapped[str] = mapped_column(String(120), default="")
    # A family's own optional filing label for a custom food (e.g. "Panda
    # Express"). NULL for the shared cache rows and for unfiled custom foods.
    # Private to the owning family: it never crosses the village wall.
    folder: Mapped[str | None] = mapped_column(String(60), nullable=True)
    # Which measure family this food is portioned in: "g" (mass, the default and
    # what every USDA/OFF food is) or "ml" (volume, for liquids a parent enters
    # by millilitres). Nutrition below is per 100 of THIS unit.
    base_unit: Mapped[str] = mapped_column(String(2), default="g", server_default="g")
    # Nutrition per 100 of base_unit (100 g for a solid, 100 mL for a liquid);
    # None when a source didn't supply a value. calories + the four base macros
    # came with 0014; 0016 added the rest of the Nutrition Facts label. cholesterol
    # and sodium are in mg (as labels print them); the rest are grams.
    calories: Mapped[float | None] = mapped_column(Float, nullable=True)
    protein_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    carbs_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    fat_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    saturated_fat_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    trans_fat_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    cholesterol_mg: Mapped[float | None] = mapped_column(Float, nullable=True)
    sodium_mg: Mapped[float | None] = mapped_column(Float, nullable=True)
    fiber_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    sugar_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Health-check fields, filled from USDA/OFF on a barcode scan (0054), and
    # carried onto a custom food saved from one. None on hand-made foods and
    # until a cache row has been healed. ingredients_text is the
    # raw label ingredient string; added_sugar_g is per-100 of base_unit like the
    # macros; additives is the OFF additives_tags list comma-joined ("en:e102,
    # en:e211") — Text, never a JSON column (Postgres json has no equality op, a
    # hard rule here); nova_group is the OFF NOVA processing class (1-4).
    ingredients_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    added_sugar_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    additives: Mapped[str | None] = mapped_column(Text, nullable=True)
    nova_group: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # Named real-world portions (e.g. "1 slice" = 21 g). Nutrition stays per-100g;
    # servings are how a person picks a portion. Ordered by position.
    servings: Mapped[list["FoodServing"]] = relationship(
        back_populates="food",
        cascade="all, delete-orphan",
        order_by="FoodServing.position",
    )

    # Shelf entries in any villages this custom food is shared to. Deleting the
    # food unshares it everywhere (saved copies are independent rows and
    # survive; see routers/villages.py).
    village_shares: Mapped[list["VillageFood"]] = relationship(
        cascade="all, delete-orphan"
    )


class FoodServing(Base):
    """One named serving for a food: a label ("1 slice", "1 tbsp") and its size in
    the food's base unit. The `grams` column holds that base amount — grams for a
    solid, millilitres for a liquid (base_unit "ml") — which is what lets a serving
    convert to the per-100 nutrition and feed the recipe math. Custom foods carry
    the servings a parent enters (Cronometer-style, several per food)."""

    __tablename__ = "food_servings"

    id: Mapped[int] = mapped_column(primary_key=True)
    food_id: Mapped[int] = mapped_column(
        ForeignKey("foods.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(60))
    grams: Mapped[float] = mapped_column(Float)
    position: Mapped[int] = mapped_column(Integer, default=0)

    food: Mapped["Food"] = relationship(back_populates="servings")


class SavedFood(Base):
    """A family's pinned foods: search or barcode results bookmarked for
    quick re-use (the Kitchen shelf and the picker). The pin references the
    shared cache row (or the family's custom food); removing the pin never
    deletes the food."""

    __tablename__ = "saved_foods"
    __table_args__ = (UniqueConstraint("family_id", "food_id", name="uq_saved_food"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), index=True)
    food_id: Mapped[int] = mapped_column(ForeignKey("foods.id", ondelete="CASCADE"))
    # Who pinned it; informational, survives account removal.
    saved_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    food: Mapped["Food"] = relationship()


class DiarySlot(str, enum.Enum):
    """Which part of the day a diary entry belongs to. Deliberately its own
    enum (not MealSlot): the menu plans meals for the family's evening, the
    diary groups what one person ate, and the two lists evolve separately."""

    breakfast = "breakfast"
    lunch = "lunch"
    dinner = "dinner"
    snack = "snack"


class DiaryEntry(Base):
    """One line of a member's food diary: what they ate, when, and the
    nutrition it amounted to.

    The nutrient columns are a snapshot of the SERVED amount, computed
    server-side at log time. That makes history honest: editing a recipe or
    deleting a custom food later never rewrites what a past day says you ate.
    food_id/recipe_id are soft references (SET NULL on delete) kept for
    provenance and for recomputing when the amount is edited; once a reference
    is gone, edits scale the snapshot linearly instead.

    A diary is personal: every query filters on user_id, and no endpoint —
    parent, admin, or otherwise — exposes another member's entries."""

    __tablename__ = "diary_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    date_for: Mapped[dt.date] = mapped_column(Date, index=True)
    slot: Mapped[DiarySlot] = mapped_column(SAEnum(DiarySlot, name="diary_slot"))
    # Wall-clock time the bite happened, as the client reported it (optional).
    time_of_day: Mapped[dt.time | None] = mapped_column(Time, nullable=True)
    # Denormalized display name/brand, so the row still reads right after its
    # food or recipe is gone.
    name: Mapped[str] = mapped_column(String(200))
    brand: Mapped[str] = mapped_column(String(120), default="")
    food_id: Mapped[int | None] = mapped_column(
        ForeignKey("foods.id", ondelete="SET NULL"), nullable=True, index=True
    )
    recipe_id: Mapped[int | None] = mapped_column(
        ForeignKey("recipes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # For a food: amount in `unit` (a mass or volume unit matching the food's
    # base). For a recipe: number of servings, unit "srv".
    amount: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(4), default="g")
    # Optional human phrasing of the portion ("2 slices", "1 serving") for
    # display; the math never reads it.
    label: Mapped[str | None] = mapped_column(String(60), nullable=True)
    # Nutrition for the served amount (NOT per-100); None = source didn't know.
    calories: Mapped[float | None] = mapped_column(Float, nullable=True)
    protein_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    carbs_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    fat_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    saturated_fat_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    trans_fat_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    cholesterol_mg: Mapped[float | None] = mapped_column(Float, nullable=True)
    sodium_mg: Mapped[float | None] = mapped_column(Float, nullable=True)
    fiber_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    sugar_g: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # View-only link back to the source food (food_id is a soft SET NULL
    # reference). Lets the diary edit sheet re-offer the food's named servings
    # without a second round-trip; never used to mutate. None once the food is
    # deleted, so edits fall back to scaling the snapshot.
    food: Mapped["Food | None"] = relationship(viewonly=True)

    @property
    def food_servings(self) -> list["FoodServing"]:
        return self.food.servings if self.food else []

    @property
    def food_base_unit(self) -> str | None:
        return self.food.base_unit if self.food else None


class TargetMode(str, enum.Enum):
    """Where the calorie budget comes from: typed by hand, or computed from
    the member's health profile and goal (see app.health)."""

    manual = "manual"
    auto = "auto"


class NutritionTarget(Base):
    """A member's own daily targets: a calorie budget and how it splits across
    protein/carbs/fat (percentages, summing to 100). Each member sets their
    own; no row yet means the app's starting default. Gram targets are derived
    from these at read time (4 kcal/g protein and carbs, 9 kcal/g fat).

    In auto mode the calorie budget is computed from the health profile at
    read time (the stored calories are kept as the fallback); the macro split
    is always the member's own, whatever the mode."""

    __tablename__ = "nutrition_targets"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    mode: Mapped[TargetMode] = mapped_column(
        SAEnum(TargetMode, name="target_mode"),
        default=TargetMode.manual,
        server_default="manual",
    )
    calories: Mapped[int] = mapped_column(Integer, default=2000)
    protein_pct: Mapped[int] = mapped_column(Integer, default=30)
    carbs_pct: Mapped[int] = mapped_column(Integer, default=40)
    fat_pct: Mapped[int] = mapped_column(Integer, default=30)


class Sex(str, enum.Enum):
    """Biological sex, as the BMR formulas define it. Asked for one reason
    only: Mifflin-St Jeor's constants differ by it."""

    male = "male"
    female = "female"


class ActivityLevel(str, enum.Enum):
    """Overall daily activity, mapped to the standard TDEE multipliers."""

    sedentary = "sedentary"  # desk day, little exercise (x1.2)
    light = "light"  # exercise 1-3 days/week (x1.375)
    moderate = "moderate"  # exercise 3-5 days/week (x1.55)
    active = "active"  # exercise 6-7 days/week (x1.725)
    very_active = "very_active"  # hard training or a physical job (x1.9)


class GoalType(str, enum.Enum):
    lose = "lose"
    maintain = "maintain"
    gain = "gain"


class HealthProfile(Base):
    """A member's optional health settings: the inputs the calorie math needs
    plus their goal. Every field is nullable - the profile fills in as much
    as the member wants to share, and the computed panel appears only once
    it's complete enough to be honest (see app.health.compute).

    Private like the diary, with one deliberate exception: a parent can see a
    CHILD's health section and set the child's goal (children never set their
    own; a calorie deficit for a kid is a parent-and-pediatrician decision)."""

    __tablename__ = "health_profiles"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    sex: Mapped[Sex | None] = mapped_column(SAEnum(Sex, name="sex"), nullable=True)
    height_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    activity_level: Mapped[ActivityLevel | None] = mapped_column(
        SAEnum(ActivityLevel, name="activity_level"), nullable=True
    )
    goal: Mapped[GoalType | None] = mapped_column(
        SAEnum(GoalType, name="goal_type"), nullable=True
    )
    rate_lbs_per_week: Mapped[float | None] = mapped_column(Float, nullable=True)
    goal_weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Informational second lens on the goal; the math stays weight-driven.
    goal_body_fat_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    user: Mapped[User] = relationship()

    # There is ONE birthdate per member (users.birthdate) — the admin sheet
    # and the health profile read and write the same value, so they can never
    # disagree. Exposed here as a property so the calorie math and the API
    # keep their original shape.
    @property
    def birthdate(self) -> dt.date | None:
        return self.user.birthdate if self.user is not None else None

    @birthdate.setter
    def birthdate(self, value: dt.date | None) -> None:
        if self.user is None:
            raise ValueError("profile must be flushed before setting birthdate")
        self.user.birthdate = value


class WeightEntry(Base):
    """One weigh-in: a day's weight (kg) and optionally body fat percent. One
    row per member per day (re-weighing updates it). The latest row is what
    the calorie math reads, so each weigh-in auto-adjusts the target."""

    __tablename__ = "weight_entries"
    __table_args__ = (UniqueConstraint("user_id", "date_for"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    date_for: Mapped[dt.date] = mapped_column(Date, index=True)
    weight_kg: Mapped[float] = mapped_column(Float)
    body_fat_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ExerciseEffort(str, enum.Enum):
    """How hard a logged workout felt; picks the MET the burn math uses."""

    light = "light"
    moderate = "moderate"
    vigorous = "vigorous"


class ExerciseEntry(Base):
    """One logged workout: what, how hard, how long, and the calories it
    burned. kcal is a snapshot computed at log time from the member's latest
    weigh-in (MET x kg x hours); editing recomputes it. A day's total burn is
    added onto that day's energy target, so exercise literally earns calories
    back the way Cronometer does. Self-only, like the diary."""

    __tablename__ = "exercise_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    date_for: Mapped[dt.date] = mapped_column(Date, index=True)
    time_of_day: Mapped[dt.time | None] = mapped_column(Time, nullable=True)
    # A key into app.health.EXERCISES ("running", "walking").
    activity: Mapped[str] = mapped_column(String(30))
    effort: Mapped[ExerciseEffort] = mapped_column(
        SAEnum(ExerciseEffort, name="exercise_effort")
    )
    minutes: Mapped[float] = mapped_column(Float)
    kcal: Mapped[float] = mapped_column(Float)
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


class JournalEntry(Base):
    """A member's private written entry for one day. One per person per day,
    strictly personal: unlike moods, a journal is never shown to anyone else."""

    __tablename__ = "journal_entries"
    __table_args__ = (UniqueConstraint("user_id", "date_for", name="uq_journal_user_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date_for: Mapped[dt.date] = mapped_column(Date, index=True)
    body: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class PushSubscription(Base):
    """One browser/device that agreed to receive Web Push. A member can hold
    several (phone, tablet); a device that changes hands re-registers its
    endpoint under the new member. Dead endpoints (404/410 from the push
    service) are deleted on the spot when a send bounces."""

    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    p256dh: Mapped[str] = mapped_column(String(255))
    auth: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ReminderLog(Base):
    """One row per card per day per kind of reminder, so a restarted server
    (or two ticks racing) never notifies the same card twice. An appointment
    gets two: the "lead" heads-up before it, then "start" when it begins."""

    __tablename__ = "reminder_log"
    __table_args__ = (
        UniqueConstraint("item_id", "date_for", "kind", name="uq_reminder_item_day_kind"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), index=True
    )
    date_for: Mapped[dt.date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(16), default="lead", server_default="lead")


class AppMeta(Base):
    """Server-wide key/value scratch, one row per fact. Holds "app_version":
    the version that last booted, so a deploy can tell it moved and announce
    itself once."""

    __tablename__ = "app_meta"

    key: Mapped[str] = mapped_column(String(32), primary_key=True)
    value: Mapped[str] = mapped_column(String(64))


class DigestLog(Base):
    """One row per member per day per scheduled push (morning digest, mid-day
    check, evening check-in) once it was handled — sent, or deliberately not:
    an empty board claims its row too. Restarts and racing ticks can then
    never hit the same phone twice."""

    __tablename__ = "digest_log"
    __table_args__ = (
        UniqueConstraint("user_id", "date_for", "kind", name="uq_digest_user_day_kind"),
        # The push tick asks "who already got today's <kind>?" every minute.
        Index("ix_digest_log_day_kind", "date_for", "kind"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    date_for: Mapped[dt.date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(10), default="morning", server_default="morning")


# ---- fitness (Apple Health import) ----------------------------------------------


class IngestToken(Base):
    """One member's key for pushing health data in from their phone (the
    Health Auto Export app POSTs to /ingest/health with it). Stored only as
    a SHA-256 hash, like invite codes: the plaintext exists exactly once, in
    the response that minted it. Re-minting replaces the old key."""

    __tablename__ = "ingest_tokens"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_used_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class FitnessDaily(Base):
    """One member's imported number for one day and one metric (steps,
    active_kcal, exercise_minutes, resting_hr). Re-imports upsert, so the
    exporter can safely resend whole windows. Self-only, like the diary."""

    __tablename__ = "fitness_daily"
    __table_args__ = (UniqueConstraint("user_id", "date_for", "metric"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    date_for: Mapped[dt.date] = mapped_column(Date, index=True)
    metric: Mapped[str] = mapped_column(String(30))
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(20))


class FitnessIntraday(Base):
    """The same imported numbers as FitnessDaily but bucketed to the hour, for
    the time-of-day charts (steps, active_kcal, distance, hr). Only the metrics
    that read well hourly live here; re-imports upsert per (member, day, metric,
    hour). Self-only, like the diary."""

    __tablename__ = "fitness_intraday"
    __table_args__ = (UniqueConstraint("user_id", "date_for", "metric", "hour"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    date_for: Mapped[dt.date] = mapped_column(Date, index=True)
    metric: Mapped[str] = mapped_column(String(30))
    hour: Mapped[int] = mapped_column(Integer)  # 0-23, member-local wall clock
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(20))


class Workout(Base):
    """One imported workout. Times are the phone's wall clock, like every
    other time in the app. external_id is the exporter's stable id, so a
    re-sent window updates instead of duplicating; workouts without one fall
    back to (member, start, activity). Self-only, like the diary."""

    __tablename__ = "workouts"
    __table_args__ = (UniqueConstraint("user_id", "external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    external_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    activity: Mapped[str] = mapped_column(String(80))
    started_at: Mapped[dt.datetime] = mapped_column(DateTime, index=True)
    ended_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    kcal: Mapped[float | None] = mapped_column(Float, nullable=True)
    distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_hr: Mapped[float | None] = mapped_column(Float, nullable=True)
    # The workout's GPS trace, downsampled to a handful of [lat, lon] pairs —
    # just enough to draw the little route thumbnail, deliberately not the
    # full-resolution track. Present only when the exporter sends route data.
    route: Mapped[list | None] = mapped_column(JSON, nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="apple", server_default="apple")


class DiaryDayLock(Base):
    """A member's "my day is recorded" mark on one diary date. Presence is the
    lock: a locked day refuses entry changes until unlocked, so the mark
    means something. The FIRST lock of a date pays +2 breadcrumbs (ledger key
    diary:<date>); unlocking and re-locking pays nothing more, ever."""

    __tablename__ = "diary_day_locks"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    date_for: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class CrumbLedger(Base):
    """One breadcrumb award. The ledger is the whole economy: totals, levels,
    and tiers all derive from SUM(amount), and every award carries a
    source_key unique per member ("login:2026-07-11", "item:42:2026-07-11",
    "vstreak:7") so nothing can ever pay twice — re-syncs, re-checks, and
    restarts all bounce off the constraint, the DigestLog claim pattern.
    Amounts are signed so a future "spend crumbs" feature is a row, not a
    rework."""

    __tablename__ = "crumb_ledger"
    __table_args__ = (
        UniqueConstraint("user_id", "source_key", name="uq_crumb_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    date_for: Mapped[dt.date] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(12))  # login/verses/workout/complete/bonus
    amount: Mapped[int] = mapped_column(Integer)
    source_key: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class InboxEntry(Base):
    """One line of a member's notification history — the Inbox in the You tab.
    Rows are written at the same moments the app would push (board changes,
    dinner lock-ins, workouts, approvals) plus crumb earns, but independently
    of push: prefs and VAPID config gate interruptions, never history. Each
    recipient gets their own row; read is flipped in bulk when they open the
    page. Retention is capped per member on insert, so the table stays small
    without a sweeper."""

    __tablename__ = "inbox_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("families.id"), index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(12))  # crumb/board/dinner/workout/pending/approved/invite/rsvp/village/grocery/recipe/member/household
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(String(200), default="")
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class VerseCheck(Base):
    """One member's check on one of the day's three verses. A day with all
    three checked counts toward that member's reading streak. Self-owned like
    the journal: which verses, on which days, is nobody else's data — only the
    streak NUMBER is ever surfaced, and beyond the family only by opt-in."""

    __tablename__ = "verse_checks"
    __table_args__ = (
        UniqueConstraint("user_id", "date_for", "verse_idx", name="uq_verse_check"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    date_for: Mapped[dt.date] = mapped_column(Date, index=True)
    verse_idx: Mapped[int] = mapped_column(Integer)  # 0..2, the day's three
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
