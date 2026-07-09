import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import get_current_user, require_admin
from app.invitecodes import hash_code, mint_code, normalize, pretty, still_valid
from app.models import Family, Role, SignupInvite, User
from app.schemas import (
    BootstrapIn,
    ChangePasswordIn,
    CreateUserIn,
    InviteCheckOut,
    InviteCodeIn,
    InviteRedeemIn,
    LoginIn,
    ResetPasswordOut,
    SetupOut,
    SignupInviteIn,
    SignupInviteOut,
    UpdateUserIn,
    UserOut,
)
from app.security import generate_password, hash_password, set_session_cookie, verify_password
from app import throttle

router = APIRouter(prefix="/auth", tags=["auth"])

# Signup invites are redeemable by ANONYMOUS visitors on the sign-in screen,
# so they live only 15 minutes (village codes, by contrast, need a signed-in
# admin and get 48h). All anonymous code attempts share ONE throttle bucket —
# per-code keys would throttle nothing, since every wrong guess is a fresh
# key — with a higher cap so a prankster can't cheaply starve a real invitee.
# Residual risk: a deliberate flood locks code entry for 15 minutes; on a
# family server that's acceptable, and the owner just re-mints afterward.
SIGNUP_INVITE_TTL = dt.timedelta(minutes=15)
SIGNUP_THROTTLE_KEY = "signup-invite"
SIGNUP_MAX_FAILURES = 30


@router.get("/setup", response_model=SetupOut)
def setup_state(db: Session = Depends(get_db)):
    """Is this install set up yet? Drives the first-run wizard vs. login."""
    user_count = db.scalar(select(func.count()).select_from(User))
    return SetupOut(initialized=bool(user_count))


@router.post("/bootstrap", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def bootstrap(data: BootstrapIn, response: Response, db: Session = Depends(get_db)):
    """Create the first family and its head. Allowed only while no users exist."""
    user_count = db.scalar(select(func.count()).select_from(User))
    if user_count:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Already initialized")

    family = Family(name=data.family_name.strip())
    db.add(family)
    db.flush()
    user = User(
        family_id=family.id,
        username=data.username,
        display_name=data.display_name,
        password_hash=hash_password(data.password),
        role=Role.parent,
        is_admin=True,  # admin of the first family
        is_owner=True,  # ...and the server admin for the whole install
        birthdate=data.birthdate,  # optional; prefills their Nutrition profile
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    set_session_cookie(response, str(user.id), user.token_version)
    return user


@router.post("/login", response_model=UserOut)
def login(data: LoginIn, response: Response, db: Session = Depends(get_db)):
    # Too many recent failures against this username and we stop checking
    # passwords at all until the window cools off (see app.throttle).
    key = data.username.lower()
    if throttle.too_many_failures(key):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many attempts. Wait a while and try again.",
        )
    user = db.scalar(select(User).where(User.username == data.username))
    # Same error whether the user is missing or the password is wrong, so an
    # attacker can't tell which usernames exist.
    if user is None or not verify_password(data.password, user.password_hash):
        throttle.record_failure(key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    throttle.clear(key)
    set_session_cookie(response, str(user.id), user.token_version)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    response.delete_cookie(settings.cookie_name, path="/")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    """Who am I? Used by the frontend to restore the session on page load."""
    return user


@router.post("/change-password", response_model=UserOut)
def change_password(
    data: ChangePasswordIn,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Change your own password (any member, any role). Also how an account an
    admin reset trades its generated hand-off password for one of its own."""
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")

    user.password_hash = hash_password(data.new_password)
    user.must_change_password = False
    # End the account's sessions everywhere else (see token_version on the
    # model), but re-issue this session's cookie so the change doesn't log out
    # the very phone that made it.
    user.token_version += 1
    set_session_cookie(response, str(user.id), user.token_version)
    db.commit()
    db.refresh(user)
    return user


# ---- signup invites --------------------------------------------------------------


def _live_invite(db: Session, raw: str) -> SignupInvite | None:
    code = normalize(raw)
    if not code:
        return None
    invite = db.scalar(select(SignupInvite).where(SignupInvite.code_hash == hash_code(code)))
    if invite is None or not still_valid(invite.expires_at, dt.datetime.now(dt.timezone.utc)):
        return None
    return invite


def _gate_anonymous_code_attempts() -> None:
    if throttle.too_many_failures(SIGNUP_THROTTLE_KEY, limit=SIGNUP_MAX_FAILURES):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Try again later."
        )


@router.post("/invites", response_model=SignupInviteOut, status_code=status.HTTP_201_CREATED)
def mint_signup_invite(
    data: SignupInviteIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Server-admin only: invite someone onto this dailybread. The response
    carries the code exactly once; the invitee redeems it on the sign-in
    screen, picks their own username and password, and founds their OWN
    family — invites never join an existing one."""
    if not admin.is_owner:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only the server admin can invite to dailybread"
        )

    now = dt.datetime.now(dt.timezone.utc)
    # Hygiene: expired invites are dead weight.
    db.execute(delete(SignupInvite).where(SignupInvite.expires_at < now))

    code = mint_code()
    invite = SignupInvite(
        code_hash=hash_code(code),
        display_name=data.display_name,
        invited_by_id=admin.id,
        expires_at=now + SIGNUP_INVITE_TTL,
    )
    db.add(invite)
    db.commit()
    return SignupInviteOut(
        code=pretty(code),
        display_name=invite.display_name,
        expires_at=invite.expires_at,
    )


@router.post("/invites/check", response_model=InviteCheckOut)
def check_signup_invite(data: InviteCodeIn, db: Session = Depends(get_db)):
    """Anonymous: does this code open a door? Drives the "Welcome, Bob" step
    without consuming the code. Wrong, expired, and never-existed codes are
    one indistinguishable 404."""
    _gate_anonymous_code_attempts()
    invite = _live_invite(db, data.code)
    if invite is None:
        throttle.record_failure(SIGNUP_THROTTLE_KEY)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That code isn't valid")
    return InviteCheckOut(display_name=invite.display_name)


@router.post("/invites/redeem", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def redeem_signup_invite(
    data: InviteRedeemIn, response: Response, db: Session = Depends(get_db)
):
    """Anonymous: trade a live invite code + a chosen username and password
    for a signed-in account. The account starts family-less; the
    create-your-family wizard takes it from there."""
    _gate_anonymous_code_attempts()
    invite = _live_invite(db, data.code)
    if invite is None:
        throttle.record_failure(SIGNUP_THROTTLE_KEY)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That code isn't valid")

    # The invitee picked this username themselves, so a collision is just a
    # normal form error: the invite stays live and they try another name.
    if db.scalar(select(User).where(User.username == data.username)):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "That username is taken. Try another."
        )

    user = User(
        family_id=None,  # the create-your-family wizard fills this in
        username=data.username,
        display_name=(data.display_name or invite.display_name).strip(),
        password_hash=hash_password(data.password),
        role=Role.parent,
        is_admin=False,
        is_owner=False,
        birthdate=data.birthdate,  # optional; prefills their Nutrition profile
    )
    db.add(user)
    db.delete(invite)  # single-use: the redemption consumes it
    try:
        db.commit()
    except IntegrityError:  # a truly concurrent taker of the same username
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "That username is taken. Try another."
        )
    db.refresh(user)
    set_session_cookie(response, str(user.id), user.token_version)
    return user


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    data: CreateUserIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Admin-only: create a member of your own family — or, with
    new_household, an account that will found its own family on first login."""
    if db.scalar(select(User).where(User.username == data.username)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already taken")

    if data.new_household:
        # Inviting a whole new household onto the install is a server-admin
        # power, not something every family's admin can do.
        if not admin.is_owner:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Only the server admin can invite another household",
            )
        if data.role != Role.parent:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "A new household's first account must be a parent"
            )

    # Default admin from role unless explicitly set. A child can never be admin.
    is_admin = data.is_admin if data.is_admin is not None else (data.role == Role.parent)
    if data.role == Role.child and is_admin:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A child account cannot be an admin")

    user = User(
        # New-household accounts start family-less; the wizard fills this in
        # and promotes them. Everyone else is born into the admin's family.
        family_id=None if data.new_household else admin.family_id,
        username=data.username,
        display_name=data.display_name,
        password_hash=hash_password(data.password),
        role=data.role,
        is_admin=False if data.new_household else is_admin,
        birthdate=data.birthdate,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Admin-only: everyone in YOUR family, for the dashboard."""
    return db.scalars(
        select(User).where(User.family_id == admin.family_id).order_by(User.created_at)
    ).all()


def _managed_user(db: Session, user_id: int, admin: User) -> User:
    """An account this admin may manage: their own family's members, plus
    family-less new-household accounts (someone must be able to reset a
    forgotten password before the wizard runs). Cross-family lookups 404 so
    other households' ids don't leak."""
    user = db.get(User, user_id)
    if user is None or (user.family_id is not None and user.family_id != admin.family_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such user")
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    data: UpdateUserIn,
    response: Response,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Admin-only: edit a family member (name, role, admin flag, password)."""
    user = _managed_user(db, user_id, admin)

    # Work out what the account would look like AFTER the edit, then validate
    # that final state. This catches bad combinations across fields.
    new_role = data.role if data.role is not None else user.role
    new_admin = data.is_admin if data.is_admin is not None else user.is_admin

    if new_role == Role.child and new_admin:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "A child account cannot be an admin. Remove admin access first.",
        )

    # Lockout protection: you cannot take away your own admin access. Since
    # only admins can reach this endpoint, this also guarantees the install
    # always keeps at least one admin.
    if user.id == admin.id and user.is_admin and not new_admin:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "You cannot remove your own admin access.",
        )

    user.role = new_role
    user.is_admin = new_admin
    if data.display_name is not None:
        user.display_name = data.display_name
    if "birthdate" in data.model_fields_set:
        user.birthdate = data.birthdate
    if data.password is not None:
        user.password_hash = hash_password(data.password)
        # A password change ends the account's existing sessions everywhere:
        # tokens carry the version they were minted under, and this bump makes
        # all of them stale. That's the point of resetting a lost phone's
        # password. When the admin changed their own, re-issue their cookie in
        # this same response so they stay signed in here.
        user.token_version += 1
        if user.id == admin.id:
            set_session_cookie(response, str(user.id), user.token_version)

    db.commit()
    db.refresh(user)
    return user


@router.post("/users/{user_id}/reset-password", response_model=ResetPasswordOut)
def reset_password(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Admin-only: replace a member's forgotten password with a generated one.

    The response is the only time the password is ever visible — the admin
    hands it to the member, whose account is then locked to the
    choose-your-own-password flow until they set one (must_change_password).
    Their existing sessions end immediately (token_version bump).
    """
    user = _managed_user(db, user_id, admin)
    if user.id == admin.id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Change your own password under Preferences instead.",
        )

    password = generate_password()
    user.password_hash = hash_password(password)
    user.must_change_password = True
    user.token_version += 1
    db.commit()
    db.refresh(user)
    return ResetPasswordOut(password=password, user=user)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Admin-only: remove a family member's account."""
    user = _managed_user(db, user_id, admin)

    # Same lockout rule as above: an admin can never delete themselves, so
    # there is always a working admin account left to sign in with.
    if user.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot delete your own account.")

    db.delete(user)
    db.commit()
