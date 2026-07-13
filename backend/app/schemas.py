import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models import (
    ActivityLevel,
    DiarySlot,
    DinnerChoice,
    ExerciseEffort,
    FoodSource,
    GoalType,
    ItemKind,
    MealSlot,
    MoodLevel,
    RepeatType,
    Role,
    Sex,
    TargetMode,
    Visibility,
)


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
    # True after an admin reset this account to a generated password; the
    # frontend routes to a choose-your-own-password screen (and the backend
    # refuses everything else) until they do.
    must_change_password: bool = False
    # When the member last set an avatar photo, or None if they have none. The
    # frontend shows a photo when this is set and appends it as a cache-busting
    # version to the avatar image URL.
    avatar_updated_at: dt.datetime | None = None
    # Kid mode: is_minor is derived (child role, nothing else) and rides along
    # on every user payload including /auth/me, so the frontend can shape
    # itself without extra calls. birthdate is optional and informational.
    birthdate: dt.date | None = None
    is_minor: bool = False
    # The member's chosen color scheme, so it follows them onto any device.
    # None until they pick one; deliberately absent from hand-built member
    # payloads (other members don't need your theme).
    theme: Literal["light", "dark"] | None = None
    # Whether this member shares mood/status onto the village card.
    village_presence: bool = False
    # Whether this member shares their level/crumbs with villages.
    share_level: bool = False

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
    # Optional: prefills the Nutrition health profile (one birthdate per
    # member — see models.User.birthdate).
    birthdate: dt.date | None = None
    # IANA zone name; the wizard sends the browser's so the family's clock
    # is right from day one. None = the server's clock.
    timezone: str | None = Field(default=None, max_length=64)


class CreateUserIn(BootstrapIn):
    """An admin creating another family member; role defaults to child."""

    role: Role = Role.child
    # None means "use the default for the role" (parent -> admin, child -> not).
    is_admin: bool | None = None
    # Kid mode switch-off date. Leaving it empty keeps a child account a minor.
    birthdate: dt.date | None = None
    # True creates the account with NO family: on first login they get the
    # create-your-family wizard and become head of their own household.
    new_household: bool = False


class FamilyIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    # Omitted = unchanged (PATCH); None sent explicitly = the server's clock.
    timezone: str | None = Field(default=None, max_length=64)


class FamilyOut(BaseModel):
    id: int
    name: str
    timezone: str | None

    model_config = {"from_attributes": True}


class RescuePasswordIn(BaseModel):
    """Server admin resetting a locked-out account, whatever its family."""

    password: str = Field(min_length=8, max_length=128)


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
    # None is ambiguous here (clear vs. omitted); update_user tells them apart
    # via model_fields_set, so sending null really does clear the birthdate.
    birthdate: dt.date | None = None


class ChangePasswordIn(BaseModel):
    """A member changing their own password. Proving the current one keeps a
    borrowed unlocked phone from silently taking over the account."""

    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class ResetPasswordOut(BaseModel):
    """An admin reset: the generated password, returned exactly once so the
    admin can hand it over. It is never retrievable again — only re-generated."""

    password: str
    user: UserOut


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
    # Routines only: a synced workout checks this routine off for that member.
    workout_auto_complete: bool = False
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
    workout_auto_complete: bool | None = None
    shared_to_feed: bool | None = None


class AssigneeCompletion(BaseModel):
    """One participant's own state on a routine: whether they've done today's
    occurrence, and their personal streak. Routines only."""

    user_id: int
    completed: bool
    streak: int
    # Kid mode: this participant tapped done but a parent hasn't approved yet.
    # Never true together with completed; the streak ignores pending marks.
    pending: bool = False


class FeedItemOut(BaseModel):
    id: int
    owner_id: int | None
    kind: ItemKind
    title: str
    notes: str
    visibility: Visibility
    assignees: list[UserOut]
    shared_to_feed: bool
    # Set only on the response to a completion that paid out, so the check
    # circle can float the "+n" without the UI guessing the economy's rules.
    crumbs_awarded: int = 0
    time_of_day: dt.time | None  # start / "From"
    end_time: dt.time | None  # end / "To"
    all_day: bool
    date_for: dt.date | None
    repeat: RepeatOut | None  # anything recurring (routines, repeating appointments)
    # Routines only: this routine checks itself off from a synced workout.
    workout_auto_complete: bool = False
    # The requesting member's own view: for a routine, their own check/streak
    # (or, for a non-participant, whether every participant is done). For other
    # kinds, the single shared check.
    completed: bool
    # Called off (appointments/activities): resolved, but never "done".
    cancelled: bool = False
    streak: int | None
    # Kid mode: a minor tapped done and the mark awaits a parent. For the
    # tapping kid this is their own waiting state; for everyone else it flags
    # the card as needing approval. pending_by names the kid (one-shots; a
    # routine's per-person state lives in assignee_completions instead).
    pending: bool = False
    pending_by: int | None = None
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


class PendingApprovalOut(BaseModel):
    """One check-off waiting on a parent, for the "Waiting on you" list. Item
    and kid ride along so the row renders without extra fetches, and marks
    from earlier days (which today's feed wouldn't surface) still show up."""

    item_id: int
    title: str
    kind: ItemKind
    user: UserOut  # the kid who tapped it
    date_for: dt.date
    completed_at: dt.datetime


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


# Measurement units for an ingredient amount. Mass units (a solid) and volume
# units (a liquid) never mix within one ingredient — the unit must match its
# food's base measure, enforced when the recipe is saved.
MassUnit = Literal["g", "oz", "lb"]
VolumeUnit = Literal["ml", "floz", "cup", "tbsp", "tsp"]
AmountUnit = Literal["g", "oz", "lb", "ml", "floz", "cup", "tbsp", "tsp"]
BaseUnit = Literal["g", "ml"]


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
    saturated_fat_g: float | None = Field(default=None, ge=0, le=10000)
    trans_fat_g: float | None = Field(default=None, ge=0, le=10000)
    cholesterol_mg: float | None = Field(default=None, ge=0, le=10_000_000)
    sodium_mg: float | None = Field(default=None, ge=0, le=10_000_000)
    fiber_g: float | None = Field(default=None, ge=0, le=10000)
    sugar_g: float | None = Field(default=None, ge=0, le=10000)
    amount: float = Field(gt=0, le=100000)
    unit: AmountUnit = "g"


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
    saturated_fat_g: float | None
    trans_fat_g: float | None
    cholesterol_mg: float | None
    sodium_mg: float | None
    fiber_g: float | None
    sugar_g: float | None


class RecipeMacros(BaseModel):
    """Per-serving nutrition, computed from the ingredient lines. A field is null
    only when no ingredient supplied that nutrient at all (so an empty recipe, or
    foods that never listed protein, reads as "—" rather than a misleading 0)."""

    calories: float | None
    protein_g: float | None
    carbs_g: float | None
    fat_g: float | None
    saturated_fat_g: float | None
    trans_fat_g: float | None
    cholesterol_mg: float | None
    sodium_mg: float | None
    fiber_g: float | None
    sugar_g: float | None


class RecipeOut(BaseModel):
    id: int
    name: str
    servings: int
    steps: str
    ingredients: list[RecipeIngredientOut]
    # Where this recipe currently sits on village shelves (own recipes only).
    shared_to: list["RecipeShareOut"] = []
    # "Copy of X shared by Alex from Team Jam on ..." when adopted.
    provenance: str | None = None
    per_serving: RecipeMacros


# ---- meals (the family menu) ----------------------------------------------------


class MealIn(BaseModel):
    """Plan one slot of one day: a saved recipe, or a typed title for nights
    that aren't a recipe. Exactly one of the two."""

    date_for: dt.date
    slot: MealSlot = MealSlot.dinner
    recipe_id: int | None = None
    custom_title: str | None = Field(default=None, max_length=120)


class MealTimeIn(BaseModel):
    """Set (or clear, with null) when dinner happens. Independent of the
    pick: a time can exist before anyone knows what's cooking."""

    date_for: dt.date
    slot: MealSlot = MealSlot.dinner
    time_of_day: dt.time | None = None


class MealOut(BaseModel):
    date_for: dt.date
    slot: MealSlot
    recipe_id: int | None
    recipe_name: str | None  # joined for display; None for a custom title
    custom_title: str | None
    time_of_day: dt.time | None = None
    # The recipe's computed per-serving nutrition, so the menu can show what a
    # night amounts to without another request. None for custom-title nights.
    per_serving: "RecipeMacros | None" = None

    model_config = {"from_attributes": True}


class RecipeToGroceryIn(BaseModel):
    """Where a recipe's ingredients land: a store's list, or None = Unsorted."""

    list_id: int | None = None


# ---- foods (database cache + custom) -------------------------------------------


# The full Nutrition Facts label, per 100 g. calories + the four base macros
# came with 0014; the rest arrived with 0016. cholesterol/sodium are in mg (as
# labels print them), everything else in grams. The router and recipe totals
# both iterate this, so a new nutrient is added in one place.
FOOD_NUTRIENTS = (
    "calories",
    "protein_g",
    "carbs_g",
    "fat_g",
    "saturated_fat_g",
    "trans_fat_g",
    "cholesterol_mg",
    "sodium_mg",
    "fiber_g",
    "sugar_g",
)


class FoodServingIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    grams: float = Field(gt=0, le=100000)


class FoodServingOut(BaseModel):
    name: str
    grams: float

    model_config = {"from_attributes": True}


class SavedFoodIn(BaseModel):
    """A food being pinned to the family's Saved Foods: the same
    find-or-create contract as recipe ingredients, minus any amount (a pin
    is about the food, not a portion). food_id reuses an already-stored row;
    otherwise source/source_id/name/macros describe it."""

    food_id: int | None = None
    source: FoodSource
    source_id: str | None = Field(default=None, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    brand: str = Field(default="", max_length=120)
    calories: float | None = Field(default=None, ge=0, le=100000)
    protein_g: float | None = Field(default=None, ge=0, le=10000)
    carbs_g: float | None = Field(default=None, ge=0, le=10000)
    fat_g: float | None = Field(default=None, ge=0, le=10000)
    saturated_fat_g: float | None = Field(default=None, ge=0, le=10000)
    trans_fat_g: float | None = Field(default=None, ge=0, le=10000)
    cholesterol_mg: float | None = Field(default=None, ge=0, le=10_000_000)
    sodium_mg: float | None = Field(default=None, ge=0, le=10_000_000)
    fiber_g: float | None = Field(default=None, ge=0, le=10000)
    sugar_g: float | None = Field(default=None, ge=0, le=10000)


class FoodOut(BaseModel):
    """A food with per-100g nutrition. id is None for an un-saved search/barcode
    result (the client saves it when it's used in a recipe); set for a stored
    custom food."""

    id: int | None = None
    source: FoodSource
    source_id: str | None = None
    name: str
    brand: str = ""
    base_unit: BaseUnit = "g"  # measure family: "g" (mass) or "ml" (volume)
    serving: str = ""  # display label for the source's serving; "" when unknown
    servings: list[FoodServingOut] = []  # structured named portions (custom foods)
    calories: float | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    saturated_fat_g: float | None = None
    trans_fat_g: float | None = None
    cholesterol_mg: float | None = None
    sodium_mg: float | None = None
    fiber_g: float | None = None
    sugar_g: float | None = None

    model_config = {"from_attributes": True}


class FoodIn(BaseModel):
    """A parent adding a custom food the databases lack. They give one or more
    named servings and the Nutrition Facts as printed for one chosen serving
    (basis_index); the server converts to per-100g so it sits alongside the
    USDA/Open Food Facts foods and feeds the gram-based recipe math."""

    name: str = Field(min_length=1, max_length=200)
    brand: str = Field(default="", max_length=120)
    # A product barcode to remember this food by (digits as printed under the
    # bars). Scanning that code later resolves to this food directly, without
    # asking Open Food Facts — how a scanned-but-unknown product, entered once,
    # stays known to the family forever.
    barcode: str | None = Field(default=None, pattern=r"^[0-9]{8,14}$")
    # "g" (measure servings by weight) or "ml" (by volume, for a liquid). The
    # serving sizes below are in this unit, and nutrition is stored per 100 of it.
    base_unit: BaseUnit = "g"
    servings: list[FoodServingIn] = Field(min_length=1, max_length=20)
    basis_index: int = Field(default=0, ge=0)  # which serving the values are per
    # Nutrition as entered, per servings[basis_index]. mg for cholesterol/sodium.
    calories: float | None = Field(default=None, ge=0, le=1_000_000)
    protein_g: float | None = Field(default=None, ge=0, le=100000)
    carbs_g: float | None = Field(default=None, ge=0, le=100000)
    fat_g: float | None = Field(default=None, ge=0, le=100000)
    saturated_fat_g: float | None = Field(default=None, ge=0, le=100000)
    trans_fat_g: float | None = Field(default=None, ge=0, le=100000)
    cholesterol_mg: float | None = Field(default=None, ge=0, le=10_000_000)
    sodium_mg: float | None = Field(default=None, ge=0, le=10_000_000)
    fiber_g: float | None = Field(default=None, ge=0, le=100000)
    sugar_g: float | None = Field(default=None, ge=0, le=100000)

    @model_validator(mode="after")
    def _basis_in_range(self) -> "FoodIn":
        if self.basis_index >= len(self.servings):
            raise ValueError("basis_index is out of range for the servings given")
        return self


# ---- the nutrition diary ---------------------------------------------------------


class DiaryEntryIn(BaseModel):
    """Logging one thing you ate: a recipe by servings (recipe_id + amount), or
    a food with the same carried-payload contract as recipe ingredient lines —
    an id when it's already saved, otherwise source/source_id/name/nutrition to
    find-or-create. The server computes the entry's nutrition; the client never
    supplies totals."""

    date_for: dt.date
    slot: DiarySlot
    time_of_day: dt.time | None = None
    amount: float = Field(gt=0, le=100000)
    unit: AmountUnit = "g"  # ignored for recipe entries (they're in servings)
    label: str | None = Field(default=None, max_length=60)

    recipe_id: int | None = None

    # Food payload, RecipeIngredientIn-shaped (used only when recipe_id is None).
    food_id: int | None = None
    source: FoodSource | None = None
    source_id: str | None = Field(default=None, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    brand: str = Field(default="", max_length=120)
    calories: float | None = Field(default=None, ge=0, le=100000)
    protein_g: float | None = Field(default=None, ge=0, le=10000)
    carbs_g: float | None = Field(default=None, ge=0, le=10000)
    fat_g: float | None = Field(default=None, ge=0, le=10000)
    saturated_fat_g: float | None = Field(default=None, ge=0, le=10000)
    trans_fat_g: float | None = Field(default=None, ge=0, le=10000)
    cholesterol_mg: float | None = Field(default=None, ge=0, le=10_000_000)
    sodium_mg: float | None = Field(default=None, ge=0, le=10_000_000)
    fiber_g: float | None = Field(default=None, ge=0, le=10000)
    sugar_g: float | None = Field(default=None, ge=0, le=10000)

    @model_validator(mode="after")
    def _one_source(self) -> "DiaryEntryIn":
        if self.recipe_id is None:
            if self.food_id is None and (self.source is None or self.name is None):
                raise ValueError("An entry needs a recipe, a saved food, or a food payload")
        return self


class DiaryEntryUpdate(BaseModel):
    """Editing an entry: portion, when, or which group. Nutrition is
    recomputed (or, when its source is gone, scaled) server-side."""

    amount: float | None = Field(default=None, gt=0, le=100000)
    unit: AmountUnit | None = None
    label: str | None = Field(default=None, max_length=60)
    slot: DiarySlot | None = None
    time_of_day: dt.time | None = None
    date_for: dt.date | None = None


class DiaryEntryOut(BaseModel):
    id: int
    date_for: dt.date
    slot: DiarySlot
    time_of_day: dt.time | None
    name: str
    brand: str
    food_id: int | None
    recipe_id: int | None
    amount: float
    unit: str
    label: str | None
    calories: float | None
    protein_g: float | None
    carbs_g: float | None
    fat_g: float | None
    saturated_fat_g: float | None
    trans_fat_g: float | None
    cholesterol_mg: float | None
    sodium_mg: float | None
    fiber_g: float | None
    sugar_g: float | None

    model_config = {"from_attributes": True}


class TargetsIn(BaseModel):
    """A member setting their own daily budget and macro split. The
    percentages must sum to 100 (checked in the endpoint so it's a friendly
    400, not a validation-shaped 422). mode=auto asks the health profile for
    the calorie budget instead of the typed one (the typed value is kept as
    the fallback); the macro split is the member's own either way."""

    calories: int = Field(ge=500, le=20000)
    protein_pct: int = Field(ge=0, le=100)
    carbs_pct: int = Field(ge=0, le=100)
    fat_pct: int = Field(ge=0, le=100)
    mode: TargetMode = TargetMode.manual


class TargetsOut(BaseModel):
    mode: TargetMode
    calories: int
    protein_pct: int
    carbs_pct: int
    fat_pct: int
    # Derived gram targets (4 kcal/g protein and carbs, 9 kcal/g fat), so every
    # surface shows the same numbers.
    protein_g: float
    carbs_g: float
    fat_g: float
    # Calories a day's logged exercise burned, already INCLUDED in `calories`
    # above (and the gram targets) when the targets are served for a specific
    # day. Zero on the date-less /diary/targets endpoint.
    exercise_kcal: float = 0.0


# ---- health profile, weigh-ins, and the computed calorie target -------------------


class HealthProfileIn(BaseModel):
    """A member filling in (part of) their health settings; omitted fields
    stay as they are. All optional by design - the computed panel simply
    waits until enough is known."""

    birthdate: dt.date | None = None
    sex: Sex | None = None
    height_cm: float | None = Field(default=None, gt=50, le=272)
    activity_level: ActivityLevel | None = None


class GoalIn(BaseModel):
    """A weight goal. The rate is capped to what's considered safe without
    medical supervision (0.25-2 lb/week)."""

    goal: GoalType
    rate_lbs_per_week: float | None = Field(default=None, ge=0.25, le=2.0)
    goal_weight_kg: float | None = Field(default=None, gt=20, le=500)
    goal_body_fat_pct: float | None = Field(default=None, ge=1, le=75)


class WeightIn(BaseModel):
    date_for: dt.date
    weight_kg: float = Field(gt=20, le=500)
    body_fat_pct: float | None = Field(default=None, ge=1, le=75)


class WeightOut(BaseModel):
    date_for: dt.date
    weight_kg: float
    body_fat_pct: float | None

    model_config = {"from_attributes": True}


class HealthProfileOut(BaseModel):
    birthdate: dt.date | None
    sex: Sex | None
    height_cm: float | None
    activity_level: ActivityLevel | None
    goal: GoalType | None
    rate_lbs_per_week: float | None
    goal_weight_kg: float | None
    goal_body_fat_pct: float | None

    model_config = {"from_attributes": True}


class ComputedHealthOut(BaseModel):
    """What the math says (see app.health): resting burn, daily burn, and the
    goal-adjusted calorie target. Estimates, not medical advice."""

    bmr: float
    tdee: float
    maintenance_calories: int
    auto_calories: int
    at_goal: bool


class HealthOut(BaseModel):
    profile: HealthProfileOut | None
    latest_weight: WeightOut | None
    weights: list[WeightOut]  # recent first
    computed: ComputedHealthOut | None


class ExerciseIn(BaseModel):
    """Logging a workout. The server computes the burn from the member's
    latest weigh-in; the client never supplies calories."""

    date_for: dt.date
    activity: Literal["running", "walking"]  # keys of app.health.EXERCISES
    effort: ExerciseEffort
    minutes: float = Field(gt=0, le=1440)
    time_of_day: dt.time | None = None


class ExerciseUpdate(BaseModel):
    minutes: float | None = Field(default=None, gt=0, le=1440)
    effort: ExerciseEffort | None = None
    time_of_day: dt.time | None = None
    date_for: dt.date | None = None


class ExerciseOut(BaseModel):
    id: int
    date_for: dt.date
    time_of_day: dt.time | None
    activity: str
    label: str  # display name from the catalog
    effort: ExerciseEffort
    minutes: float
    kcal: float


class DiaryDayOut(BaseModel):
    """One member's diary for one day: their targets, what the day's entries
    total so far, and the entries themselves (the client groups by slot).
    Exercise rides along: the day's burn is already folded into targets."""

    date: dt.date
    targets: TargetsOut
    consumed: RecipeMacros
    # The day's imported workout calories, present only when the member opted
    # in to counting them; the client uses it to say where the day's
    # earn-back came from.
    watch_kcal: float | None = None
    entries: list[DiaryEntryOut]
    exercise: list[ExerciseOut] = []
    burned: float = 0.0
    # The day is locked in: entries refuse changes until unlocked.
    locked: bool = False


class DiaryLockOut(BaseModel):
    """The lock/unlock response: the day's new state, and what the lock just
    earned (+2 the first time a date is locked, 0 forever after)."""

    locked: bool
    crumbs_awarded: int = 0


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
    # The member's breadcrumb level — always visible inside the family (it
    # sits in the little circle beside the name).
    level: int = 1


class VersesOut(BaseModel):
    enabled: bool
    checks: list[bool]  # today's three, in verse order
    streak: int
    # What the check that produced this response earned (the day's +3 and any
    # milestone bonus), so the UI can float the number without guessing.
    crumbs_awarded: int = 0


class VerseCheckIn(BaseModel):
    date_for: dt.date
    verse_idx: int = Field(ge=0, le=2)


class VerseSettingsIn(BaseModel):
    """Only the fields sent change."""

    enabled: bool | None = None


class ProfileOut(FamilyMemberOut):
    bio: str
    created_at: dt.datetime
    # The tap-profile modal's economy panel.
    crumbs: int = 0
    tier: str = "slice"
    level_progress: int = 0  # crumbs into the current level
    next_level_cost: int = 10


class ProfileUpdateIn(BaseModel):
    """A member editing their own profile."""

    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    bio: str | None = Field(default=None, max_length=500)
    theme: Literal["light", "dark"] | None = None
    # Opt in to showing today's mood and status on the village card. Off by
    # default; minors are excluded server-side regardless.
    village_presence: bool | None = None
    # Opt in to showing level + crumb total to village members.
    share_level: bool | None = None


class CrumbsOut(BaseModel):
    """The signed-in member's own economy state (the profile modal + banner)."""

    total: int
    level: int
    tier: str
    level_progress: int
    next_level_cost: int
    today: int  # crumbs earned today
    login_award_today: bool  # the daily +1 landed on this family-local day


# ---- the dinner plan -----------------------------------------------------------


class DinnerVoteIn(BaseModel):
    """An adult's pick for tonight. detail is the short typed bit ("Chipotle");
    homemade may carry a recipe instead (or as well — the recipe name wins)."""

    choice: DinnerChoice
    detail: str = Field(default="", max_length=30)
    recipe_id: int | None = None


class DinnerVoterOut(BaseModel):
    id: int
    display_name: str
    avatar_updated_at: dt.datetime | None


class DinnerVoteOut(BaseModel):
    user: DinnerVoterOut
    choice: DinnerChoice
    detail: str
    recipe_id: int | None
    recipe_name: str | None


class DinnerPlanOut(BaseModel):
    """The standing plan for a night: every adult's pick (in voting order)
    plus the family's kids, whose avatars the client pins to the leading
    choice — they eat whatever wins, they don't vote."""

    date_for: dt.date
    votes: list[DinnerVoteOut]
    kids: list[DinnerVoterOut]


# ---- the village recipe shelf --------------------------------------------------------


class ShareRecipeIn(BaseModel):
    recipe_id: int


class RecipeShareOut(BaseModel):
    share_id: int
    village_id: int
    village_name: str


class SharedIngredientOut(BaseModel):
    """An ingredient line as village-mates see it: what and how much, with its
    macro contribution — and NO ids. A share grants reading and copying, never
    a handle into the owning family's rows."""

    name: str
    brand: str
    amount: float
    unit: str
    grams: float
    calories: float | None
    protein_g: float | None
    carbs_g: float | None
    fat_g: float | None
    saturated_fat_g: float | None
    trans_fat_g: float | None
    cholesterol_mg: float | None
    sodium_mg: float | None
    fiber_g: float | None
    sugar_g: float | None


class SharedRecipeOut(BaseModel):
    """A shelf row: the recipe at arm's length (no recipe id), with village
    and family attribution. is_own lets the sharing family see the Unshare
    action on their entries."""

    share_id: int
    village_id: int
    village_name: str
    family_id: int
    family_name: str
    # First name of the parent who shared it ("Shared by Alex from Team Jam").
    shared_by: str | None
    is_own: bool
    name: str
    servings: int
    per_serving: RecipeMacros
    created_at: dt.datetime
    # The recipe is a live pointer: the owner's edits show here. This is when
    # they last touched it.
    updated_at: dt.datetime


class SharedRecipeDetailOut(SharedRecipeOut):
    steps: str
    ingredients: list[SharedIngredientOut]


# ---- server overview ---------------------------------------------------------------


class OverviewUserOut(BaseModel):
    id: int
    username: str
    display_name: str
    role: Role
    is_admin: bool
    is_owner: bool

    model_config = {"from_attributes": True}


class OverviewFamilyOut(BaseModel):
    id: int
    name: str
    users: list[OverviewUserOut]


class OverviewVillageOut(BaseModel):
    id: int
    name: str
    families: list[OverviewFamilyOut]


class OverviewOut(BaseModel):
    """The whole install at a glance, for the server admin alone: every
    village with its families, then families in no village, then accounts
    that haven't founded a family yet."""

    villages: list[OverviewVillageOut]
    solo_families: list[OverviewFamilyOut]
    homeless_users: list[OverviewUserOut]


# ---- signup invites --------------------------------------------------------------


class SignupInviteIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)


class SignupInviteOut(BaseModel):
    """The minted invite. `code` appears here and nowhere else, ever."""

    code: str
    display_name: str
    expires_at: dt.datetime


class InviteCodeIn(BaseModel):
    code: str = Field(min_length=1, max_length=20)


class InviteCheckOut(BaseModel):
    display_name: str


class InviteRedeemIn(InviteCodeIn):
    """The invitee picks their own identity: username, optionally a tweak to
    the name the admin typed, and a password nobody else has ever seen."""

    username: str = Field(min_length=3, max_length=50)
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=128)
    # Optional: prefills the Nutrition health profile.
    birthdate: dt.date | None = None


# ---- villages -------------------------------------------------------------------


class VillageIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class VillageJoinIn(BaseModel):
    code: str = Field(min_length=1, max_length=20)


class VillageParentOut(BaseModel):
    """A parent as village-mates see them: name, id, photo — and, ONLY when
    that parent opted in (village_presence), today's mood and status. The
    avatar image is the one other thing served across the family wall;
    profiles and boards stay sealed, and children never appear at all."""

    id: int
    display_name: str
    avatar_updated_at: dt.datetime | None = None
    # Whether this parent shares mood/status at all — the mini profile uses
    # it to say "private" honestly instead of guessing from empty fields.
    presence: bool = False
    mood: MoodOut | None = None
    # Today's status line, empty unless presence is on (statuses clear
    # themselves overnight like moods).
    status: str = ""
    # Breadcrumb level (and total, for the mini profile), present ONLY when
    # that parent opted in to sharing it (share_level). Numbers, nothing else.
    level: int | None = None
    crumbs: int | None = None


class VillageFamilyOut(BaseModel):
    id: int
    name: str
    joined_at: dt.datetime
    parents: list[VillageParentOut] = []
    # How many kid accounts the family has on the app. Only the COUNT crosses
    # the wall; kids' names, faces, and everything else stay sealed.
    kid_count: int = 0


class VillageCheckOut(BaseModel):
    """What a held code opens: enough to ask "Join <name>?" and nothing more.
    Non-consuming; only reachable with a live code in hand."""

    name: str
    families: list[str]


class VillageOut(BaseModel):
    """A village as its members see it. Carries invite STATUS only — the code
    itself is stored as a hash and can never be read back, only regenerated
    (it appears exactly once, in the response that minted it)."""

    id: int
    name: str
    created_at: dt.datetime
    families: list[VillageFamilyOut]
    invite_active: bool
    invite_expires_at: dt.datetime | None
    # True when the REQUESTING family founded this village — founders may
    # delete it outright; everyone else may only leave.
    is_creator: bool = False


class VillageCreatedOut(VillageOut):
    invite_code: str


class VillageInviteOut(BaseModel):
    invite_code: str
    invite_expires_at: dt.datetime


# ---- web push -----------------------------------------------------------------


class PushKeys(BaseModel):
    """The browser-generated encryption keys that ride along with a
    PushSubscription (the standard subscription JSON's "keys" object)."""

    p256dh: str = Field(min_length=1, max_length=255)
    auth: str = Field(min_length=1, max_length=255)


class PushSubscriptionIn(BaseModel):
    endpoint: str = Field(min_length=1, max_length=2000)
    keys: PushKeys


class PushUnsubscribeIn(BaseModel):
    endpoint: str = Field(min_length=1, max_length=2000)


class PushKeyOut(BaseModel):
    key: str


class PushTestOut(BaseModel):
    sent: int


class PushPrefsIn(BaseModel):
    """A partial update: only the kinds being flipped, e.g. {"midday": false}.
    Kind names are validated against app.push.PREF_KINDS in the router."""

    prefs: dict[str, bool]


class PushPrefsOut(BaseModel):
    """The full map, every kind present, for the settings toggles."""

    prefs: dict[str, bool]


# ---- fitness (Apple Health import) -----------------------------------------------


class IngestTokenOut(BaseModel):
    """Shown exactly once, at mint time. The server keeps only the hash."""

    token: str
    # Where the exporter app should POST, relative to the app's address.
    path: str


class WorkoutOut(BaseModel):
    id: int
    activity: str
    started_at: dt.datetime
    ended_at: dt.datetime | None
    duration_s: float | None
    kcal: float | None
    distance_m: float | None
    avg_hr: float | None
    # Downsampled [lat, lon] pairs for the little route thumbnail, when the
    # exporter sent GPS data.
    route: list[list[float]] | None = None
    # Which dialect the workout came from ("apple" / "android").
    source: str = "apple"

    model_config = {"from_attributes": True}


class FitnessDayOut(BaseModel):
    steps: float | None
    active_kcal: float | None
    exercise_minutes: float | None
    resting_hr: float | None
    # Walking + running distance in meters (the client renders miles).
    distance: float | None = None


class FitnessWeekDayOut(BaseModel):
    """One day of the trailing week, every metric — the tab's mini charts."""

    date_for: dt.date
    steps: float | None
    active_kcal: float | None
    exercise_minutes: float | None
    resting_hr: float | None
    # Walking + running distance in meters (the client renders miles).
    distance: float | None = None


class FitnessGoalsOut(BaseModel):
    """The member's ring targets, already resolved: their own number where
    they set one, the recommended default where they didn't."""

    steps: int
    active_kcal: int
    exercise_minutes: int


class FitnessGoalsIn(BaseModel):
    """Only the fields sent change; an explicit null puts that goal back on
    the recommended default."""

    steps: int | None = Field(default=None, ge=1000, le=100000)
    active_kcal: int | None = Field(default=None, ge=50, le=5000)
    exercise_minutes: int | None = Field(default=None, ge=5, le=1440)


class FitnessHistoryOut(BaseModel):
    """A longer trailing window for the per-metric detail views; same day
    shape as the week, just more of it."""

    days: list[FitnessWeekDayOut]


class FitnessOut(BaseModel):
    connected: bool
    last_sync: dt.datetime | None
    today: FitnessDayOut
    week: list[FitnessWeekDayOut]
    workouts: list[WorkoutOut]
    goals: FitnessGoalsOut
    # Opt-in: watch workout calories raise the day's food budget.
    count_watch_kcal: bool = False


class WatchKcalIn(BaseModel):
    enabled: bool


class IngestResultOut(BaseModel):
    days: int
    workouts: int
    # Routines checked off by this sync (the per-routine workout opt-in).
    routines_completed: int = 0
