import datetime as dt

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Response

from app.config import settings

# One reusable hasher with sensible defaults. Argon2 is memory-hard, so it
# resists GPU brute-forcing far better than older schemes like bcrypt/sha.
_hasher = PasswordHasher()

_ALGORITHM = "HS256"  # symmetric signing with our SECRET_KEY


def hash_password(raw: str) -> str:
    return _hasher.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, raw)
    except VerifyMismatchError:
        return False


def create_access_token(subject: str) -> str:
    """Issue a signed JWT whose `sub` claim is the user's id."""
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + dt.timedelta(days=settings.session_days),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=_ALGORITHM)


def decode_token(token: str) -> dict:
    """Verify signature + expiry and return the claims. Raises on bad/expired."""
    return jwt.decode(token, settings.secret_key, algorithms=[_ALGORITHM])


def set_session_cookie(response: Response, subject: str) -> None:
    """Attach a fresh signed-JWT session cookie to the response."""
    token = create_access_token(subject)
    response.set_cookie(
        key=settings.cookie_name,
        value=token,
        httponly=True,  # JavaScript can't read it -> XSS can't steal it
        samesite="lax",  # not sent on cross-site requests -> CSRF mitigation
        secure=settings.cookie_secure,  # HTTPS-only in production
        max_age=settings.session_days * 24 * 3600,
        path="/",
    )
