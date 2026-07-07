import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

from app.models import FoodSource, ItemKind, MoodLevel, RepeatType, Role, Visibility


# Pydantic models define the JSON shapes for requests/responses and validate
# them automatically. They are separate from the SQLAlchemy ORM models so we
# never accidentally leak fields like password_hash to the client.


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    role: Role
    is_admin: bool
    # The instance owner / "server admin". Only this account may invite new
    # households; the frontend uses it to show that action to the owner alone.
    is_owner: bool = False
    # None only while a new-household account hasn't created its family yet;
    # the frontend uses this to show the create-your-family wizard.
    family_id: int | None = None
    # When the member last set an avatar photo, or None if they have none. The
    # frontend shows a photo when this is set and appends it as a cache-busting
    # version to the avatar image URL.
    avatar_updated_at: dt.datetime | None = None

    # Let Pydantic read attributes off a SQLAlchemy User object directly.
    model_config = {"from_attributes": True}


class LoginIn(BaseModel):
    username: str
    password: str


class BootstrapIn(BaseModel):
    """Payload for creating the very first parent account (and its family)."""

    username: str = Field(min_length=3, max_length=50)
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=128)
    family_name: str = Field(default="Home", min_length=1, max_length=80)


class CreateUserIn(BootstrapIn):
    """An admin creating another family member; role defaults to child."""

    role: Role = Role.child
    # None means "use the default for the role" (parent -> admin, child -> not).
    is_admin: bool | None = None
    # True creates the account with NO family: on first login they get the
    # create-your-family wizard and become head of their own household.
    new_household: bool = False


class FamilyIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class FamilyOut(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class UpdateUserIn(BaseModel):
    """Admin editing an account. Every field is optional; omitted = unchanged.

    Usernames are deliberately immutable for now: they are the stable login
    identity, and renaming would be an easy way to confuse sessions later.
    """

    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    role: Role | None = None
    is_admin: bool | None = None
    # Setting this resets the account's password (same policy as creation).
    password: str | None = Field(default=None, min_length=8, max_length=128)


class SetupOut(BaseModel):
    """Tells the frontend whether the first-run wizard should be shown.

    Unauthenticated by design, and it reveals exactly one bit: "has this
    install been set up yet". Same pattern Jellyfin's startup wizard uses.
    """

    initialized: bool


# ---- items and the home feed -------------------------------------------------


class RepeatIn(BaseModel):
    """How a routine recurs. Weekly uses days (0=Mon .. 6=Sun); monthly uses
    month_day. interval is "every N weeks/months"; anchor phases it (defaults
    to the routine's creation date)."""

    type: RepeatType
    days: list[int] = Field(default_factory=list)
    interval: int = Field(default=1, ge=1, le=52)
    month_day: int | None = Field(default=None, ge=1, le=31)
    anchor: dt.date | None = None


class RepeatOut(BaseModel):
    type: RepeatType
    days: list[int]  # 0=Mon .. 6=Sun
    interval: int
    month_day: int | None


class ItemIn(BaseModel):
    """A parent creating a card for the board."""

    kind: ItemKind
    title: str = Field(min_length=1, max_length=120)
    notes: str = Field(default="", max_length=300)
    # Who the card is shared with. Empty on a personal card means the owner
    # alone; use visibility=family for "Everyone".
    assignee_ids: list[int] = Field(default_factory=list)
    # Household visibility. None lets the server pick: family if visibility is
    # explicitly Everyone, else assigned when members are named, else personal.
    visibility: Visibility | None = None
    time_of_day: dt.time | None = None  # start / "From"
    end_time: dt.time | None = None  # end / "To" (activities & timed appointments)
    all_day: bool = False  # all-day appointment: a date with no times
    date_for: dt.date | None = None  # tasks/events; routines use repeat instead
    repeat: RepeatIn | None = None  # required for routines, forbidden otherwise
    # Future cross-household feed (Phase E). None follows the kind default.
    shared_to_feed: bool | None = None


class ItemUpdate(BaseModel):
    """Editing a card. Omitted fields stay unchanged; explicit nulls clear.

    Pydantic can't tell "omitted" from "sent as null" without this trick:
    model_fields_set records which keys were actually in the JSON body.
    """

    title: str | None = Field(default=None, min_length=1, max_length=120)
    notes: str | None = Field(default=None, max_length=300)
    # Sending the list replaces the assignees wholesale.
    assignee_ids: list[int] | None = None
    visibility: Visibility | None = None
    time_of_day: dt.time | None = None
    end_time: dt.time | None = None
    all_day: bool | None = None
    date_for: dt.date | None = None
    repeat: RepeatIn | None = None
    shared_to_feed: bool | None = None


class AssigneeCompletion(BaseModel):
    """One participant's own state on a routine: whether they've done today's
    occurrence, and their personal streak. Routines only."""

    user_id: int
    completed: bool
    streak: int


class FeedItemOut(BaseModel):
    id: int
    owner_id: int | None
    kind: ItemKind
    title: str
    notes: str
    visibility: Visibility
    assignees: list[UserOut]
    shared_to_feed: bool
    time_of_day: dt.time | None  # start / "From"
    end_time: dt.time | None  # end / "To"
    all_day: bool
    date_for: dt.date | None
    repeat: RepeatOut | None  # routines only
    # The requesting member's own view: for a routine, their own check/streak
    # (or, for a non-participant, whether every participant is done). For other
    # kinds, the single shared check.
    completed: bool
    streak: int | None
    # Per-participant state for routines, so the parents' board can show each
    # member's check independently. None for non-routine kinds.
    assignee_completions: list[AssigneeCompletion] | None

    model_config = {"from_attributes": True}


class FeedOut(BaseModel):
    """Everything the home screen needs for one day, in three date-based buckets.

    The client slices ``today`` further by the live clock (past due / now /
    coming up / anytime); the server only groups by date so it never has to
    know the family's wall-clock time.
    """

    date: dt.date
    # One-off cards (never routines) whose date has passed and that are still
    # open, plus any checked off today so they linger crossed out until midnight.
    overdue: list[FeedItemOut]
    # Everything happening today: routines that land today, cards dated today,
    # and undated tasks.
    today: list[FeedItemOut]
    # One-off cards dated in the next seven days.
    next7: list[FeedItemOut]


class CalendarDayOut(BaseModel):
    """One day on the calendar: its scheduled cards, time-sorted. Routines are
    expanded onto the days their schedule lands on; undated "anytime" tasks
    aren't scheduled and never appear here."""

    date: dt.date
    items: list[FeedItemOut]


class CalendarOut(BaseModel):
    start: dt.date
    end: dt.date
    days: list[CalendarDayOut]


# ---- grocery list --------------------------------------------------------------


class GroceryListIn(BaseModel):
    """A parent adding a store."""

    name: str = Field(min_length=1, max_length=60)


class GroceryListOut(BaseModel):
    id: int
    name: str

    model_config = {"from_attributes": True}


class GroceryItemIn(BaseModel):
    """A parent adding a line. list_id None means the General list."""

    title: str = Field(min_length=1, max_length=120)
    list_id: int | None = None


class GroceryItemUpdate(BaseModel):
    """Editing a line: rename, (un)check, or move it to another store.

    Omitted fields stay put; list_id sent as null moves the item to General
    (told apart from "omitted" via model_fields_set, same as ItemUpdate).
    """

    title: str | None = Field(default=None, min_length=1, max_length=120)
    checked: bool | None = None
    list_id: int | None = None


class GroceryItemOut(BaseModel):
    id: int
    title: str
    checked: bool
    list_id: int | None

    model_config = {"from_attributes": True}


class GroceryStateOut(BaseModel):
    """Everything the Kitchen tab needs in one request."""

    lists: list[GroceryListOut]
    items: list[GroceryItemOut]


# ---- recipes -------------------------------------------------------------------


MassUnit = Literal["g", "oz", "lb"]


class RecipeIngredientIn(BaseModel):
    """One ingredient line the cook is saving. It carries the food itself, not
    just a reference: a food picked from search or a barcode isn't in our
    database until it's used, so the recipe save is what persists it. `food_id`
    is set only when reusing a food that's already saved (a custom food, or one
    a previous recipe already cached); otherwise source/source_id/name/macros
    describe the food to find-or-create."""

    food_id: int | None = None
    source: FoodSource
    source_id: str | None = Field(default=None, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    brand: str = Field(default="", max_length=120)
    calories: float | None = Field(default=None, ge=0, le=100000)
    protein_g: float | None = Field(default=None, ge=0, le=10000)
    carbs_g: float | None = Field(default=None, ge=0, le=10000)
    fat_g: float | None = Field(default=None, ge=0, le=10000)
    amount: float = Field(gt=0, le=100000)
    unit: MassUnit = "g"


class RecipeIn(BaseModel):
    """A parent creating a recipe. Nutrition isn't sent — it's computed from the
    ingredient lines. A recipe can be saved with no ingredients yet."""

    name: str = Field(min_length=1, max_length=120)
    servings: int = Field(default=1, ge=1, le=100)
    steps: str = Field(default="", max_length=10000)
    ingredients: list[RecipeIngredientIn] = Field(default_factory=list, max_length=100)


class RecipeUpdate(BaseModel):
    """Editing a recipe. Omitted fields stay (told apart from "sent" via
    model_fields_set, like ItemUpdate); sending `ingredients` replaces the whole
    list, which is how the editor works — it posts the lines it currently has."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    servings: int | None = Field(default=None, ge=1, le=100)
    steps: str | None = Field(default=None, max_length=10000)
    ingredients: list[RecipeIngredientIn] | None = Field(default=None, max_length=100)


class RecipeIngredientOut(BaseModel):
    """A saved ingredient line: what food, how much, and the macros that amount
    contributes (per-100g scaled by grams) so the client can total without
    re-deriving. `grams` is the canonical amount the contribution is based on."""

    id: int
    food_id: int
    source: FoodSource
    source_id: str | None
    name: str
    brand: str
    amount: float
    unit: str
    grams: float
    calories: float | None
    protein_g: float | None
    carbs_g: float | None
    fat_g: float | None


class RecipeMacros(BaseModel):
    """Per-serving nutrition, computed from the ingredient lines. A field is null
    only when no ingredient supplied that macro at all (so an empty recipe, or
    foods that never listed protein, reads as "—" rather than a misleading 0)."""

    calories: float | None
    protein_g: float | None
    carbs_g: float | None
    fat_g: float | None


class RecipeOut(BaseModel):
    id: int
    name: str
    servings: int
    steps: str
    ingredients: list[RecipeIngredientOut]
    per_serving: RecipeMacros


# ---- foods (database cache + custom) -------------------------------------------


class FoodOut(BaseModel):
    """A food with per-100g nutrition. id is None for an un-saved search/barcode
    result (the client saves it when it's used in a recipe); set for a stored
    custom food."""

    id: int | None = None
    source: FoodSource
    source_id: str | None = None
    name: str
    brand: str = ""
    calories: float | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None

    model_config = {"from_attributes": True}


class FoodIn(BaseModel):
    """A parent adding a custom food the databases don't have. Nutrition is per
    100 g, to match the USDA/Open Food Facts foods it sits alongside."""

    name: str = Field(min_length=1, max_length=200)
    brand: str = Field(default="", max_length=120)
    calories: float | None = Field(default=None, ge=0, le=100000)
    protein_g: float | None = Field(default=None, ge=0, le=10000)
    carbs_g: float | None = Field(default=None, ge=0, le=10000)
    fat_g: float | None = Field(default=None, ge=0, le=10000)


# ---- profiles and moods --------------------------------------------------------


class MoodOut(BaseModel):
    level: MoodLevel
    hidden: bool

    model_config = {"from_attributes": True}


class MoodIn(BaseModel):
    date_for: dt.date
    level: MoodLevel
    hidden: bool = False


class JournalOut(BaseModel):
    date_for: dt.date
    body: str
    updated_at: dt.datetime

    model_config = {"from_attributes": True}


class JournalIn(BaseModel):
    date_for: dt.date
    body: str = Field(max_length=20000)


class FamilyMemberOut(UserOut):
    """A member as others see them on the family strip: user + today's mood.

    mood is None when the member has not set one OR chose to hide it; the
    two cases are deliberately indistinguishable to other members.
    """

    mood: MoodOut | None = None


class ProfileOut(FamilyMemberOut):
    bio: str
    created_at: dt.datetime


class ProfileUpdateIn(BaseModel):
    """A member editing their own profile."""

    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    bio: str | None = Field(default=None, max_length=500)
