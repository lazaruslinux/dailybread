import datetime as dt

import jwt
from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import Role, User
from app.security import decode_token, set_session_cookie


def get_current_user(
    request: Request, response: Response, db: Session = Depends(get_db)
) -> User:
    """Resolve the logged-in user from the session cookie, or raise 401."""
    token = request.cookies.get(settings.cookie_name)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = decode_token(token)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")

    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists")

    # A token minted before the account's last password change is refused even
    # though its signature and expiry still check out. (Tokens from before the
    # "ver" claim existed read as version 0, matching un-bumped accounts.)
    if payload.get("ver", 0) != user.token_version:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")

    # Sliding session: once the token is more than a day old, re-issue it so
    # the expiry keeps moving forward. Anyone who opens the app at least once
    # every session_days stays logged in; only true inactivity logs you out.
    # (Cookie headers set on this injected Response merge into the real one.)
    issued = dt.datetime.fromtimestamp(payload["iat"], tz=dt.timezone.utc)
    age = dt.datetime.now(dt.timezone.utc) - issued
    if age > dt.timedelta(hours=settings.session_refresh_after_hours):
        set_session_cookie(response, str(user.id), user.token_version)

    return user


def require_family(user: User = Depends(get_current_user)) -> User:
    """Gate every data endpoint: a new-household account that hasn't run its
    create-your-family wizard belongs to no family and can't touch anything."""
    if user.family_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Create your family first")
    return user


def require_admin(user: User = Depends(require_family)) -> User:
    """Gate admin-only actions (the dashboard: managing accounts, settings)."""
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins only")
    return user


def require_parent(user: User = Depends(require_family)) -> User:
    """Gate parent-only actions (managing the board). Distinct from admin:
    a non-admin parent still runs the family's day-to-day."""
    if user.role != Role.parent:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Parents only")
    return user
