"""Family-local wall clocks.

The server runs on one clock (the TZ environment variable), but families on
a shared install may not all live in it. families.timezone holds an IANA
zone name ("America/Phoenix"); anything schedule-shaped converts through it
before comparing against the wall-clock times stored on cards. NULL means
"the server's clock", which is exactly the single-family behavior.
"""

import datetime as dt
import os
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


def _zone(tz_name: str | None) -> ZoneInfo | dt.tzinfo:
    """The zone a NULL family timezone means: the server's own. Resolved from
    the TZ environment variable as a real IANA zone so a conversion honours the
    date's own DST offset; the current fixed-offset tzinfo would apply today's
    offset to a date on the other side of a boundary, an hour off. TZ unset or
    unloadable falls back to that fixed offset, the module's graceful-failure
    philosophy (see family_now)."""
    if tz_name:
        return ZoneInfo(tz_name)
    env = os.environ.get("TZ")
    if env:
        try:
            return ZoneInfo(env)
        except Exception:
            pass
    server = dt.datetime.now().astimezone().tzinfo
    return server if server is not None else dt.timezone.utc


def shift_schedule(
    date_for: dt.date,
    time_of_day: dt.time | None,
    end_time: dt.time | None,
    all_day: bool,
    from_tz: str | None,
    to_tz: str | None,
    end_date: dt.date | None = None,
) -> tuple[dt.date, dt.time | None, dt.time | None, dt.date | None]:
    """A village event's schedule moved from the organizer family's wall
    clock onto an attendee family's. All-day (or timeless) events stay on
    their calendar date everywhere — "Saturday's fair" is Saturday in every
    zone.

    A SINGLE-DAY timed event converts its start instant; the end travels as a
    DURATION added to the converted start (so a DST boundary can't stretch or
    shrink the event), clamped to 23:59 when the converted span would cross
    midnight — such a card holds one date and two times, nothing more.

    A MULTI-DAY timed event has a real end instant of its own, on end_date, so
    both ends convert independently. The duration trick would be wrong here
    twice over: it measures the end time against the START day, and its
    midnight clamp would pin a Sunday 4 PM finish at 23:59 on the wrong date.

    A zone that fails to load leaves the schedule untouched, the family_now
    philosophy."""
    if all_day or time_of_day is None:
        return date_for, time_of_day, end_time, end_date
    try:
        src, dst = _zone(from_tz), _zone(to_tz)
    except Exception:
        return date_for, time_of_day, end_time, end_date
    start = dt.datetime.combine(date_for, time_of_day).replace(tzinfo=src).astimezone(dst)
    new_date, new_start = start.date(), start.time()
    if end_date is not None and end_time is not None:
        end = dt.datetime.combine(end_date, end_time).replace(tzinfo=src).astimezone(dst)
        return new_date, new_start, end.time(), end.date()
    new_end = end_time
    if end_time is not None:
        duration = dt.datetime.combine(date_for, end_time) - dt.datetime.combine(
            date_for, time_of_day
        )
        end = start + duration
        new_end = end.time() if end.date() == start.date() else dt.time(23, 59)
    new_end_date = None if end_date is None else end_date + (new_date - date_for)
    return new_date, new_start, new_end, new_end_date
