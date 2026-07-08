import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.models import (
    ActivityLevel,
    DiarySlot,
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
    # Kid mode. birthdate is admin-set; is_minor is derived (child role and
    # under 18, or no birthdate at all) and rides along on every user payload
    # including /auth/me, so the frontend can shape itself without extra calls.
    birthdate: dt.date | None = None
    is_minor: bool = False

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
    # Kid mode switch-off date. Leaving it empty keeps a child account a minor.
    birthdate: dt.date | None = None
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
    per_serving: RecipeMacros


# ---- meals (the family menu) ----------------------------------------------------


class MealIn(BaseModel):
    """Plan one slot of one day: a saved recipe, or a typed title for nights
    that aren't a recipe. Exactly one of the two."""

    date_for: dt.date
    slot: MealSlot = MealSlot.dinner
    recipe_id: int | None = None
    custom_title: str | None = Field(default=None, max_length=120)


class MealOut(BaseModel):
    date_for: dt.date
    slot: MealSlot
    recipe_id: int | None
    recipe_name: str | None  # joined for display; None for a custom title
    custom_title: str | None
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
    barcode: str | None = Field(default=None, pattern=r"^[0-9]{6,14}$")
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
    entries: list[DiaryEntryOut]
    exercise: list[ExerciseOut] = []
    burned: float = 0.0


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
