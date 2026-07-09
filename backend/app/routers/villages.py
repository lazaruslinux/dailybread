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

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app import throttle
from app.invitecodes import hash_code, mint_code, normalize, pretty, still_valid
from app.db import get_db
from app.deps import require_admin, require_family
from app.models import Family, Role, User, Village, VillageFamily, VillageRecipe
from app.schemas import (
    VillageCheckOut,
    VillageCreatedOut,
    VillageFamilyOut,
    VillageIn,
    VillageInviteOut,
    VillageJoinIn,
    VillageOut,
    VillageParentOut,
)

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
    parents_by_family: dict[int, list[VillageParentOut]] = {}
    family_ids = [family.id for _, family in rows]
    if family_ids:
        for user in db.scalars(
            select(User)
            .where(User.family_id.in_(family_ids), User.role == Role.parent)
            .order_by(User.created_at, User.id)
        ):
            parents_by_family.setdefault(user.family_id, []).append(
                VillageParentOut(
                    id=user.id,
                    display_name=user.display_name,
                    avatar_updated_at=user.avatar_updated_at,
                )
            )
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
def list_villages(db: Session = Depends(get_db), user: User = Depends(require_family)):
    """The family's villages. Any member may look; only admins change them."""
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
    One village per family for now."""
    if _family_in_a_village(db, admin.family_id):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Your family is already in a village"
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
    # this caller, so these refusals can say what they are. The code stays
    # live either way.
    if _family_in_a_village(db, admin.family_id):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Your family is already in a village"
        )

    db.add(VillageFamily(village_id=village.id, family_id=admin.family_id))
    # Single-use: the join consumes the code.
    village.invite_code_hash = None
    village.invite_expires_at = None
    db.commit()
    throttle.clear(f"village-join:{admin.username}")
    db.refresh(village)
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


@router.delete("/{village_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_village(
    village_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """The founding family dissolves the village for everyone — the answer
    to stale villages nobody tends. Other families may only leave."""
    village = _member_village(db, village_id, admin.family_id)
    if village.created_by_family_id != admin.family_id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the founding family can delete the village"
        )
    db.delete(village)  # memberships and shelf rows cascade away
    db.commit()


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
    db.execute(
        delete(VillageRecipe).where(
            VillageRecipe.village_id == village.id,
            VillageRecipe.family_id == admin.family_id,
        )
    )
    db.execute(
        delete(VillageFamily).where(
            VillageFamily.village_id == village.id,
            VillageFamily.family_id == admin.family_id,
        )
    )
    remaining = db.scalar(
        select(func.count())
        .select_from(VillageFamily)
        .where(VillageFamily.village_id == village.id)
    )
    if remaining == 0:
        db.delete(village)
    db.commit()
