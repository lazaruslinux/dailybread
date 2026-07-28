import datetime as dt
import secrets

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Request, Response

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


# Vocabulary for generated reset passwords. Short, concrete, unambiguous
# words: the admin reads the password to the member across the room and the
# member types it on a phone, so "cedar-lantern-42" beats "xK9#mQ2v". Two
# words plus two digits is modest entropy on purpose — the login throttle
# caps guessing, the LAN is the whole attack surface, and the password dies
# at first sign-in when its owner is forced to pick their own.
_WORDS = (
    "acorn", "amber", "aspen", "badge", "basil", "beach", "berry", "birch",
    "brave", "bread", "brook", "candle", "canyon", "cedar", "cliff", "clover",
    "coral", "creek", "crisp", "dawn", "delta", "drift", "dune", "ember",
    "fable", "fern", "field", "flint", "forest", "fox", "garden", "glade",
    "grain", "grove", "harbor", "hazel", "hearth", "hill", "honey", "iris",
    "ivory", "juniper", "kite", "lake", "lantern", "laurel", "leaf", "linen",
    "maple", "marble", "meadow", "mint", "moss", "north", "oak", "ocean",
    "olive", "orchard", "otter", "pearl", "pebble", "pine", "plum", "pond",
    "prairie", "quill", "rain", "raven", "reed", "ridge", "river", "robin",
    "rose", "sage", "sand", "shore", "sky", "slate", "spring", "sprout",
    "stone", "storm", "summit", "thistle", "timber", "trail", "tulip", "vale",
    "violet", "walnut", "wheat", "willow", "wren", "yarrow", "cobalt", "russet",
)


def generate_password() -> str:
    """A reset password an admin can hand over: word-word-NN."""
    a, b = secrets.choice(_WORDS), secrets.choice(_WORDS)
    return f"{a}-{b}-{secrets.randbelow(90) + 10}"


def create_access_token(subject: str, version: int = 0) -> str:
    """Issue a signed JWT whose `sub` claim is the user's id. `ver` records the
    account's token_version at mint time; a later password change bumps the
    account's version, and tokens carrying the old one stop being accepted."""
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": subject,
        "ver": version,
        "iat": now,
        "exp": now + dt.timedelta(days=settings.session_days),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=_ALGORITHM)


def decode_token(token: str) -> dict:
    """Verify signature + expiry and return the claims. Raises on bad/expired."""
    return jwt.decode(token, settings.secret_key, algorithms=[_ALGORITHM])


def cookie_secure(request: Request | None) -> bool:
    """Whether to mark the session cookie Secure. COOKIE_SECURE=true/false
    forces it; the "auto" default follows how this request actually arrived,
    trusting the proxy chain's X-Forwarded-Proto when present. A direct client
    lying in that header only breaks its own login, never anyone else's."""
    forced = settings.cookie_secure.strip().lower()
    if forced in {"true", "1", "yes"}:
        return True
    if forced in {"false", "0", "no"}:
        return False
    if request is None:
        return False
    return request.headers.get("x-forwarded-proto", request.url.scheme) == "https"


def set_session_cookie(
    response: Response, subject: str, version: int = 0, *, request: Request | None = None
) -> None:
    """Attach a fresh signed-JWT session cookie to the response."""
    token = create_access_token(subject, version)
    response.set_cookie(
        key=settings.cookie_name,
        value=token,
        httponly=True,  # JavaScript can't read it -> XSS can't steal it
        samesite="lax",  # not sent on cross-site requests -> CSRF mitigation
        secure=cookie_secure(request),  # HTTPS-only whenever HTTPS is in play
        max_age=settings.session_days * 24 * 3600,
        path="/",
    )
