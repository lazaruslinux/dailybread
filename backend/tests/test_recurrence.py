"""Unit tests for the pure recurrence date math (no database)."""

import datetime as dt

from app.models import RepeatType
from app.recurrence import ALL_WEEKDAYS, occurs_on, streak

D = dt.date


def _weekly(days, interval=1, anchor=None, until=None):
    return dict(
        repeat_type=RepeatType.weekly,
        repeat_days=days,
        repeat_interval=interval,
        repeat_anchor=anchor,
        repeat_month_day=None,
        repeat_until=until,
    )


def _monthly(month_day, interval=1, anchor=None, until=None):
    return dict(
        repeat_type=RepeatType.monthly,
        repeat_days=None,
        repeat_interval=interval,
        repeat_anchor=anchor,
        repeat_month_day=month_day,
        repeat_until=until,
    )


def _occurs(spec, date):
    return occurs_on(
        spec["repeat_type"],
        spec["repeat_days"],
        spec["repeat_interval"],
        spec["repeat_anchor"],
        spec["repeat_month_day"],
        spec["repeat_until"],
        date,
    )


def test_daily_routine_lands_every_day():
    spec = _weekly(ALL_WEEKDAYS)
    for offset in range(14):
        assert _occurs(spec, D(2026, 7, 5) + dt.timedelta(days=offset))


def test_weekly_lands_only_on_chosen_weekdays():
    # Tue (1) and Thu (3).
    spec = _weekly((1 << 1) | (1 << 3))
    # 2026-07-06 is a Monday; walk the week.
    monday = D(2026, 7, 6)
    got = {i for i in range(7) if _occurs(spec, monday + dt.timedelta(days=i))}
    assert got == {1, 3}


def test_every_other_week_phases_off_the_anchor():
    anchor = D(2026, 7, 6)  # a Monday, week 0
    spec = _weekly(1 << 0, interval=2, anchor=anchor)  # every other Monday
    assert _occurs(spec, D(2026, 7, 6))  # week 0: yes
    assert not _occurs(spec, D(2026, 7, 13))  # week 1: no
    assert _occurs(spec, D(2026, 7, 20))  # week 2: yes


def test_monthly_lands_on_its_day():
    spec = _monthly(15)
    assert _occurs(spec, D(2026, 7, 15))
    assert not _occurs(spec, D(2026, 7, 14))
    assert _occurs(spec, D(2026, 8, 15))


def test_monthly_day_31_clamps_to_the_last_day_of_short_months():
    spec = _monthly(31)
    assert _occurs(spec, D(2026, 1, 31))  # January has a 31st
    assert _occurs(spec, D(2026, 2, 28))  # February clamps to the 28th
    assert not _occurs(spec, D(2026, 2, 27))
    assert _occurs(spec, D(2026, 4, 30))  # April clamps to the 30th


def test_every_other_month_phases_off_the_anchor():
    anchor = D(2026, 7, 1)
    spec = _monthly(1, interval=2, anchor=anchor)
    assert _occurs(spec, D(2026, 7, 1))  # month 0
    assert not _occurs(spec, D(2026, 8, 1))  # month 1
    assert _occurs(spec, D(2026, 9, 1))  # month 2


def test_weekly_stops_after_its_until_date():
    last = D(2026, 7, 20)  # a Monday
    spec = _weekly(1 << 0, until=last)  # every Monday, ending on one
    assert _occurs(spec, D(2026, 7, 13))
    assert _occurs(spec, last)  # the boundary day itself still lands
    assert not _occurs(spec, D(2026, 7, 27))


def test_until_cuts_a_repeat_short_mid_pattern():
    # Tue/Thu, ending on a Tuesday: that Thursday never comes.
    spec = _weekly((1 << 1) | (1 << 3), until=D(2026, 7, 7))
    assert _occurs(spec, D(2026, 7, 7))
    assert not _occurs(spec, D(2026, 7, 9))


def test_until_holds_across_interval_phasing():
    anchor = D(2026, 7, 6)  # a Monday, week 0
    spec = _weekly(1 << 0, interval=2, anchor=anchor, until=D(2026, 7, 20))
    assert _occurs(spec, D(2026, 7, 20))  # week 2, the last one
    assert not _occurs(spec, D(2026, 8, 3))  # week 4 would have landed


def test_monthly_stops_after_its_until_date():
    spec = _monthly(15, until=D(2026, 8, 15))
    assert _occurs(spec, D(2026, 8, 15))
    assert not _occurs(spec, D(2026, 9, 15))


def test_monthly_until_holds_across_interval_phasing():
    anchor = D(2026, 7, 1)
    spec = _monthly(1, interval=2, anchor=anchor, until=D(2026, 9, 1))
    assert _occurs(spec, D(2026, 9, 1))  # month 2, the last one
    assert not _occurs(spec, D(2026, 11, 1))  # month 4 would have landed


def test_streak_counts_consecutive_completed_occurrences():
    spec = _weekly(ALL_WEEKDAYS)
    upto = D(2026, 7, 5)
    done = {upto, upto - dt.timedelta(days=1), upto - dt.timedelta(days=2)}
    assert streak(**spec, completed_dates=done, upto=upto) == 3


def test_streak_gives_grace_to_a_pending_today():
    spec = _weekly(ALL_WEEKDAYS)
    upto = D(2026, 7, 5)
    # Today not done, but the two days before were.
    done = {upto - dt.timedelta(days=1), upto - dt.timedelta(days=2)}
    assert streak(**spec, completed_dates=done, upto=upto) == 2


def test_streak_breaks_on_a_missed_earlier_occurrence():
    spec = _weekly(ALL_WEEKDAYS)
    upto = D(2026, 7, 5)
    # Missed the day before yesterday, so only today + yesterday count.
    done = {upto, upto - dt.timedelta(days=1), upto - dt.timedelta(days=3)}
    assert streak(**spec, completed_dates=done, upto=upto) == 2


def test_streak_ignores_days_past_the_until_date():
    # Daily, ended two days ago: the chain is what was completed while it ran,
    # and the days since aren't misses.
    upto = D(2026, 7, 5)
    spec = _weekly(ALL_WEEKDAYS, until=D(2026, 7, 3))
    done = {D(2026, 7, 3), D(2026, 7, 2), D(2026, 7, 1)}
    assert streak(**spec, completed_dates=done, upto=upto) == 3


def test_streak_follows_a_sparse_weekly_schedule():
    # Tue/Thu; completing both this week and last week is a 4-occurrence streak.
    spec = _weekly((1 << 1) | (1 << 3))
    upto = D(2026, 7, 9)  # Thursday
    done = {D(2026, 7, 9), D(2026, 7, 7), D(2026, 7, 2), D(2026, 6, 30)}
    assert streak(**spec, completed_dates=done, upto=upto) == 4
