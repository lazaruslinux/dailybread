import datetime as dt

from pydantic import BaseModel, Field

from app.models import ItemKind, MoodLevel, Role


# Pydantic models define the JSON shapes for requests/responses and validate
# them automatically. They are separate from the SQLAlchemy ORM models so we
# never accidentally leak fields like password_hash to the client.


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    role: Role
    is_admin: bool
    # None only while a new-household account hasn't created its family yet;
    # the frontend uses this to show the create-your-family wizard.
    family_id: int | None = None

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


class ItemIn(BaseModel):
    """A parent creating a card for the board."""

    kind: ItemKind
    title: str = Field(min_length=1, max_length=120)
    notes: str = Field(default="", max_length=300)
    assignee_id: int | None = None  # None means the whole family
    time_of_day: dt.time | None = None
    date_for: dt.date | None = None  # todos/events; routines leave it unset


class ItemUpdate(BaseModel):
    """Editing a card. Omitted fields stay unchanged; explicit nulls clear.

    Pydantic can't tell "omitted" from "sent as null" without this trick:
    model_fields_set records which keys were actually in the JSON body.
    """

    title: str | None = Field(default=None, min_length=1, max_length=120)
    notes: str | None = Field(default=None, max_length=300)
    assignee_id: int | None = None
    time_of_day: dt.time | None = None
    date_for: dt.date | None = None


class FeedItemOut(BaseModel):
    id: int
    kind: ItemKind
    title: str
    notes: str
    assignee: UserOut | None
    time_of_day: dt.time | None
    date_for: dt.date | None
    completed: bool
    # Consecutive days done, routines only. None for todos/events.
    streak: int | None

    model_config = {"from_attributes": True}


class FeedOut(BaseModel):
    """Everything the home screen needs for one day, in three buckets."""

    date: dt.date
    today: list[FeedItemOut]  # timed + dated cards, sorted by time
    anytime: list[FeedItemOut]  # undated, uncompleted todos
    upcoming: list[FeedItemOut]  # dated cards in the next 7 days


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


# ---- profiles and moods --------------------------------------------------------


class MoodOut(BaseModel):
    level: MoodLevel
    hidden: bool

    model_config = {"from_attributes": True}


class MoodIn(BaseModel):
    date_for: dt.date
    level: MoodLevel
    hidden: bool = False


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
