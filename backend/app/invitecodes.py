"""One-time invite codes, shared by villages and account signup.

8 characters from an alphabet without lookalikes (no 0/O/1/I/L), so a code
survives being read over the phone. Only the SHA-256 of a code is stored — a
database read never exposes a live door key — and the plaintext is returned
exactly once, by the endpoint that minted it. Wrong, expired, and
never-existed codes must always answer identically at the API layer, so
probing reveals nothing.
"""
import datetime as dt
import hashlib
import secrets

ALPHABET = "ABCDEFGHJKMNPQRSTVWXYZ23456789"
CODE_LEN = 8


def mint_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(CODE_LEN))


def pretty(code: str) -> str:
    """ABCD-EFGH — the dash is display sugar, stripped again on entry."""
    return f"{code[:4]}-{code[4:]}"


def normalize(code: str) -> str:
    return code.replace("-", "").replace(" ", "").strip().upper()


def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def still_valid(expires_at: dt.datetime | None, now: dt.datetime) -> bool:
    """Has this expiry not passed yet? SQLite (tests) hands back naive
    datetimes for timezone-aware columns; Postgres hands back aware ones.
    Compare in UTC either way."""
    if expires_at is None:
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=dt.timezone.utc)
    return expires_at > now
