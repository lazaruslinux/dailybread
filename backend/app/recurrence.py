"""Pure date math for routine recurrence.

Kept free of the database and the ORM so it can be reasoned about and tested on
its own. Everything here is a plain function over dates and the recurrence
fields stored on an Item (repeat_type, repeat_days, repeat_interval,
repeat_anchor, repeat_month_day).

Weekday bitmask convention: Monday = bit 0 ... Sunday = bit 6, matching
datetime.date.weekday(). All seven bits set (127) is a plain daily routine.
"""

import calendar
import datetime as dt

from app.models import RepeatType

ALL_WEEKDAYS = 0b1111111  # 127: every day
# The most days we scan backwards when counting a streak, so a sparse routine
# (say, monthly) still terminates. Two years comfortably covers any real chain.
_STREAK_SCAN_LIMIT = 800


def _week_start(d: dt.date) -> dt.date:
    """The Monday of d's week."""
    return d - dt.timedelta(days=d.weekday())


def occurs_on(
    repeat_type: RepeatType | None,
    repeat_days: int | None,
    repeat_interval: int | None,
    repeat_anchor: dt.date | None,
    repeat_month_day: int | None,
    repeat_until: dt.date | None,
    date: dt.date,
) -> bool:
    """Does a routine with these recurrence fields land on `date`?"""
    if repeat_until is not None and date > repeat_until:
        return False  # the repeat has run out; nothing lands past its last day
    interval = repeat_interval or 1

    if repeat_type == RepeatType.weekly:
        if not repeat_days or not (repeat_days & (1 << date.weekday())):
            return False
        if interval > 1:
            base = _week_start(repeat_anchor or date)
            weeks = (_week_start(date) - base).days // 7
            if weeks % interval != 0:
                return False
        return True

    if repeat_type == RepeatType.monthly:
        if not repeat_month_day:
            return False
        # Clamp so "the 31st" lands on the last day of shorter months.
        last_day = calendar.monthrange(date.year, date.month)[1]
        if date.day != min(repeat_month_day, last_day):
            return False
        if interval > 1:
            anchor = repeat_anchor or date
            months = (date.year - anchor.year) * 12 + (date.month - anchor.month)
            if months % interval != 0:
                return False
        return True

    return False


def streak(
    repeat_type: RepeatType | None,
    repeat_days: int | None,
    repeat_interval: int | None,
    repeat_anchor: dt.date | None,
    repeat_month_day: int | None,
    repeat_until: dt.date | None,
    completed_dates: set[dt.date],
    upto: dt.date,
) -> int:
    """Consecutive scheduled occurrences completed, counting back from `upto`.

    Grace on the most recent occurrence: if the routine is scheduled for today
    but not yet done, the streak earned up to yesterday still shows. A missed
    earlier occurrence breaks the chain.
    """
    count = 0
    seen_first = False
    day = upto
    for _ in range(_STREAK_SCAN_LIMIT):
        if occurs_on(
            repeat_type,
            repeat_days,
            repeat_interval,
            repeat_anchor,
            repeat_month_day,
            repeat_until,
            day,
        ):
            if day in completed_dates:
                count += 1
            elif seen_first:
                break  # a genuinely missed occurrence ends the streak
            # else: the most recent occurrence is still pending -> grace
            seen_first = True
        day -= dt.timedelta(days=1)
    return count
