"""Family-local wall clocks.

The server runs on one clock (the TZ environment variable), but families on
a shared install may not all live in it. families.timezone holds an IANA
zone name ("America/Phoenix"); anything schedule-shaped converts through it
before comparing against the wall-clock times stored on cards. NULL means
"the server's clock", which is exactly the single-family behavior.
"""

import datetime as dt
from zoneinfo import ZoneInfo


def valid_timezone(name: str) -> bool:
    try:
        ZoneInfo(name)
    except Exception:
        return False
    return True


def family_now(now: dt.datetime, tz_name: str | None) -> dt.datetime:
    """A family's wall clock, given the server's. A naive `now` is taken as
    server-local time; the result is naive family-local time, directly
    comparable to stored card times. A zone that fails to load falls back to
    the server clock — reminders on the wrong clock beat no reminders."""
    if not tz_name:
        return now
    try:
        return now.astimezone(ZoneInfo(tz_name)).replace(tzinfo=None)
    except Exception:
        return now
