from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import get_current_user, require_admin
from app.models import Role, User
from app.schemas import BootstrapIn, CreateUserIn, LoginIn, SetupOut, UpdateUserIn, UserOut
from app.security import hash_password, set_session_cookie, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/setup", response_model=SetupOut)
def setup_state(db: Session = Depends(get_db)):
    """Is this install set up yet? Drives the first-run wizard vs. login."""
    user_count = db.scalar(select(func.count()).select_from(User))
    return SetupOut(initialized=bool(user_count))


@router.post("/bootstrap", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def bootstrap(data: BootstrapIn, response: Response, db: Session = Depends(get_db)):
    """Create the first parent account. Allowed only while no users exist."""
    user_count = db.scalar(select(func.count()).select_from(User))
    if user_count:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Already initialized")

    user = User(
        username=data.username,
        display_name=data.display_name,
        password_hash=hash_password(data.password),
        role=Role.parent,
        is_admin=True,  # the first account is always the master admin
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    set_session_cookie(response, str(user.id))
    return user


@router.post("/login", response_model=UserOut)
def login(data: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == data.username))
    # Same error whether the user is missing or the password is wrong, so an
    # attacker can't tell which usernames exist.
    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    set_session_cookie(response, str(user.id))
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    response.delete_cookie(settings.cookie_name, path="/")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    """Who am I? Used by the frontend to restore the session on page load."""
    return user


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    data: CreateUserIn,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Admin-only: create another family member's account."""
    if db.scalar(select(User).where(User.username == data.username)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already taken")

    # Default admin from role unless explicitly set. A child can never be admin.
    is_admin = data.is_admin if data.is_admin is not None else (data.role == Role.parent)
    if data.role == Role.child and is_admin:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A child account cannot be an admin")

    user = User(
        username=data.username,
        display_name=data.display_name,
        password_hash=hash_password(data.password),
        role=data.role,
        is_admin=is_admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    """Admin-only: everyone in the family, for the dashboard."""
    return db.scalars(select(User).order_by(User.created_at)).all()


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    data: UpdateUserIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Admin-only: edit a family member (name, role, admin flag, password)."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such user")

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
    if data.password is not None:
        user.password_hash = hash_password(data.password)

    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Admin-only: remove a family member's account."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such user")

    # Same lockout rule as above: an admin can never delete themselves, so
    # there is always a working admin account left to sign in with.
    if user.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot delete your own account.")

    db.delete(user)
    db.commit()
