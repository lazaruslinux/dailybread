"""Villages: private circles of linked families.

A village is invitation-only plumbing between households on the same install.
Nothing is discoverable — no directory, no search, no friend requests — and a
village you don't belong to 404s exactly like it doesn't exist. What crosses
the family wall is deliberately tiny (a shared recipe shelf and opt-in
mood/status, later slices); boards, kitchens, and calendars never do.

Invite codes: 8 characters from an alphabet without lookalikes (no 0/O/1/I/L),
so a code survives being read over the phone. Only the SHA-256 of a code is
stored — a database read never exposes a live door key — and the plaintext is
returned exactly once, by the endpoint that minted it. One active code per
village, single-use (a successful join consumes it), regenerable by any member
family's admin. Wrong, expired, and never-existed codes all answer with the
same 404, and guesses are throttled like failed logins, so probing reveals
nothing about which villages exist.
"""
import datetime as dt
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app import inbox, push, throttle, village_events
from app.clock import family_now, shift_schedule
from app.invitecodes import hash_code, mint_code, normalize, pretty, still_valid
from app.db import get_db
from app.deps import require_admin, require_adult, require_family, require_parent
from app.models import (
    Completion,
    Family,
    Food,
    FoodServing,
    FoodSource,
    Item,
    ItemKind,
    Recipe,
    RecipeIngredient,
    Role,
    RsvpStatus,
    User,
    Village,
    VillageEvent,
    VillageEventAttendee,
    VillageEventRsvp,
    VillageFamily,
    VillageFood,
    VillageRecipe,
)
from app.schemas import (
    FOOD_NUTRIENTS,
    AttendeeOut,
    FoodOut,
    FoodServingOut,
    KidAvatarIn,
    MoodOut,
    RecipeOut,
    RsvpIn,
    ShareEventIn,
    ShareFoodIn,
    SharedFoodDetailOut,
    SharedFoodOut,
    SharedIngredientOut,
    SharedRecipeDetailOut,
    SharedRecipeOut,
    ShareRecipeIn,
    VillageCheckOut,
    VillageCreatedOut,
    VillageEventOut,
    VillageEventRsvpOut,
    VillageFamilyOut,
    VillageIn,
    VillageInviteOut,
    VillageJoinIn,
    VillageOut,
    VillageParentOut,
)

log = logging.getLogger("dailybread.villages")

router = APIRouter(prefix="/villages", tags=["villages"])

INVITE_TTL = dt.timedelta(hours=48)


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _invite_active(village: Village, now: dt.datetime) -> bool:
    return village.invite_code_hash is not None and still_valid(
        village.invite_expires_at, now
    )


def _member_village(db: Session, village_id: int, family_id: int) -> Village:
    """A village this family doesn't belong to 404s like it doesn't exist."""
    village = db.get(Village, village_id)
    membership = (
        None
        if village is None
        else db.scalar(
            select(VillageFamily).where(
                VillageFamily.village_id == village_id,
                VillageFamily.family_id == family_id,
            )
        )
    )
    if village is None or membership is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such village")
    return village


def _village_out(db: Session, village: Village, viewer_family_id: int) -> VillageOut:
    rows = db.execute(
        select(VillageFamily, Family)
        .join(Family, Family.id == VillageFamily.family_id)
        .where(VillageFamily.village_id == village.id)
        .order_by(VillageFamily.joined_at, VillageFamily.id)
    ).all()
    # The faces of the village: every member family's PARENTS. Children are
    # never shown across the family wall, whatever their birthdate says.
    # A parent who opted in (village_presence) shares today's mood (unless
    # hidden — hidden reads exactly like unset) AND today's status line, for
    # the mini profile. Boards, kitchens, and calendars still never cross.
    from app.models import Mood

    parents_by_family: dict[int, list[VillageParentOut]] = {}
    family_ids = [family.id for _, family in rows]
    if family_ids:
        parents = db.scalars(
            select(User)
            .where(User.family_id.in_(family_ids), User.role == Role.parent)
            .order_by(User.created_at, User.id)
        ).all()
        today = dt.date.today()
        sharer_ids = [u.id for u in parents if u.village_presence]
        moods = {
            m.user_id: m
            for m in db.scalars(
                select(Mood).where(Mood.date_for == today, Mood.user_id.in_(sharer_ids))
            )
        } if sharer_ids else {}
        # Levels cross the wall only by their own opt-in, separate from mood
        # presence; the numbers are all that travel — never the ledger.
        from app import crumbs

        totals = crumbs.totals_for(db, [u.id for u in parents if u.share_level])
        for user in parents:
            mood = moods.get(user.id)
            sharing = user.village_presence
            total = totals.get(user.id, 0) if user.share_level else None
            parents_by_family.setdefault(user.family_id, []).append(
                VillageParentOut(
                    id=user.id,
                    display_name=user.display_name,
                    avatar_updated_at=user.avatar_updated_at,
                    presence=sharing,
                    mood=(
                        MoodOut.model_validate(mood)
                        if sharing and mood is not None and not mood.hidden
                        else None
                    ),
                    status=(user.bio if sharing and user.status_date == today else ""),
                    level=crumbs.level_of(total)[0] if total is not None else None,
                    crumbs=total,
                )
            )
    # Kid accounts cross the wall as a COUNT only, nothing else.
    kid_counts = dict(
        db.execute(
            select(User.family_id, func.count())
            .where(User.family_id.in_(family_ids), User.role == Role.child)
            .group_by(User.family_id)
        ).all()
    ) if family_ids else {}
    active = _invite_active(village, _utcnow())
    return VillageOut(
        id=village.id,
        name=village.name,
        created_at=village.created_at,
        families=[
            VillageFamilyOut(
                id=family.id,
                name=family.name,
                joined_at=vf.joined_at,
                parents=parents_by_family.get(family.id, []),
                kid_count=kid_counts.get(family.id, 0),
            )
            for vf, family in rows
        ],
        invite_active=active,
        invite_expires_at=village.invite_expires_at if active else None,
        is_creator=village.created_by_family_id == viewer_family_id,
    )


def _family_in_a_village(db: Session, family_id: int) -> bool:
    return (
        db.scalar(select(VillageFamily).where(VillageFamily.family_id == family_id))
        is not None
    )


@router.get("", response_model=list[VillageOut])
def list_villages(db: Session = Depends(get_db), user: User = Depends(require_adult)):
    """The family's villages. Adults may look; only admins change them. The
    roster carries other households' names, moods, and levels, so minors
    don't get it — kids' only cross-family window is the recipe shelf."""
    villages = db.scalars(
        select(Village)
        .join(VillageFamily, VillageFamily.village_id == Village.id)
        .where(VillageFamily.family_id == user.family_id)
        .order_by(Village.created_at, Village.id)
    ).all()
    return [_village_out(db, v, user.family_id) for v in villages]


@router.post("", response_model=VillageCreatedOut, status_code=status.HTTP_201_CREATED)
def create_village(
    data: VillageIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Found a village: the creating family is its first member, and the
    response carries the invite code — the only time it is ever shown.
    A family may JOIN many villages but FOUND only one."""
    founded = db.scalar(
        select(Village).where(Village.created_by_family_id == admin.family_id)
    )
    if founded is not None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Your family already created a village"
        )
    code = mint_code()
    village = Village(
        name=data.name.strip(),
        created_by_family_id=admin.family_id,
        invite_code_hash=hash_code(code),
        invite_expires_at=_utcnow() + INVITE_TTL,
    )
    db.add(village)
    db.flush()
    db.add(VillageFamily(village_id=village.id, family_id=admin.family_id))
    db.commit()
    db.refresh(village)
    base = _village_out(db, village, admin.family_id)
    return VillageCreatedOut(**base.model_dump(), invite_code=pretty(code))


def _village_for_code(db: Session, raw: str, throttle_user: str) -> Village:
    """The throttled door: turn a submitted code into its village, or record
    a failure and answer the uniform 404."""
    key = f"village-join:{throttle_user}"
    if throttle.too_many_failures(key):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Try again later."
        )
    code = normalize(raw)
    village = (
        db.scalar(select(Village).where(Village.invite_code_hash == hash_code(code)))
        if code
        else None
    )
    if village is None or not _invite_active(village, _utcnow()):
        throttle.record_failure(key)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That code isn't valid")
    return village


@router.post("/join/check", response_model=VillageCheckOut)
def check_join_code(
    data: VillageJoinIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """What would this code join? Drives the "Join <name>?" confirmation
    without consuming the code. Same throttle bucket as joining."""
    village = _village_for_code(db, data.code, admin.username)
    names = db.scalars(
        select(Family.name)
        .join(VillageFamily, VillageFamily.family_id == Family.id)
        .where(VillageFamily.village_id == village.id)
        .order_by(VillageFamily.joined_at, VillageFamily.id)
    ).all()
    return VillageCheckOut(name=village.name, families=list(names))


@router.post("/join", response_model=VillageOut)
def join_village(
    data: VillageJoinIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Join with an invite code. Wrong, expired, and nonexistent codes are one
    indistinguishable 404; attempts are throttled like failed logins."""
    village = _village_for_code(db, data.code, admin.username)

    # A valid code in hand means the village's existence isn't a secret from
    # this caller, so this refusal can say what it is. The code stays live —
    # it was minted for someone else.
    if db.scalar(
        select(VillageFamily).where(
            VillageFamily.village_id == village.id,
            VillageFamily.family_id == admin.family_id,
        )
    ):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Your family is already in this village"
        )

    db.add(VillageFamily(village_id=village.id, family_id=admin.family_id))
    # Single-use: the join consumes the code.
    village.invite_code_hash = None
    village.invite_expires_at = None
    db.commit()
    throttle.clear(f"village-join:{admin.username}")
    db.refresh(village)
    # The village's other families hear a new one arrived (inbox-only; a join
    # is news, not an interruption). The joining family is excluded — it knows
    # it joined.
    family = db.get(Family, admin.family_id)
    _notify_village(
        db,
        _village_adults(db, village.id, exclude_family=admin.family_id),
        "village",
        f"{family.name} joined {village.name}",
        "",
        f"village-join-{village.id}-{admin.family_id}",
        send_push=False,
    )
    # The joining admin's own co-parents see it too (inbox-only).
    inbox.record_all(
        db, inbox.other_adults(db, admin), "village",
        f"{admin.display_name.split()[0]} joined {village.name}",
    )
    return _village_out(db, village, admin.family_id)


@router.post("/{village_id}/invite", response_model=VillageInviteOut)
def regenerate_invite(
    village_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Mint a fresh invite code (killing any previous one). Codes can never be
    re-shown — losing one costs a regenerate, never a lookup."""
    village = _member_village(db, village_id, admin.family_id)
    code = mint_code()
    village.invite_code_hash = hash_code(code)
    village.invite_expires_at = _utcnow() + INVITE_TTL
    db.commit()
    return VillageInviteOut(
        invite_code=pretty(code), invite_expires_at=village.invite_expires_at
    )


@router.patch("/{village_id}", status_code=status.HTTP_204_NO_CONTENT)
def rename_village(
    village_id: int,
    data: VillageIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Rename a village. Install-wide plumbing, so it's a SERVER-admin power
    only — a family admin who isn't the server owner gets nothing new here
    (403), matching the overview gate. Any village on the install, member or
    not."""
    if not admin.is_owner:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Server admin only")
    village = db.get(Village, village_id)
    if village is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such village")
    new_name = data.name.strip()
    if not new_name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Give the village a name")
    old_name = village.name
    if new_name != old_name:
        village.name = new_name
        db.commit()
        # The member families hear their circle was renamed (inbox-only; a
        # rename is news, not an interruption). The actor's own family is
        # excluded — a server admin outside the village excludes nobody.
        _notify_village(
            db,
            _village_adults(db, village.id, exclude_family=admin.family_id),
            "village",
            f"Village renamed to {new_name}",
            f"{old_name} is now {new_name}",
            f"village-renamed-{village.id}",
            send_push=False,
        )
    # No body: a full village payload would hand a non-member admin the
    # members' presence data that GET /villages reserves for members.


@router.delete("/{village_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_village(
    village_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """The founding family dissolves the village for everyone — the answer
    to stale villages nobody tends. Other families may only leave. The server
    admin may dissolve any village on the install, member or not."""
    if admin.is_owner:
        village = db.get(Village, village_id)
        if village is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such village")
    else:
        village = _member_village(db, village_id, admin.family_id)
        if village.created_by_family_id != admin.family_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Only the founding family can delete the village"
            )
    # Shared events die with the village; the going families' board copies
    # must go EXPLICITLY (SQLite tests run without the use_alter FK), and
    # their adults hear why. Collect before anything disappears.
    event_ids = list(
        db.scalars(select(VillageEvent.id).where(VillageEvent.village_id == village.id))
    )
    recipients = [
        u for u in village_events.going_adults(db, event_ids)
        if u.family_id != admin.family_id
    ]
    village_events.delete_copies(db, event_ids)
    db.delete(village)  # memberships, shelf rows, and event rows cascade away
    db.commit()
    _notify_village(
        db, recipients, "village", f"{village.name} was closed",
        "Its shared events came off your board", f"village-gone-{village_id}",
    )


@router.delete("/{village_id}/membership", status_code=status.HTTP_204_NO_CONTENT)
def leave_village(
    village_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Leave: the family's shelf entries in this village go with it (saved
    copies in other kitchens are independent rows and survive). The last
    family out turns off the lights — the village row is deleted."""
    village = _member_village(db, village_id, admin.family_id)
    # Hosted events go with the leaving family (their going guests hear why);
    # the family's own RSVPs and board copies of OTHERS' events go too.
    hosted_ids = list(
        db.scalars(
            select(VillageEvent.id).where(
                VillageEvent.village_id == village.id,
                VillageEvent.family_id == admin.family_id,
            )
        )
    )
    recipients = [
        u for u in village_events.going_adults(db, hosted_ids)
        if u.family_id != admin.family_id
    ]
    hosted_titles = ", ".join(
        db.scalars(
            select(Item.title)
            .join(VillageEvent, VillageEvent.item_id == Item.id)
            .where(VillageEvent.id.in_(hosted_ids))
        )
    ) if hosted_ids else ""
    village_events.delete_copies(db, hosted_ids)
    for event in db.scalars(
        select(VillageEvent).where(VillageEvent.id.in_(hosted_ids))
    ):
        db.delete(event)
    all_event_ids = list(
        db.scalars(select(VillageEvent.id).where(VillageEvent.village_id == village.id))
    )
    if all_event_ids:
        db.execute(
            delete(VillageEventRsvp).where(
                VillageEventRsvp.event_id.in_(all_event_ids),
                VillageEventRsvp.family_id == admin.family_id,
            )
        )
        for copy in db.scalars(
            select(Item).where(
                Item.village_event_id.in_(all_event_ids),
                Item.family_id == admin.family_id,
            )
        ):
            db.delete(copy)
    db.execute(
        delete(VillageRecipe).where(
            VillageRecipe.village_id == village.id,
            VillageRecipe.family_id == admin.family_id,
        )
    )
    db.execute(
        delete(VillageFood).where(
            VillageFood.village_id == village.id,
            VillageFood.family_id == admin.family_id,
        )
    )
    db.execute(
        delete(VillageFamily).where(
            VillageFamily.village_id == village.id,
            VillageFamily.family_id == admin.family_id,
        )
    )
    village_name = village.name  # survives the last-family-out delete below
    remaining = db.scalar(
        select(func.count())
        .select_from(VillageFamily)
        .where(VillageFamily.village_id == village.id)
    )
    if remaining == 0:
        db.delete(village)
    db.commit()
    if recipients:
        _notify_village(
            db, recipients, "village", f"Called off: {hosted_titles}",
            "The organizer's family left the village", f"village-left-{village_id}",
        )
    # The leaving admin's own co-parents see it too (inbox-only).
    inbox.record_all(
        db, inbox.other_adults(db, admin), "village",
        f"{admin.display_name.split()[0]} left {village_name}",
    )


# ---- the recipe shelf ---------------------------------------------------------------
# What a village actually shares. A shelf entry is a POINTER at the owning
# family's recipe (their edits show live on the shelf); "Save a copy" is what
# puts an independent snapshot in another family's kitchen — unsharing,
# leaving, or deleting never reaches into anyone else's recipe box.


def _my_village_ids(db: Session, family_id: int):
    return select(VillageFamily.village_id).where(VillageFamily.family_id == family_id)


def _shelf_row(
    db: Session,
    share: VillageRecipe,
    recipe: Recipe,
    village_name: str,
    family_name: str,
    viewer_family: int,
) -> SharedRecipeOut:
    from app.routers.recipes import per_serving_macros

    sharer = db.get(User, share.shared_by_id) if share.shared_by_id else None
    return SharedRecipeOut(
        share_id=share.id,
        village_id=share.village_id,
        village_name=village_name,
        family_id=share.family_id,
        family_name=family_name,
        shared_by=sharer.display_name.split()[0] if sharer else None,
        is_own=share.family_id == viewer_family,
        name=recipe.name,
        servings=recipe.servings,
        per_serving=per_serving_macros(recipe),
        created_at=share.created_at,
        updated_at=recipe.updated_at,
    )


def _get_share(db: Session, share_id: int, viewer_family: int) -> VillageRecipe:
    """A shelf entry in one of the viewer's villages; anything else 404s."""
    share = db.get(VillageRecipe, share_id)
    if share is None or share.village_id not in set(
        db.scalars(_my_village_ids(db, viewer_family))
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such shared recipe")
    return share


@router.get("/shelf", response_model=list[SharedRecipeOut])
def shelf(db: Session = Depends(get_db), user: User = Depends(require_family)):
    rows = db.execute(
        select(VillageRecipe, Recipe, Village.name, Family.name)
        .join(Recipe, Recipe.id == VillageRecipe.recipe_id)
        .join(Village, Village.id == VillageRecipe.village_id)
        .join(Family, Family.id == VillageRecipe.family_id)
        .where(VillageRecipe.village_id.in_(_my_village_ids(db, user.family_id)))
        .order_by(VillageRecipe.created_at.desc(), VillageRecipe.id.desc())
    ).all()
    return [
        _shelf_row(db, share, recipe, vname, fname, user.family_id)
        for share, recipe, vname, fname in rows
    ]


@router.get("/shelf/{share_id}", response_model=SharedRecipeDetailOut)
def shared_recipe_detail(
    share_id: int, db: Session = Depends(get_db), user: User = Depends(require_family)
):
    share = _get_share(db, share_id, user.family_id)
    recipe = db.get(Recipe, share.recipe_id)
    village = db.get(Village, share.village_id)
    family = db.get(Family, share.family_id)
    base = _shelf_row(db, share, recipe, village.name, family.name, user.family_id)
    lines = [
        SharedIngredientOut(
            name=ing.food.name,
            brand=ing.food.brand,
            amount=ing.amount,
            unit=ing.unit,
            grams=round(ing.grams, 2),
            **{
                n: (
                    round(getattr(ing.food, n) * ing.grams / 100.0, 1)
                    if getattr(ing.food, n) is not None
                    else None
                )
                for n in FOOD_NUTRIENTS
            },
        )
        for ing in recipe.ingredients
    ]
    return SharedRecipeDetailOut(
        **base.model_dump(), steps=recipe.steps, ingredients=lines
    )


@router.post(
    "/{village_id}/recipes",
    response_model=SharedRecipeOut,
    status_code=status.HTTP_201_CREATED,
)
def share_recipe(
    village_id: int,
    data: ShareRecipeIn,
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    """Put one of the family's own recipes on the village shelf."""
    from app.routers.recipes import _get_recipe

    village = _member_village(db, village_id, parent.family_id)
    recipe = _get_recipe(db, data.recipe_id, parent.family_id)
    if db.scalar(
        select(VillageRecipe).where(
            VillageRecipe.village_id == village.id, VillageRecipe.recipe_id == recipe.id
        )
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Already on the shelf")
    share = VillageRecipe(
        village_id=village.id,
        recipe_id=recipe.id,
        family_id=parent.family_id,
        shared_by_id=parent.id,
    )
    db.add(share)
    db.commit()
    db.refresh(share)
    family = db.get(Family, parent.family_id)
    first = parent.display_name.split()[0]
    # The village's other families hear about the new shelf entry (inbox-only;
    # a shelf entry is browsable news, not an interruption).
    _notify_village(
        db,
        _village_adults(db, village.id, exclude_family=parent.family_id),
        "village",
        f"{first} shared a recipe: {recipe.name}",
        f"On {village.name}'s shelf",
        f"village-recipe-{share.id}",
        send_push=False,
    )
    # And the acting family's OTHER adults see it in their own history too.
    inbox.record_all(
        db, inbox.other_adults(db, parent), "village",
        f"{first} shared to {village.name}: {recipe.name}",
    )
    return _shelf_row(db, share, recipe, village.name, family.name, parent.family_id)


@router.delete("/shelf/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
def unshare_recipe(
    share_id: int, db: Session = Depends(get_db), parent: User = Depends(require_parent)
):
    """Take an own-family entry off the shelf. Copies others saved survive.
    The village hears nothing; the co-parent sees the retraction in history."""
    share = _get_share(db, share_id, parent.family_id)
    if share.family_id != parent.family_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such shared recipe")
    name = db.scalar(select(Recipe.name).where(Recipe.id == share.recipe_id)) or ""
    db.delete(share)
    db.commit()
    inbox.record_all(
        db, inbox.other_adults(db, parent), "village",
        f"{parent.display_name.split()[0]} took off the shelf: {name}",
    )


def _matching_custom_food(db: Session, family_id: int, src: Food) -> Food | None:
    """An existing custom food of the destination family that is the same
    thing: same name/brand/base unit AND all ten nutrients equal. Name alone
    could silently swap in different nutrition; this keeps repeated copies
    idempotent without ever lying."""
    from sqlalchemy import func

    candidates = db.scalars(
        select(Food).where(
            Food.family_id == family_id,
            func.lower(Food.name) == src.name.lower(),
            func.lower(Food.brand) == src.brand.lower(),
            Food.base_unit == src.base_unit,
        )
    )
    for cand in candidates:
        if all(getattr(cand, n) == getattr(src, n) for n in FOOD_NUTRIENTS):
            return cand
    return None


@router.post(
    "/shelf/{share_id}/copy", response_model=RecipeOut, status_code=status.HTTP_201_CREATED
)
def save_a_copy(
    share_id: int, db: Session = Depends(get_db), parent: User = Depends(require_parent)
):
    """Adopt a shared recipe: an independent snapshot in the family's own
    kitchen. Shared-cache foods are reused as-is; the sharing family's custom
    foods are copied in (servings and all), deduped against existing ones."""
    from sqlalchemy import func

    from app.routers.recipes import _serialize

    share = _get_share(db, share_id, parent.family_id)
    if share.family_id == parent.family_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "It's already your recipe, no copy needed",
        )
    src = db.get(Recipe, share.recipe_id)

    # Copying must never fail on a name collision: suffix until free.
    name = src.name
    n = 2
    while db.scalar(
        select(Recipe).where(
            Recipe.family_id == parent.family_id, func.lower(Recipe.name) == name.lower()
        )
    ):
        suffix = f" ({n})"
        name = src.name[: 120 - len(suffix)] + suffix
        n += 1

    sharer = db.get(User, share.shared_by_id) if share.shared_by_id else None
    src_family = db.get(Family, share.family_id)
    stamp = dt.datetime.now().strftime("%b %-d, %-I:%M %p")
    provenance = (
        f"Copy of {src.name} shared by "
        f"{sharer.display_name.split()[0] if sharer else src_family.name} "
        f"from {src_family.name} on {stamp}"
    )[:200]
    copy = Recipe(
        family_id=parent.family_id,
        name=name,
        servings=src.servings,
        steps=src.steps,
        provenance=provenance,
    )
    db.add(copy)
    db.flush()

    for ing in src.ingredients:
        food = ing.food
        if food.family_id is not None:  # the sharer's custom food: bring it over
            existing = _matching_custom_food(db, parent.family_id, food)
            if existing is None:
                existing = Food(
                    family_id=parent.family_id,
                    source=FoodSource.custom,
                    source_id=None,
                    name=food.name,
                    brand=food.brand,
                    folder=food.folder,
                    base_unit=food.base_unit,
                    **{n_: getattr(food, n_) for n_ in FOOD_NUTRIENTS},
                )
                db.add(existing)
                db.flush()
                for serving in food.servings:
                    db.add(
                        FoodServing(
                            food_id=existing.id,
                            name=serving.name,
                            grams=serving.grams,
                            position=serving.position,
                        )
                    )
            food = existing
        db.add(
            RecipeIngredient(
                recipe_id=copy.id,
                food_id=food.id,
                position=ing.position,
                amount=ing.amount,
                unit=ing.unit,
            )
        )
    db.commit()
    db.refresh(copy)
    # The payoff for the sharer: their family's parents hear when another
    # family adopts their recipe. Inbox-only — a quiet thank-you, not a push.
    copier_family = db.get(Family, parent.family_id)
    sharer_parents = list(
        db.scalars(
            select(User).where(
                User.family_id == share.family_id, User.role == Role.parent
            )
        )
    )
    inbox.record_all(
        db, sharer_parents, "recipe",
        f"{copier_family.name} saved your recipe: {src.name}",
    )
    return _serialize(copy)


# ---- the food shelf ------------------------------------------------------------------
# Custom foods shared to a village, the recipe-shelf pattern exactly. A shelf
# entry POINTS at the owning family's custom food (their edits show live);
# "Save a copy" is what puts an independent snapshot in another family's
# kitchen. The path prefix is /food-shelf, not /shelf/foods: GET /shelf/
# {share_id} registers first and would int-parse-eat a /shelf/foods segment.
# folder never crosses the wall — it's the owning family's private filing.


def _food_shelf_row(
    db: Session,
    share: VillageFood,
    food: Food,
    village_name: str,
    family_name: str,
    viewer_family: int,
) -> SharedFoodOut:
    sharer = db.get(User, share.shared_by_id) if share.shared_by_id else None
    return SharedFoodOut(
        share_id=share.id,
        village_id=share.village_id,
        village_name=village_name,
        family_id=share.family_id,
        family_name=family_name,
        shared_by=sharer.display_name.split()[0] if sharer else None,
        is_own=share.family_id == viewer_family,
        name=food.name,
        brand=food.brand,
        base_unit=food.base_unit,
        serving=food.servings[0].name if food.servings else "",
        created_at=share.created_at,
        **{n: getattr(food, n) for n in FOOD_NUTRIENTS},
    )


def _get_food_share(db: Session, share_id: int, viewer_family: int) -> VillageFood:
    """A food-shelf entry in one of the viewer's villages; anything else 404s."""
    share = db.get(VillageFood, share_id)
    if share is None or share.village_id not in set(
        db.scalars(_my_village_ids(db, viewer_family))
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such shared food")
    return share


@router.get("/food-shelf", response_model=list[SharedFoodOut])
def food_shelf(db: Session = Depends(get_db), user: User = Depends(require_family)):
    rows = db.execute(
        select(VillageFood, Food, Village.name, Family.name)
        .join(Food, Food.id == VillageFood.food_id)
        .join(Village, Village.id == VillageFood.village_id)
        .join(Family, Family.id == VillageFood.family_id)
        .where(VillageFood.village_id.in_(_my_village_ids(db, user.family_id)))
        .order_by(VillageFood.created_at.desc(), VillageFood.id.desc())
    ).all()
    return [
        _food_shelf_row(db, share, food, vname, fname, user.family_id)
        for share, food, vname, fname in rows
    ]


@router.get("/food-shelf/{share_id}", response_model=SharedFoodDetailOut)
def shared_food_detail(
    share_id: int, db: Session = Depends(get_db), user: User = Depends(require_family)
):
    share = _get_food_share(db, share_id, user.family_id)
    food = db.get(Food, share.food_id)
    village = db.get(Village, share.village_id)
    family = db.get(Family, share.family_id)
    base = _food_shelf_row(db, share, food, village.name, family.name, user.family_id)
    return SharedFoodDetailOut(
        **base.model_dump(),
        servings=[FoodServingOut.model_validate(s) for s in food.servings],
    )


@router.post(
    "/{village_id}/foods",
    response_model=SharedFoodOut,
    status_code=status.HTTP_201_CREATED,
)
def share_food(
    village_id: int,
    data: ShareFoodIn,
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    """Put one of the family's own custom foods on the village shelf."""
    from app.routers.foods import _own_custom_food

    village = _member_village(db, village_id, parent.family_id)
    food = _own_custom_food(db, data.food_id, parent)
    if db.scalar(
        select(VillageFood).where(
            VillageFood.village_id == village.id, VillageFood.food_id == food.id
        )
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Already on the shelf")
    share = VillageFood(
        village_id=village.id,
        food_id=food.id,
        family_id=parent.family_id,
        shared_by_id=parent.id,
    )
    db.add(share)
    db.commit()
    db.refresh(share)
    family = db.get(Family, parent.family_id)
    first = parent.display_name.split()[0]
    # The village's other families hear about the new shelf entry (inbox-only;
    # a shelf entry is browsable news, not an interruption).
    _notify_village(
        db,
        _village_adults(db, village.id, exclude_family=parent.family_id),
        "village",
        f"{first} shared a food: {food.name}",
        f"On {village.name}'s shelf",
        f"village-food-{share.id}",
        send_push=False,
    )
    # And the acting family's OTHER adults see it in their own history too.
    inbox.record_all(
        db, inbox.other_adults(db, parent), "village",
        f"{first} shared to {village.name}: {food.name}",
    )
    return _food_shelf_row(db, share, food, village.name, family.name, parent.family_id)


@router.delete("/food-shelf/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
def unshare_food(
    share_id: int, db: Session = Depends(get_db), parent: User = Depends(require_parent)
):
    """Take an own-family entry off the food shelf. Copies others saved survive.
    The village hears nothing; the co-parent sees the retraction in history."""
    share = _get_food_share(db, share_id, parent.family_id)
    if share.family_id != parent.family_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such shared food")
    name = db.scalar(select(Food.name).where(Food.id == share.food_id)) or ""
    db.delete(share)
    db.commit()
    inbox.record_all(
        db, inbox.other_adults(db, parent), "village",
        f"{parent.display_name.split()[0]} took off the shelf: {name}",
    )


@router.post(
    "/food-shelf/{share_id}/copy",
    response_model=FoodOut,
    status_code=status.HTTP_201_CREATED,
)
def save_a_food_copy(
    share_id: int, db: Session = Depends(get_db), parent: User = Depends(require_parent)
):
    """Adopt a shared custom food: an independent snapshot in the family's own
    kitchen (servings and all), deduped against existing customs. source_id is
    dropped (the sharer's barcode never crosses); the sharer's folder rides
    along only as the copier's own filing, and dedup ignores it so a match
    keeps the copier's existing filing."""
    share = _get_food_share(db, share_id, parent.family_id)
    if share.family_id == parent.family_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "It's already your food, no copy needed",
        )
    src = db.get(Food, share.food_id)
    existing = _matching_custom_food(db, parent.family_id, src)
    if existing is not None:
        # A repeat copy: the family already has this food. Idempotent, no line.
        return existing
    copy = Food(
        family_id=parent.family_id,
        source=FoodSource.custom,
        source_id=None,
        name=src.name,
        brand=src.brand,
        folder=src.folder,
        base_unit=src.base_unit,
        **{n: getattr(src, n) for n in FOOD_NUTRIENTS},
    )
    db.add(copy)
    db.flush()
    for serving in src.servings:
        db.add(
            FoodServing(
                food_id=copy.id,
                name=serving.name,
                grams=serving.grams,
                position=serving.position,
            )
        )
    db.commit()
    db.refresh(copy)
    # The payoff for the sharer: their family's parents hear when another family
    # adopts their food. Inbox-only — a quiet thank-you, not a push.
    copier_family = db.get(Family, parent.family_id)
    sharer_parents = list(
        db.scalars(
            select(User).where(
                User.family_id == share.family_id, User.role == Role.parent
            )
        )
    )
    inbox.record_all(
        db, sharer_parents, "recipe",
        f"{copier_family.name} saved your food: {src.name}",
    )
    return copy


# ---- village events -------------------------------------------------------------
# An activity or appointment offered to the village. The event row is a
# pointer at the organizer's own card; a family that answers "going" gets an
# independent copy on its board (app/village_events.py). Every read goes
# through the same membership gate as the shelf — an outsider 404s.


def _notify_village(
    db: Session,
    users: list[User],
    kind: str,
    title: str,
    body: str | dict[int, str],
    tag: str,
    send_push: bool = True,
) -> None:
    """Inbox lines first (always), committed on their own, then the push leg
    gated per-user by the "village" pref. The _push_board_change shape. A dict
    body carries per-family text (each family's own wall clock); a str is the
    same for all.

    send_push=False makes the line inbox-only. The phone buzzes ONLY for
    event invitations and changes to events the family RSVP'd going to. Joins,
    shelf shares, and RSVP replies are history, not interruptions."""
    if not users:
        return

    def _body(u) -> str:
        return body if isinstance(body, str) else body.get(u.family_id, "")

    try:
        for u in users:
            inbox.record(db, u.id, u.family_id, kind, title, _body(u))
        db.commit()
    except Exception:
        db.rollback()
        log.exception("village inbox write failed (the change itself is saved)")
    if not send_push or not push.enabled():
        return
    try:
        for u in users:
            if push.wants(u, "village"):
                payload = {"title": title, "body": _body(u), "tag": tag, "url": "/"}
                push.send_to_user(db, u.id, payload)
    except Exception:
        log.exception("village push failed (the change itself is saved)")


def _village_adults(db: Session, village_id: int, exclude_family: int | None = None) -> list[User]:
    """Parents across the village's member families (adults == parents; kid
    mode follows the role)."""
    q = (
        select(User)
        .join(VillageFamily, VillageFamily.family_id == User.family_id)
        .where(VillageFamily.village_id == village_id, User.role == Role.parent)
    )
    if exclude_family is not None:
        q = q.where(User.family_id != exclude_family)
    return list(db.scalars(q))


def _get_event(db: Session, event_id: int, viewer_family: int) -> VillageEvent:
    """An event in one of the viewer's villages; anything else 404s."""
    event = db.get(VillageEvent, event_id)
    if event is None or event.village_id not in set(
        db.scalars(_my_village_ids(db, viewer_family))
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such event")
    return event


def _attendee_out(member: User, viewer_family: int, kids_shared: bool) -> AttendeeOut:
    """How one attendee crosses the wall. Parents go whole (name + face); a
    kid goes as a bare initial unless their FAMILY opted its kids in
    (share_kid_avatars — one switch covers every kid). The viewer's own
    family always sees its own members in full — the picker needs real
    faces."""
    first = member.display_name.split()[0]
    own = member.family_id == viewer_family
    if member.role == Role.parent or own or kids_shared:
        return AttendeeOut(
            user_id=member.id,
            name=member.display_name if (member.role == Role.parent or own) else first,
            initial=first[:1].upper(),
            is_minor=member.is_minor,
            avatar=True,
            avatar_updated_at=member.avatar_updated_at,
        )
    return AttendeeOut(
        user_id=None, name=None, initial=first[:1].upper(), is_minor=True, avatar=False
    )


def _events_out(
    db: Session, viewer: User, only_event_ids: list[int] | None = None
) -> list[VillageEventOut]:
    """Every upcoming event across the viewer's villages (or just the given
    ids), schedule on the viewer family's clock, attendee lists shaped by
    each kid's privacy flag. A fixed handful of queries however many events."""
    viewer_family = db.get(Family, viewer.family_id)
    q = (
        select(VillageEvent, Item, Village.name, Family)
        .join(Item, VillageEvent.item_id == Item.id)
        .join(Village, VillageEvent.village_id == Village.id)
        .join(Family, VillageEvent.family_id == Family.id)
        .where(VillageEvent.village_id.in_(_my_village_ids(db, viewer.family_id)))
    )
    if only_event_ids is not None:
        q = q.where(VillageEvent.id.in_(only_event_ids))
    else:
        # Don't drag the whole event history through the joins forever: a
        # shifted schedule moves at most one calendar day, so a one-day slack
        # in SQL keeps the exact viewer-local cutoff below the only filter
        # that matters.
        q = q.where(Item.date_for >= dt.date.today() - dt.timedelta(days=1))
    rows = db.execute(q).all()
    if not rows:
        return []
    event_ids = [e.id for e, _, _, _ in rows]
    item_ids = [i.id for _, i, _, _ in rows]

    rsvp_rows = db.execute(
        select(VillageEventRsvp, Family.name)
        .join(Family, VillageEventRsvp.family_id == Family.id)
        .where(VillageEventRsvp.event_id.in_(event_ids))
    ).all()
    rsvp_ids = [r.id for r, _ in rsvp_rows]
    attendee_rows = (
        db.execute(
            select(VillageEventAttendee.rsvp_id, User)
            .join(User, VillageEventAttendee.user_id == User.id)
            .where(VillageEventAttendee.rsvp_id.in_(rsvp_ids))
        ).all()
        if rsvp_ids
        else []
    )
    attendees_by_rsvp: dict[int, list[User]] = {}
    for rsvp_id, member in attendee_rows:
        attendees_by_rsvp.setdefault(rsvp_id, []).append(member)
    # Which attendee families share their kids' faces (one query, one switch
    # per family covering every kid).
    attendee_family_ids = {m.family_id for _, m in attendee_rows if m.family_id}
    kids_shared_by_family = (
        {
            fid: shared
            for fid, shared in db.execute(
                select(Family.id, Family.share_kid_avatars).where(
                    Family.id.in_(attendee_family_ids)
                )
            )
        }
        if attendee_family_ids
        else {}
    )

    my_copy_by_event = {
        ve_id: item_id
        for ve_id, item_id in db.execute(
            select(Item.village_event_id, Item.id).where(
                Item.village_event_id.in_(event_ids),
                Item.family_id == viewer.family_id,
            )
        )
    }
    cancelled_items = set(
        db.scalars(
            select(Completion.item_id).where(
                Completion.item_id.in_(item_ids), Completion.cancelled.is_(True)
            )
        )
    )
    name_ids = {e.shared_by_id for e, _, _, _ in rows if e.shared_by_id} | {
        r.set_by_id for r, _ in rsvp_rows if r.set_by_id
    }
    first_names = (
        {
            u.id: u.display_name.split()[0]
            for u in db.scalars(select(User).where(User.id.in_(name_ids)))
        }
        if name_ids
        else {}
    )

    out: list[VillageEventOut] = []
    today_here = family_now(dt.datetime.now(), viewer_family.timezone).date()
    for event, item, village_name, organizer_family in rows:
        date_for, start, end = shift_schedule(
            item.date_for,
            item.time_of_day,
            item.end_time,
            item.all_day,
            organizer_family.timezone,
            viewer_family.timezone,
        )
        if only_event_ids is None and date_for < today_here:
            continue
        rsvps = []
        my_rsvp = None
        for rsvp, family_name in rsvp_rows:
            if rsvp.event_id != event.id:
                continue
            if rsvp.family_id == viewer.family_id:
                my_rsvp = rsvp.status
            rsvps.append(
                VillageEventRsvpOut(
                    family_id=rsvp.family_id,
                    family_name=family_name,
                    status=rsvp.status,
                    set_by=first_names.get(rsvp.set_by_id),
                    attendees=[
                        _attendee_out(
                            m,
                            viewer.family_id,
                            kids_shared_by_family.get(m.family_id, False),
                        )
                        for m in attendees_by_rsvp.get(rsvp.id, [])
                    ],
                )
            )
        out.append(
            VillageEventOut(
                event_id=event.id,
                village_id=event.village_id,
                village_name=village_name,
                item_id=item.id,
                my_item_id=my_copy_by_event.get(event.id),
                is_own=event.family_id == viewer.family_id,
                organizer_family_id=event.family_id,
                organizer_family_name=organizer_family.name,
                shared_by=first_names.get(event.shared_by_id),
                kind=item.kind,
                title=item.title,
                notes=item.notes,
                location=item.location,
                date_for=date_for,
                time_of_day=start,
                end_time=end,
                all_day=item.all_day,
                cancelled=item.id in cancelled_items,
                my_rsvp=my_rsvp,
                rsvps=rsvps,
                created_at=event.created_at,
            )
        )
    out.sort(key=lambda e: (e.date_for, e.time_of_day is not None, e.time_of_day or dt.time.min, e.title))
    return out


@router.get("/events", response_model=list[VillageEventOut])
def list_events(db: Session = Depends(get_db), user: User = Depends(require_adult)):
    """Upcoming shared events across the member's villages. Adults only, the
    roster rule: the RSVP lists carry other households' names."""
    return _events_out(db, user)


@router.post("/{village_id}/events", response_model=VillageEventOut, status_code=status.HTTP_201_CREATED)
def share_event(
    village_id: int,
    data: ShareEventIn,
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    """Offer one of the family's own dated activities/appointments to a
    village. The card itself stays the family's; the event row is a pointer."""
    village = _member_village(db, village_id, parent.family_id)
    item = db.scalar(
        select(Item).where(Item.id == data.item_id, Item.family_id == parent.family_id)
    )
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such card")
    # The same wall every item route has: another member's private card can't
    # be published to a village by someone who can't even open it.
    from app.routers.items import _require_visible

    _require_visible(item, parent)
    if item.kind not in (ItemKind.activity, ItemKind.appointment):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Only activities and appointments can be shared"
        )
    if item.village_event_id is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That card came from a village event")
    if item.date_for is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Give it a date first")
    if item.repeat_type is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Repeating cards can't be shared")
    if db.scalar(
        select(VillageEvent).where(
            VillageEvent.village_id == village.id, VillageEvent.item_id == item.id
        )
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Already shared with this village")

    event = VillageEvent(
        village_id=village.id,
        item_id=item.id,
        family_id=parent.family_id,
        shared_by_id=parent.id,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    from app.routers.items import _event_notify_bodies

    recipients = _village_adults(db, village.id, exclude_family=parent.family_id)
    first = parent.display_name.split()[0]
    # Invitations are one of the two things that still PUSH.
    _notify_village(
        db,
        recipients,
        "invite",
        f"{first} invited you: {item.title}",
        _event_notify_bodies(db, item, recipients),
        f"village-invite-{event.id}",
    )
    # The acting family's OTHER adults get an inbox-only line, never a push.
    inbox.record_all(
        db, inbox.other_adults(db, parent), "village",
        f"{first} shared to {village.name}: {item.title}",
    )
    return _events_out(db, parent, [event.id])[0]


@router.put("/events/{event_id}/rsvp", response_model=VillageEventOut)
def set_rsvp(
    event_id: int,
    data: RsvpIn,
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    """The family's answer, set or changed by either parent. Going names who
    is coming and lands the event on the family board; leaving going takes
    it back off."""
    event = _get_event(db, event_id, parent.family_id)
    if event.family_id == parent.family_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You're hosting this one")

    members = {
        u.id: u for u in db.scalars(select(User).where(User.family_id == parent.family_id))
    }
    attendee_ids = list(dict.fromkeys(data.attendee_ids))
    if any(uid not in members for uid in attendee_ids):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Attendees must be your own family")
    if data.status == RsvpStatus.going and not attendee_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Pick who's going")

    rsvp = db.scalar(
        select(VillageEventRsvp).where(
            VillageEventRsvp.event_id == event.id,
            VillageEventRsvp.family_id == parent.family_id,
        )
    )
    # Identical re-save (same status AND same attendee set) changes nothing
    # and records nothing — the dinner-vote convention (27d2e83). Attendee
    # rows only exist for going, so a non-going answer compares against the
    # empty set.
    if rsvp is not None and rsvp.status == data.status:
        stored = set(
            db.scalars(
                select(VillageEventAttendee.user_id).where(
                    VillageEventAttendee.rsvp_id == rsvp.id
                )
            )
        )
        effective = set(attendee_ids) if data.status == RsvpStatus.going else set()
        if stored == effective:
            return _events_out(db, parent, [event.id])[0]
    was_going = rsvp is not None and rsvp.status == RsvpStatus.going
    if rsvp is None:
        rsvp = VillageEventRsvp(
            event_id=event.id,
            family_id=parent.family_id,
            status=data.status,
            set_by_id=parent.id,
        )
        db.add(rsvp)
    else:
        rsvp.status = data.status
        rsvp.set_by_id = parent.id
        rsvp.updated_at = dt.datetime.now(dt.timezone.utc)
    db.flush()  # the attendee rows need rsvp.id
    db.execute(
        delete(VillageEventAttendee).where(VillageEventAttendee.rsvp_id == rsvp.id)
    )
    if data.status == RsvpStatus.going:
        for uid in attendee_ids:
            db.add(VillageEventAttendee(rsvp_id=rsvp.id, user_id=uid))

    src = db.get(Item, event.item_id)
    if data.status == RsvpStatus.going and not was_going:
        organizer_tz = db.scalar(select(Family.timezone).where(Family.id == event.family_id))
        village_events.materialize(
            db, event, src, organizer_tz, db.get(Family, parent.family_id), parent
        )
    elif was_going and data.status != RsvpStatus.going:
        village_events.delete_copies_for_family(db, event.id, parent.family_id)
    db.commit()

    labels = {RsvpStatus.going: "Going", RsvpStatus.maybe: "Maybe", RsvpStatus.cant: "Can't make it"}
    label = labels[data.status]
    if data.status == RsvpStatus.going:
        label = f"Going · {len(attendee_ids)}"
    family_name = db.scalar(select(Family.name).where(Family.id == parent.family_id))
    # RSVP replies are history for the organizer, not an interruption:
    # inbox-only.
    _notify_village(
        db,
        [u for u in db.scalars(select(User).where(User.family_id == event.family_id, User.role == Role.parent))],
        "rsvp",
        f"{family_name}: {label}",
        src.title,
        f"village-rsvp-{event.id}-{parent.family_id}",
        send_push=False,
    )
    # The acting family's OTHER adults see the answer their co-parent gave.
    inbox.record_all(
        db, inbox.other_adults(db, parent), "rsvp",
        f"{parent.display_name.split()[0]} replied {label}: {src.title}",
    )
    return _events_out(db, parent, [event.id])[0]


@router.delete("/events/{event_id}/rsvp", status_code=status.HTTP_204_NO_CONTENT)
def clear_rsvp(
    event_id: int,
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    """Withdraw the family's answer entirely (back to un-answered)."""
    event = _get_event(db, event_id, parent.family_id)
    rsvp = db.scalar(
        select(VillageEventRsvp).where(
            VillageEventRsvp.event_id == event.id,
            VillageEventRsvp.family_id == parent.family_id,
        )
    )
    if rsvp is None:
        return
    was_going = rsvp.status == RsvpStatus.going
    db.delete(rsvp)  # attendee rows cascade
    if was_going:
        village_events.delete_copies_for_family(db, event.id, parent.family_id)
    db.commit()
    src = db.get(Item, event.item_id)
    family_name = db.scalar(select(Family.name).where(Family.id == parent.family_id))
    title = src.title if src else ""
    # Withdrawals are history too: inbox-only.
    _notify_village(
        db,
        [u for u in db.scalars(select(User).where(User.family_id == event.family_id, User.role == Role.parent))],
        "rsvp",
        f"{family_name} withdrew their RSVP",
        title,
        f"village-rsvp-{event.id}-{parent.family_id}",
        send_push=False,
    )
    # The acting family's OTHER adults see the withdrawal too.
    inbox.record_all(
        db, inbox.other_adults(db, parent), "rsvp",
        f"{parent.display_name.split()[0]} withdrew the RSVP: {title}",
    )


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def unshare_event(
    event_id: int,
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    """The organizer takes the event back off the village. Copies leave the
    going families' boards, with a note about why."""
    event = _get_event(db, event_id, parent.family_id)
    if event.family_id != parent.family_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such event")
    title = db.scalar(select(Item.title).where(Item.id == event.item_id)) or ""
    village_name = db.scalar(select(Village.name).where(Village.id == event.village_id)) or ""
    recipients = village_events.going_adults(db, [event.id])
    village_events.delete_copies(db, [event.id])
    db.delete(event)  # RSVPs and attendee rows cascade
    db.commit()
    _notify_village(
        db, recipients, "village", f"Called off: {title}",
        "The organizer took it off the village", f"village-off-{event_id}",
    )
    inbox.record_all(
        db, inbox.other_adults(db, parent), "village",
        f"{parent.display_name.split()[0]} unshared from {village_name}: {title}",
    )


@router.put("/kid-avatars", status_code=status.HTTP_204_NO_CONTENT)
def set_kid_avatars(
    data: KidAvatarIn,
    db: Session = Depends(get_db),
    parent: User = Depends(require_parent),
):
    """Parent-controlled, one switch for the whole household: show OUR KIDS'
    photos (and first names) to the family's villages — every kid, present
    and future. Off, the default, means other families only ever see a
    first-initial circle per kid."""
    family = db.get(Family, parent.family_id)
    family.share_kid_avatars = data.shared
    db.commit()
