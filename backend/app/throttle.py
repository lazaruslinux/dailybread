"""In-memory login throttle.

Argon2 makes each password guess expensive for us; this makes a sustained
guessing run expensive for the guesser: too many failures against the same
username inside the window and further tries are refused until it cools off.

Keyed by username rather than client address on purpose — behind the reverse
proxy every request can look like the same client, and the thing worth
protecting is the account under attack. Unknown usernames are throttled the
same way, so the 429 doesn't reveal which accounts exist. State is in-process
memory: a restart forgets it, which is fine for what it defends against.
"""

import threading
import time

# 10 wrong passwords against one username inside 15 minutes locks that
# username's logins until attempts age out of the window.
MAX_FAILURES = 10
WINDOW_SECONDS = 15 * 60

_failures: dict[str, list[float]] = {}
_lock = threading.Lock()


def _fresh(times: list[float], now: float) -> list[float]:
    cutoff = now - WINDOW_SECONDS
    return [t for t in times if t > cutoff]


def too_many_failures(key: str, limit: int = MAX_FAILURES) -> bool:
    """Is this key locked out right now? Prunes expired attempts as it looks.
    Callers guarding a shared/global key (e.g. anonymous invite redemption)
    pass a higher limit so one prankster can't starve a legitimate user as
    easily."""
    now = time.monotonic()
    with _lock:
        times = _fresh(_failures.get(key, []), now)
        if times:
            _failures[key] = times
        else:
            _failures.pop(key, None)
        return len(times) >= limit


def record_failure(key: str) -> None:
    now = time.monotonic()
    with _lock:
        _failures[key] = _fresh(_failures.get(key, []), now) + [now]


def clear(key: str | None = None) -> None:
    """Forget one key's failures (on successful login), or everything (tests)."""
    with _lock:
        if key is None:
            _failures.clear()
        else:
            _failures.pop(key, None)
