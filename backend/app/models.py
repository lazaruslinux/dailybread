import datetime as dt
import enum

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
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
    # Admin-set, drives kid mode (see is_minor). Deliberately independent from
    # health_profiles.birthdate, which is a self-reported BMR input.
    birthdate: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    @property
    def is_minor(self) -> bool:
        """Kid mode: child accounts under 18 get the shepherded experience —
        no nutrition/health area, only their own slice of the board, and
        check-offs that wait for a parent. No birthdate means minor, so a kid
        is never accidentally unrestricted; restrictions lift by themselves on
        the 18th birthday (role stays child). Same server-local clock as the
        rest of the app's day math."""
        if self.role != Role.child:
            return False
        if self.birthdate is None:
            return True
        today = dt.date.today()
        try:
            eighteenth = self.birthdate.replace(year=self.birthdate.year + 18)
        except ValueError:  # born Feb 29; turns 18 on Mar 1 of a common year
            eighteenth = self.birthdate.replace(year=self.birthdate.year + 18, month=3, day=1)
        return today < eighteenth


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

    # Start time (the "From"). Activities and appointments need one (unless the
    # appointment is all-day); routines and tasks may leave it NULL.
    time_of_day: Mapped[dt.time | None] = mapped_column(Time, nullable=True)
    # End time (the "To"), for the event kinds that span a block. NULL on
    # routines, tasks, and all-day appointments.
    end_time: Mapped[dt.time | None] = mapped_column(Time, nullable=True)
    # An all-day appointment: a date with no times (Outlook's "all day").
    all_day: Mapped[bool] = mapped_column(Boolean, default=False)
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
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    recipe: Mapped["Recipe | None"] = relationship()


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
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    # Named real-world portions (e.g. "1 slice" = 21 g). Nutrition stays per-100g;
    # servings are how a person picks a portion. Ordered by position.
    servings: Mapped[list["FoodServing"]] = relationship(
        back_populates="food",
        cascade="all, delete-orphan",
        order_by="FoodServing.position",
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
    birthdate: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
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
    """One row per card per day a reminder went out, so a restarted server
    (or two ticks racing) never notifies the same card twice."""

    __tablename__ = "reminder_log"
    __table_args__ = (UniqueConstraint("item_id", "date_for", name="uq_reminder_item_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), index=True
    )
    date_for: Mapped[dt.date] = mapped_column(Date)


class DigestLog(Base):
    """One row per member per day the morning digest was handled (sent, or
    deliberately not — an empty board claims its row too), so a restart or a
    racing tick never greets the same phone twice."""

    __tablename__ = "digest_log"
    __table_args__ = (UniqueConstraint("user_id", "date_for", name="uq_digest_user_day"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    date_for: Mapped[dt.date] = mapped_column(Date)
