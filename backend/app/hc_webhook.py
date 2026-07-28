"""The Android dialect of the fitness ingest: HC Webhook payloads.

HC Webhook (an open-source Android app) reads Health Connect — where Pixel
Watch, Fitbit, and Samsung Health data lands — and POSTs it to a configured
URL on a schedule, with the same Authorization header our tokens already use.
Its payload is one flat object: `timestamp`, `app_version`, and a snake_case
array per data type. Times are ISO-8601 UTC, so everything converts to the
FAMILY's wall clock before day bucketing — otherwise an evening walk in
Phoenix files under tomorrow.

The Apple path (Health Auto Export) stays exactly as it was; the ingest route
sniffs which dialect arrived and the same idempotent upserts absorb both.
Known v1 gaps, accepted: HC Webhook sends no GPS routes and no per-session
calories, so Android workout cards have no little map and the watch-kcal
opt-in earns 0 until the bridge exposes energy per session.
"""

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clock import family_now
from app.models import Family, User, WeightEntry


def looks_like(payload: dict) -> bool:
    """HC Webhook payloads carry app_version + type arrays and never HAE's
    {"data": {...}} envelope."""
    if not isinstance(payload, dict) or isinstance(payload.get("data"), dict):
        return False
    return "app_version" in payload or any(
        isinstance(payload.get(k), list)
        for k in ("steps", "active_calories", "exercise_sessions", "exercise")
    )


def _num(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) else None


def _local(raw, tz_name: str | None) -> dt.datetime | None:
    """An ISO-8601 UTC timestamp as naive family-local time — the same wall
    clock every other time in the app lives on."""
    if not isinstance(raw, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    # family_now handles the zone lookup; feed it the server-local equivalent
    # so a NULL zone means "server clock", as always. Its no-zone path returns
    # the input untouched — still aware here — so strip explicitly: everything
    # downstream stores and compares naive wall times.
    return family_now(parsed.astimezone(), tz_name).replace(tzinfo=None)


# Truncation bound per list, matching the HAE dialect's MAX_POINTS_PER_METRIC
# in routers/fitness.py (which imports this module, so the constant lives in
# both places): ~65k is 45 days of minute-level samples.
MAX_POINTS = 70_000


def _points(payload: dict, key: str) -> list[dict]:
    raw = payload.get(key)
    if not isinstance(raw, list):
        return []
    return [p for p in raw[:MAX_POINTS] if isinstance(p, dict)]


def _sum_by_day(points, when_key, qty_key, tz) -> dict[dt.date, float]:
    by_day: dict[dt.date, float] = {}
    for p in points:
        when = _local(p.get(when_key), tz)
        qty = _num(p.get(qty_key))
        if when is None or qty is None:
            continue
        by_day[when.date()] = by_day.get(when.date(), 0.0) + qty
    return by_day


def _hourly(points, when_key, qty_key, tz, combine) -> dict[tuple[dt.date, int], float]:
    """Bucket points to (day, hour); sum cumulative metrics, average rates."""
    buckets: dict[tuple[dt.date, int], list[float]] = {}
    for p in points:
        when = _local(p.get(when_key), tz)
        qty = _num(p.get(qty_key))
        if when is None or qty is None:
            continue
        buckets.setdefault((when.date(), when.hour), []).append(qty)
    return {
        k: (sum(v) if combine == "sum" else sum(v) / len(v)) for k, v in buckets.items()
    }


def import_payload(
    db: Session, user: User, payload: dict, upsert_daily, import_workout_row, upsert_intraday
) -> tuple[int, int, set[dt.date]]:
    """Absorb one HC Webhook payload. Returns (metric-days touched, workouts
    touched, workout days) — the same accounting the Apple path reports.

    upsert_daily, import_workout_row, and upsert_intraday are the fitness
    router's own helpers, passed in so both dialects share one write path."""
    family = db.get(Family, user.family_id)
    tz = family.timezone if family else None
    days = 0

    # (payload key, our metric, qty field, unit, combine) for the metrics that
    # store both a daily total and an hourly breakdown for the time-of-day charts.
    for key, metric, field, unit in (
        ("steps", "steps", "count", "count"),
        ("active_calories", "active_kcal", "calories", "kcal"),
        # Provisional distance array, mirroring the workout session's
        # distance_meters — harmless if the bridge omits it; confirm against a
        # real Health Connect payload before relying on it.
        ("distance", "distance", "distance_meters", "m"),
    ):
        pts = _points(payload, key)
        for day, total in _sum_by_day(pts, "start_time", field, tz).items():
            upsert_daily(db, user, day, metric, total, unit)
            days += 1
        for (day, hour), total in _hourly(pts, "start_time", field, tz, "sum").items():
            upsert_intraday(db, user, day, hour, metric, total, unit)

    # All-day heart rate (if present) feeds the time-of-day HR line, hourly avg.
    for (day, hour), avg in _hourly(
        _points(payload, "heart_rate"), "time", "bpm", tz, "avg"
    ).items():
        upsert_intraday(db, user, day, hour, "hr", avg, "count/min")

    # Resting HR arrives as point readings; the day's value is their average.
    hr_by_day: dict[dt.date, list[float]] = {}
    for p in _points(payload, "resting_heart_rate"):
        when = _local(p.get("time"), tz)
        bpm = _num(p.get("bpm"))
        if when is not None and bpm is not None:
            hr_by_day.setdefault(when.date(), []).append(bpm)
    for day, values in hr_by_day.items():
        upsert_daily(db, user, day, "resting_hr", sum(values) / len(values), "count/min")
        days += 1

    # Sessions become workouts, and their minutes double as the day's
    # exercise-minutes metric (Health Connect has no separate daily total).
    workouts = 0
    workout_days: set[dt.date] = set()
    minutes_by_day: dict[dt.date, float] = {}
    for p in [*_points(payload, "exercise_sessions"), *_points(payload, "exercise")]:
        started = _local(p.get("start_time"), tz)
        activity = p.get("type")
        if started is None or not isinstance(activity, str) or not activity.strip():
            continue
        duration = _num(p.get("duration_seconds"))
        import_workout_row(
            db,
            user,
            external_id=None,
            activity=activity.strip().replace("_", " ").title()[:80],
            started_at=started,
            ended_at=_local(p.get("end_time"), tz),
            duration_s=duration,
            # No real HC payload has carried per-session energy yet; try the
            # plausible spellings and take the first that parses as a number,
            # so one malformed key can't shadow a good one.
            kcal=next(
                (
                    n
                    for k in ("calories", "active_calories", "energy_kcal", "kcal")
                    if (n := _num(p.get(k))) is not None
                ),
                None,
            ),
            distance_m=_num(p.get("distance_meters")),
            avg_hr=_num(p.get("avg_heart_rate")),
            route=None,
            source="android",
        )
        workouts += 1
        workout_days.add(started.date())
        if duration:
            minutes_by_day[started.date()] = minutes_by_day.get(started.date(), 0.0) + duration / 60
    for day, minutes in minutes_by_day.items():
        upsert_daily(db, user, day, "exercise_minutes", minutes, "min")
        days += 1

    # Weight is already kilograms; the newest reading per day wins, and a
    # deliberate in-app weigh-in always beats the sync (same rule as Apple).
    last_weight: dict[dt.date, tuple[dt.datetime, float]] = {}
    for p in _points(payload, "weight"):
        when = _local(p.get("time"), tz)
        kg = _num(p.get("kilograms"))
        if when is None or kg is None:
            continue
        day = when.date()
        if day not in last_weight or when > last_weight[day][0]:
            last_weight[day] = (when, kg)
    for day, (_, kg) in last_weight.items():
        existing = db.scalar(
            select(WeightEntry).where(
                WeightEntry.user_id == user.id, WeightEntry.date_for == day
            )
        )
        if existing is None:
            db.add(WeightEntry(user_id=user.id, date_for=day, weight_kg=round(kg, 2)))
            days += 1

    # Body fat fills blanks on the day's weigh-in, never overwrites — the
    # same-payload weigh-ins must be queryable first (no autoflush). Deduped
    # to the day's latest reading first, so a dense export costs one query
    # per day rather than one per sample.
    db.flush()
    fat_by_day: dict[dt.date, tuple[dt.datetime, float]] = {}
    for p in _points(payload, "body_fat"):
        when = _local(p.get("time"), tz)
        pct = _num(p.get("percentage"))
        if when is None or pct is None or not (1.0 < pct <= 75.0):
            continue
        day = when.date()
        if day not in fat_by_day or when > fat_by_day[day][0]:
            fat_by_day[day] = (when, pct)
    for day, (_, pct) in fat_by_day.items():
        entry = db.scalar(
            select(WeightEntry).where(
                WeightEntry.user_id == user.id, WeightEntry.date_for == day
            )
        )
        if entry is not None and entry.body_fat_pct is None:
            entry.body_fat_pct = round(pct, 1)
            days += 1

    return days, workouts, workout_days
