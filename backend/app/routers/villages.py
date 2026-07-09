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
from app.models import Family, User, Village, VillageFamily, VillageRecipe
from app.schemas import (
    VillageCreatedOut,
    VillageFamilyOut,
    VillageIn,
    VillageInviteOut,
    VillageJoinIn,
    VillageOut,
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


def _village_out(db: Session, village: Village) -> VillageOut:
    rows = db.execute(
        select(VillageFamily, Family)
        .join(Family, Family.id == VillageFamily.family_id)
        .where(VillageFamily.village_id == village.id)
        .order_by(VillageFamily.joined_at, VillageFamily.id)
    ).all()
    active = _invite_active(village, _utcnow())
    return VillageOut(
        id=village.id,
        name=village.name,
        created_at=village.created_at,
        families=[
            VillageFamilyOut(id=family.id, name=family.name, joined_at=vf.joined_at)
            for vf, family in rows
        ],
        invite_active=active,
        invite_expires_at=village.invite_expires_at if active else None,
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
    return [_village_out(db, v) for v in villages]


@router.post("", response_model=VillageCreatedOut, status_code=status.HTTP_201_CREATED)
def create_village(
    data: VillageIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Found a village: the creating family is its first member, and the
    response carries the invite code — the only time it is ever shown."""
    code = mint_code()
    village = Village(
        name=data.name.strip(),
        invite_code_hash=hash_code(code),
        invite_expires_at=_utcnow() + INVITE_TTL,
    )
    db.add(village)
    db.flush()
    db.add(VillageFamily(village_id=village.id, family_id=admin.family_id))
    db.commit()
    db.refresh(village)
    base = _village_out(db, village)
    return VillageCreatedOut(**base.model_dump(), invite_code=pretty(code))


@router.post("/join", response_model=VillageOut)
def join_village(
    data: VillageJoinIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Join with an invite code. Wrong, expired, and nonexistent codes are one
    indistinguishable 404; attempts are throttled like failed logins."""
    key = f"village-join:{admin.username}"
    if throttle.too_many_failures(key):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Try again later."
        )

    code = normalize(data.code)
    village = (
        db.scalar(select(Village).where(Village.invite_code_hash == hash_code(code)))
        if code
        else None
    )
    if village is None or not _invite_active(village, _utcnow()):
        throttle.record_failure(key)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That code isn't valid")

    already = db.scalar(
        select(VillageFamily).where(
            VillageFamily.village_id == village.id,
            VillageFamily.family_id == admin.family_id,
        )
    )
    # A valid code in hand means the village's existence isn't a secret from
    # this caller, so the duplicate case can say what it is. The code stays
    # live — it was minted for someone else.
    if already is not None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Your family is already in this village"
        )

    db.add(VillageFamily(village_id=village.id, family_id=admin.family_id))
    # Single-use: the join consumes the code.
    village.invite_code_hash = None
    village.invite_expires_at = None
    db.commit()
    throttle.clear(key)
    db.refresh(village)
    return _village_out(db, village)


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
