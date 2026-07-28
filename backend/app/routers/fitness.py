"""Apple Health import and the Fitness tab's data.

POST /ingest/health takes the JSON that the Health Auto Export iOS app sends
(documented at github.com/Lybron/health-auto-export): {"data": {"metrics":
[{name, units, data: [{date, qty}]}], "workouts": [...]}}. It authenticates
with a per-member bearer token (models.IngestToken) instead of cookies, so
the endpoint a phone automation hits has no CSRF surface and no session.

Everything imported is self-only, like the diary — no parent exception, and
minors have no fitness area at all. Imports are idempotent: daily metrics
upsert on (member, day, metric) and workouts on the exporter's stable id, so
re-sending a whole window is always safe.
"""

import datetime as dt
import json
import logging
import secrets
from collections import defaultdict

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import crumbs, hc_webhook, throttle
from app.clock import family_now
from app.db import get_db
from app.deps import require_adult
from app.invitecodes import hash_code
from app.models import (
    Completion,
    Family,
    FitnessDaily,
    FitnessIntraday,
    IngestToken,
    Item,
    ItemKind,
    User,
    WeightEntry,
    Workout,
)
from app.recurrence import occurs_on
from app.schemas import (
    FitnessDayOut,
    FitnessGoalsIn,
    FitnessGoalsOut,
    FitnessHistoryOut,
    FitnessIntradayOut,
    FitnessOut,
    FitnessWeekDayOut,
    IngestResultOut,
    IngestTokenOut,
    WatchKcalIn,
    WorkoutOut,
)

router = APIRouter(tags=["fitness"])
log = logging.getLogger("dailybread.ingest")

# The Android dialect (HC Webhook). Un-parked 2026-07-11 so the connect flow
# can offer Android for real: unit-tested and exercised via captured payloads,
# still awaiting its first real device. Flip to False to park it again.
HC_INGEST_ENABLED = True

# Exporter metric name -> (our metric, how multiple same-day points combine).
# The exporter can send one point per day or many intra-day ones depending on
# its aggregation setting; summing cumulative metrics and averaging rates
# gives the same daily number either way.
METRIC_MAP = {
    "step_count": ("steps", "sum"),
    "active_energy": ("active_kcal", "sum"),
    "apple_exercise_time": ("exercise_minutes", "sum"),
    "resting_heart_rate": ("resting_hr", "avg"),
}
WEIGHT_METRIC = "weight_body_mass"
BODYFAT_METRIC = "body_fat_percentage"
# Walking + Running Distance. Kept out of METRIC_MAP because it needs per-entry
# unit handling (mi/km) rather than the plain sum/avg the others use; stored
# normalized to meters as the "distance" daily metric. Confirm this exporter key
# against a real HAE payload before relying on it in the wild.
DISTANCE_METRIC = "walking_running_distance"
# All-day heart rate (distinct from resting_heart_rate) feeds only the
# time-of-day HR line; there's no daily rollup, so it lives outside METRIC_MAP.
HEARTRATE_METRIC = "heart_rate"
# Which stored metrics also get an hourly breakdown for the time-of-day charts,
# and how points landing in the same hour combine.
INTRADAY_COMBINE = {"steps": "sum", "active_kcal": "sum", "distance": "sum", "hr": "avg"}

# One shared bucket for bad tokens, same reasoning as signup invites: the
# tokens are long random secrets, so every wrong guess is a fresh key and
# per-token buckets would throttle nothing.
INGEST_THROTTLE_KEY = "ingest-health"
INGEST_MAX_FAILURES = 30

# Sanity bounds on one payload's element counts, applied as plain truncation.
# A 45-day window of minute-level samples is ~65k points per metric; anything
# past these came from a hostile or broken exporter, not a phone. The metric
# cap clears HAE's full catalog, so even a select-everything setup never
# loses a tracked metric to truncation order.
MAX_METRICS = 200
MAX_WORKOUTS = 400
MAX_POINTS_PER_METRIC = 70_000

LB_TO_KG = 0.45359237
MILE_M = 1609.344


def _parse_when(raw) -> dt.datetime | None:
    """The exporter's timestamps ("2026-07-09 06:30:00 -0700") carry the
    phone's own offset. We keep the LOCAL wall time — the same clock every
    other time in the app lives on — and drop the offset."""
    if not isinstance(raw, str):
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(raw, fmt).replace(tzinfo=None)
        except ValueError:
            continue
    return None


def _qty(raw) -> float | None:
    """Numbers arrive bare or wrapped ({"qty": 5.2, "units": "km"})."""
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, dict) and isinstance(raw.get("qty"), (int, float)):
        return float(raw["qty"])
    return None


def _units(raw, fallback: str = "") -> str:
    if isinstance(raw, dict) and isinstance(raw.get("units"), str):
        return raw["units"]
    return fallback


def _meters(qty: float, unit: str) -> float:
    u = unit.lower()
    if u in ("km", "kilometers"):
        return qty * 1000.0
    if u in ("mi", "miles"):
        return qty * MILE_M
    return qty  # meters, or a bare number we take at face value


def _distance_m(raw) -> float | None:
    qty = _qty(raw)
    if qty is None:
        return None
    return _meters(qty, _units(raw))


def _ingest_user(db: Session, authorization: str | None) -> User:
    """The member a bearer token belongs to; anything else 401s uniformly."""
    if throttle.too_many_failures(INGEST_THROTTLE_KEY, limit=INGEST_MAX_FAILURES):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Try again later."
        )
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    row = (
        db.scalar(select(IngestToken).where(IngestToken.token_hash == hash_code(token)))
        if token
        else None
    )
    user = db.get(User, row.user_id) if row else None
    if user is None or user.family_id is None or user.is_minor:
        throttle.record_failure(INGEST_THROTTLE_KEY)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    row.last_used_at = dt.datetime.now(dt.timezone.utc)
    return user


def _prefetch_daily(
    db: Session, user: User, metric: str, days
) -> dict[dt.date, FitnessDaily]:
    """One query for a metric's existing rows across all of a payload's days,
    so a catch-up export upserts from memory instead of one SELECT per day."""
    days = list(days)
    if not days:
        return {}
    rows = db.scalars(
        select(FitnessDaily).where(
            FitnessDaily.user_id == user.id,
            FitnessDaily.metric == metric,
            FitnessDaily.date_for.in_(days),
        )
    )
    return {r.date_for: r for r in rows}


def _upsert_daily(
    db: Session,
    user: User,
    day: dt.date,
    metric: str,
    value: float,
    unit: str,
    cache: dict[dt.date, FitnessDaily] | None = None,
) -> None:
    if cache is not None:
        row = cache.get(day)
    else:
        row = db.scalar(
            select(FitnessDaily).where(
                FitnessDaily.user_id == user.id,
                FitnessDaily.date_for == day,
                FitnessDaily.metric == metric,
            )
        )
    if row is None:
        row = FitnessDaily(
            family_id=user.family_id, user_id=user.id, date_for=day, metric=metric
        )
        db.add(row)
        if cache is not None:
            cache[day] = row
    row.value = round(value, 2)
    row.unit = unit


def _prefetch_intraday(
    db: Session, user: User, metric: str, days
) -> dict[tuple[dt.date, int], FitnessIntraday]:
    """The intraday twin of _prefetch_daily: all of a metric's existing hourly
    rows for the payload's days in one query, keyed (day, hour)."""
    days = list(days)
    if not days:
        return {}
    rows = db.scalars(
        select(FitnessIntraday).where(
            FitnessIntraday.user_id == user.id,
            FitnessIntraday.metric == metric,
            FitnessIntraday.date_for.in_(days),
        )
    )
    return {(r.date_for, r.hour): r for r in rows}


def _upsert_intraday(
    db: Session,
    user: User,
    day: dt.date,
    hour: int,
    metric: str,
    value: float,
    unit: str,
    cache: dict[tuple[dt.date, int], FitnessIntraday] | None = None,
) -> None:
    if cache is not None:
        row = cache.get((day, hour))
    else:
        row = db.scalar(
            select(FitnessIntraday).where(
                FitnessIntraday.user_id == user.id,
                FitnessIntraday.date_for == day,
                FitnessIntraday.metric == metric,
                FitnessIntraday.hour == hour,
            )
        )
    if row is None:
        row = FitnessIntraday(
            family_id=user.family_id,
            user_id=user.id,
            date_for=day,
            metric=metric,
            hour=hour,
        )
        db.add(row)
        if cache is not None:
            cache[(day, hour)] = row
    row.value = round(value, 2)
    row.unit = unit


def _clean_points(points) -> list[tuple[dt.datetime, float]]:
    """The (when, qty) pairs of a metric's data array, the junk dropped."""
    out: list[tuple[dt.datetime, float]] = []
    for point in (points if isinstance(points, list) else [])[:MAX_POINTS_PER_METRIC]:
        when = _parse_when(point.get("date")) if isinstance(point, dict) else None
        qty = _qty(point.get("qty")) if isinstance(point, dict) else None
        if when is not None and qty is not None:
            out.append((when, qty))
    return out


def _store_intraday(db, user, metric, combine, unit, points_wq) -> None:
    """Bucket (when, qty) points to the hour and upsert the time-of-day rows.
    A single-daily-point exporter simply files everything under that point's
    hour — honest, if coarse, until the export sends finer samples."""
    by_hour: dict[tuple[dt.date, int], list[float]] = defaultdict(list)
    for when, qty in points_wq:
        by_hour[(when.date(), when.hour)].append(qty)
    cache = _prefetch_intraday(db, user, metric, {day for day, _ in by_hour})
    for (day, hour), vals in by_hour.items():
        value = sum(vals) if combine == "sum" else sum(vals) / len(vals)
        _upsert_intraday(db, user, day, hour, metric, value, unit, cache=cache)


def _import_metrics(db: Session, user: User, metrics) -> int:
    touched = 0
    # Body fat rides on the day's weight entry, so its points wait until every
    # other metric (weight included) has landed — the exporter doesn't promise
    # an order within one payload.
    bodyfat_points: list = []
    for entry in (metrics if isinstance(metrics, list) else [])[:MAX_METRICS]:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        unit = entry.get("units", "") if isinstance(entry.get("units"), str) else ""
        points = entry.get("data") if isinstance(entry.get("data"), list) else []

        if name == WEIGHT_METRIC:
            touched += _import_weight(db, user, points, unit)
            continue
        if name == BODYFAT_METRIC:
            bodyfat_points.extend(points)
            continue
        if name == DISTANCE_METRIC:
            touched += _import_distance(db, user, points, unit)
            continue
        if name == HEARTRATE_METRIC:
            # No daily rollup; the all-day HR line reads from intraday only.
            _store_intraday(db, user, "hr", "avg", unit or "count/min", _clean_points(points))
            continue
        if name not in METRIC_MAP:
            continue  # metrics we don't track yet are silently fine
        metric, combine = METRIC_MAP[name]
        wq = _clean_points(points)
        by_day: dict[dt.date, list[float]] = defaultdict(list)
        for when, qty in wq:
            by_day[when.date()].append(qty)
        cache = _prefetch_daily(db, user, metric, by_day)
        for day, values in by_day.items():
            value = sum(values) if combine == "sum" else sum(values) / len(values)
            _upsert_daily(db, user, day, metric, value, unit, cache=cache)
            touched += 1
        if metric in INTRADAY_COMBINE:
            _store_intraday(db, user, metric, combine, unit, wq)
    return touched + _import_body_fat(db, user, bodyfat_points)


def _import_distance(db: Session, user: User, points, unit: str) -> int:
    """Daily and hourly walking + running distance, normalized to meters. The
    exporter carries one unit for the whole metric (mi or km), so we sum each
    bucket's native points and convert once."""
    wq = _clean_points(points)
    by_day: dict[dt.date, float] = defaultdict(float)
    for when, qty in wq:
        by_day[when.date()] += qty
    daily_cache = _prefetch_daily(db, user, "distance", by_day)
    for day, native_total in by_day.items():
        _upsert_daily(db, user, day, "distance", _meters(native_total, unit), "m", cache=daily_cache)
    by_hour: dict[tuple[dt.date, int], float] = defaultdict(float)
    for when, qty in wq:
        by_hour[(when.date(), when.hour)] += qty
    hourly_cache = _prefetch_intraday(db, user, "distance", {day for day, _ in by_hour})
    for (day, hour), native in by_hour.items():
        _upsert_intraday(db, user, day, hour, "distance", _meters(native, unit), "m", cache=hourly_cache)
    return len(by_day)


def _import_weight(db: Session, user: User, points, unit: str) -> int:
    """Weigh-ins flow into the existing weight log so the calorie math picks
    them up — but only onto days with no entry yet: a deliberate in-app
    weigh-in always beats the scale sync."""
    last_by_day: dict[dt.date, tuple[dt.datetime, float]] = {}
    for point in (points if isinstance(points, list) else [])[:MAX_POINTS_PER_METRIC]:
        when = _parse_when(point.get("date")) if isinstance(point, dict) else None
        qty = _qty(point.get("qty")) if isinstance(point, dict) else None
        if when is None or qty is None:
            continue
        day = when.date()
        if day not in last_by_day or when > last_by_day[day][0]:
            last_by_day[day] = (when, qty)
    touched = 0
    for day, (_, qty) in last_by_day.items():
        existing = db.scalar(
            select(WeightEntry).where(
                WeightEntry.user_id == user.id, WeightEntry.date_for == day
            )
        )
        if existing is not None:
            continue
        kg = qty * LB_TO_KG if unit.lower().startswith("lb") else qty
        db.add(WeightEntry(user_id=user.id, date_for=day, weight_kg=round(kg, 2)))
        touched += 1
    return touched


def _import_body_fat(db: Session, user: User, points) -> int:
    """Body fat percentage joins the day's weight entry (the column the manual
    weigh-in form already fills) so the trend chart reads both lines from one
    log. It only fills a blank: a value someone typed is never overwritten,
    and a reading on a day with no weigh-in at all has nowhere to live — smart
    scales send weight and fat together, so that day's weight is normally in
    the same payload and has already landed by the time this runs."""
    last_by_day: dict[dt.date, tuple[dt.datetime, float]] = {}
    for point in points[:MAX_POINTS_PER_METRIC]:
        when = _parse_when(point.get("date")) if isinstance(point, dict) else None
        qty = _qty(point.get("qty")) if isinstance(point, dict) else None
        if when is None or qty is None:
            continue
        # HealthKit stores body fat as a fraction; the exporter has shipped it
        # both ways. No human is at 1% body fat, so a value at or below 1 can
        # only be a fraction.
        pct = qty * 100.0 if qty <= 1.0 else qty
        if not (1.0 < pct <= 75.0):
            continue
        day = when.date()
        if day not in last_by_day or when > last_by_day[day][0]:
            last_by_day[day] = (when, pct)
    touched = 0
    if last_by_day:
        # The session doesn't autoflush, and this payload's own weigh-ins are
        # usually still pending inserts — make them queryable first.
        db.flush()
    for day, (_, pct) in last_by_day.items():
        entry = db.scalar(
            select(WeightEntry).where(
                WeightEntry.user_id == user.id, WeightEntry.date_for == day
            )
        )
        if entry is None or entry.body_fat_pct is not None:
            continue
        entry.body_fat_pct = round(pct, 1)
        touched += 1
    return touched


# The thumbnail needs a shape, not a track: cap stored routes at this many
# evenly spaced points so a two-hour run costs the same few hundred bytes.
_ROUTE_MAX_POINTS = 60


def _parse_route(raw) -> list | None:
    """The exporter's route array, downsampled to [lat, lon] pairs. Newer
    exports name the keys latitude/longitude, older ones lat/lon; a point
    missing either is skipped."""
    if not isinstance(raw, list):
        return None
    pts = []
    for p in raw:
        if not isinstance(p, dict):
            continue
        lat = p.get("latitude", p.get("lat"))
        lon = p.get("longitude", p.get("lon"))
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            pts.append([round(float(lat), 5), round(float(lon), 5)])
    if len(pts) < 2:
        return None
    if len(pts) > _ROUTE_MAX_POINTS:
        step = (len(pts) - 1) / (_ROUTE_MAX_POINTS - 1)
        pts = [pts[round(i * step)] for i in range(_ROUTE_MAX_POINTS)]
    return pts


def _upsert_workout(
    db: Session,
    user: User,
    *,
    external_id: str | None,
    activity: str,
    started_at: dt.datetime,
    ended_at: dt.datetime | None,
    duration_s: float | None,
    kcal: float | None,
    distance_m: float | None,
    avg_hr: float | None,
    route: list | None,
    source: str = "apple",
) -> None:
    """The one idempotent workout write both dialects (Apple and Android)
    share: a stable exporter id wins, otherwise (member, start, activity).
    A resend without route data never erases a trace already stored."""
    if external_id:
        row = db.scalar(
            select(Workout).where(
                Workout.user_id == user.id, Workout.external_id == external_id
            )
        )
    else:
        row = db.scalar(
            select(Workout).where(
                Workout.user_id == user.id,
                Workout.started_at == started_at,
                Workout.activity == activity,
            )
        )
    if row is None:
        row = Workout(family_id=user.family_id, user_id=user.id, external_id=external_id)
        db.add(row)
    row.activity = activity
    row.started_at = started_at
    row.ended_at = ended_at
    row.duration_s = duration_s
    row.kcal = kcal
    row.distance_m = distance_m
    row.avg_hr = avg_hr
    row.source = source
    if route is not None:
        row.route = route


def _import_workouts(db: Session, user: User, workouts) -> tuple[int, set[dt.date]]:
    """Returns (workouts touched, the days they started on) — the days feed
    the routine auto-complete pass."""
    touched = 0
    days: set[dt.date] = set()
    for entry in (workouts if isinstance(workouts, list) else [])[:MAX_WORKOUTS]:
        if not isinstance(entry, dict):
            continue
        started = _parse_when(entry.get("start"))
        activity = entry.get("name")
        if started is None or not isinstance(activity, str) or not activity.strip():
            continue
        external = entry.get("id") if isinstance(entry.get("id"), str) else None
        heart = entry.get("heartRate")
        route = _parse_route(entry.get("route"))
        _upsert_workout(
            db,
            user,
            external_id=external[:64] if external else None,
            activity=activity.strip()[:80],
            started_at=started,
            ended_at=_parse_when(entry.get("end")),
            duration_s=_qty(entry.get("duration")),
            kcal=_qty(entry.get("activeEnergyBurned")),
            distance_m=_distance_m(entry.get("distance")),
            avg_hr=_qty(heart.get("avg")) if isinstance(heart, dict) else None,
            route=route,
        )
        touched += 1
        days.add(started.date())
    return touched, days


def _auto_complete_routines(db: Session, user: User, days: set[dt.date]) -> int:
    """Check off this member's opted-in routines on days a workout landed.

    Any workout counts — the opt-in on the routine is the whole contract, the
    server never matches workout names to titles. Only the syncing member's
    own slot is filled, only on days the routine actually occurs, and an
    existing row (done, pending, or cancelled) is never touched, so re-sent
    windows and deliberate taps both stay authoritative."""
    if not days:
        return 0
    routines = db.scalars(
        select(Item)
        .where(
            Item.family_id == user.family_id,
            Item.kind == ItemKind.routine,
            Item.workout_auto_complete.is_(True),
        )
        .options(selectinload(Item.assignees))
    ).all()
    mine = [
        r
        for r in routines
        if (user.id in {a.id for a in r.assignees}) or (not r.assignees and r.owner_id == user.id)
    ]
    if not mine:
        return 0
    existing = {
        (item_id, day)
        for item_id, day in db.execute(
            select(Completion.item_id, Completion.date_for).where(
                Completion.item_id.in_([r.id for r in mine]),
                Completion.user_id == user.id,
                Completion.date_for.in_(days),
            )
        )
    }
    done = 0
    for routine in mine:
        for day in days:
            if (routine.id, day) in existing:
                continue
            if not occurs_on(
                routine.repeat_type,
                routine.repeat_days,
                routine.repeat_interval,
                routine.repeat_anchor,
                routine.repeat_month_day,
                day,
            ):
                continue
            db.add(Completion(item_id=routine.id, user_id=user.id, date_for=day))
            done += 1
    return done


@router.post("/ingest/health", response_model=IngestResultOut)
async def ingest_health(
    request: Request,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    # Token first, body second: taking the raw Request (rather than a body
    # parameter, which FastAPI would read and parse before the handler runs)
    # means a garbage token is 401'd without ever buffering the payload. The
    # body-size middleware bounds what a valid token may send. The heavy
    # import work stays in the threadpool, like a plain def handler.
    user = await run_in_threadpool(_ingest_user, db, authorization)
    try:
        payload = json.loads(await request.body())
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Body is not valid JSON")
    if not isinstance(payload, dict):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Body must be a JSON object")
    return await run_in_threadpool(_ingest_import, db, user, payload)


def _ingest_import(db: Session, user: User, payload: dict) -> IngestResultOut:
    family = db.get(Family, user.family_id)
    local_today = family_now(dt.datetime.now(), family.timezone if family else None).date()
    seen_before = _todays_workout_ids(db, user, local_today)
    if HC_INGEST_ENABLED and hc_webhook.looks_like(payload):
        # The Android dialect (HC Webhook / Health Connect); same token, same
        # idempotent writes, times converted onto the family's clock.
        days, workouts, workout_days = hc_webhook.import_payload(
            db, user, payload, _upsert_daily, _upsert_workout, _upsert_intraday
        )
    else:
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        days = _import_metrics(db, user, data.get("metrics"))
        workouts, workout_days = _import_workouts(db, user, data.get("workouts"))
    routines = _auto_complete_routines(db, user, workout_days)
    db.commit()
    _award_workout_crumbs(db, user, workout_days)
    _push_new_workouts(db, user, local_today, seen_before)
    return IngestResultOut(days=days, workouts=workouts, routines_completed=routines)


def _todays_workout_ids(db: Session, user: User, day: dt.date) -> set[int]:
    return set(
        db.scalars(
            select(Workout.id).where(
                Workout.user_id == user.id,
                Workout.started_at >= dt.datetime.combine(day, dt.time.min),
                Workout.started_at <= dt.datetime.combine(day, dt.time.max),
            )
        )
    )


def _push_new_workouts(db: Session, user: User, day: dt.date, seen_before: set[int]) -> None:
    """Tell the household when a member finishes a real workout: only rows
    this very sync CREATED, only today's (catch-up syncs of past days stay
    silent), only 15+ minutes. Insert-only detection means a re-sent window
    never re-pings. A push failure never fails the sync."""
    from app import inbox, push

    try:
        fresh = [
            w
            for w in db.scalars(
                select(Workout).where(
                    Workout.id.in_(_todays_workout_ids(db, user, day) - seen_before)
                )
            )
            if (w.duration_s or 0) >= crumbs.WORKOUT_MIN_SECONDS
        ]
        if not fresh:
            return
        first_name = user.display_name.split()[0]
        adults = [
            m
            for m in db.scalars(
                select(User).where(User.family_id == user.family_id, User.id != user.id)
            )
            if not m.is_minor
        ]
        payloads = [
            {
                "title": f"{first_name} completed a workout",
                "body": f"{workout.activity} · {round((workout.duration_s or 0) / 60)} min",
                "tag": f"workout-{workout.id}",
                "url": "/",
            }
            for workout in fresh
        ]
        # Inbox first, committed before the push leg, and regardless of
        # whether push is configured — history is not an interruption.
        for payload in payloads:
            for member in adults:
                inbox.record(
                    db, member.id, member.family_id, "workout",
                    payload["title"], payload["body"],
                )
        db.commit()
        if push.enabled():
            for payload in payloads:
                for member in adults:
                    if push.wants(member, "workouts"):
                        push.send_to_user(db, member.id, payload)
    except Exception:
        db.rollback()
        log.exception("workout push failed (the sync itself landed)")


def _award_workout_crumbs(db: Session, user: User, workout_days: set[dt.date]) -> None:
    """One +3 per day that has a real (15+ minute) imported workout. Catch-up
    syncs pay for the historical days they carry — the runs happened — and
    the ledger key keeps every re-send from paying twice."""
    for day in workout_days:
        qualifying = db.scalar(
            select(Workout.id)
            .where(
                Workout.user_id == user.id,
                Workout.started_at >= dt.datetime.combine(day, dt.time.min),
                Workout.started_at <= dt.datetime.combine(day, dt.time.max),
                Workout.duration_s >= crumbs.WORKOUT_MIN_SECONDS,
            )
            .limit(1)
        )
        if qualifying is not None:
            crumbs.award(
                db, user, "workout", crumbs.WORKOUT_CRUMBS, f"workout:{day.isoformat()}", day
            )


# ---- the Fitness tab -------------------------------------------------------------

# The ring targets a member starts on: the widely recommended daily numbers
# (10,000 steps and the 150-minutes-a-week guideline's 30 a day). A member's
# own goal_* column, when set, replaces one of these.
DEFAULT_GOALS = {"steps": 10000, "active_kcal": 500, "exercise_minutes": 30}


def _goals_out(user: User) -> FitnessGoalsOut:
    return FitnessGoalsOut(
        steps=user.goal_steps or DEFAULT_GOALS["steps"],
        active_kcal=user.goal_active_kcal or DEFAULT_GOALS["active_kcal"],
        exercise_minutes=user.goal_exercise_min or DEFAULT_GOALS["exercise_minutes"],
    )


def _days_out(
    db: Session, user: User, start: dt.date, end: dt.date
) -> list[FitnessWeekDayOut]:
    """Every day in [start, end] with all four metrics; missing days stay
    None so the charts can show the gap honestly."""
    rows = db.scalars(
        select(FitnessDaily).where(
            FitnessDaily.user_id == user.id,
            FitnessDaily.date_for.between(start, end),
        )
    ).all()
    by_day_metric = {(r.date_for, r.metric): r.value for r in rows}
    return [
        FitnessWeekDayOut(
            date_for=day,
            steps=by_day_metric.get((day, "steps")),
            active_kcal=by_day_metric.get((day, "active_kcal")),
            exercise_minutes=by_day_metric.get((day, "exercise_minutes")),
            resting_hr=by_day_metric.get((day, "resting_hr")),
            distance=by_day_metric.get((day, "distance")),
        )
        for day in (start + dt.timedelta(days=i) for i in range((end - start).days + 1))
    ]


@router.get("/me/fitness", response_model=FitnessOut)
def my_fitness(
    date: dt.date | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_adult),
):
    today = date or dt.date.today()
    week_start = today - dt.timedelta(days=6)
    token = db.get(IngestToken, user.id)

    week = _days_out(db, user, week_start, today)

    workouts = db.scalars(
        select(Workout)
        .where(Workout.user_id == user.id, Workout.started_at >= dt.datetime.combine(week_start, dt.time.min))
        .order_by(Workout.started_at.desc())
        .limit(20)
    ).all()

    today_out = week[-1]
    return FitnessOut(
        connected=token is not None,
        last_sync=token.last_used_at if token else None,
        today=FitnessDayOut(
            steps=today_out.steps,
            active_kcal=today_out.active_kcal,
            exercise_minutes=today_out.exercise_minutes,
            resting_hr=today_out.resting_hr,
            distance=today_out.distance,
        ),
        week=week,
        workouts=[WorkoutOut.model_validate(w) for w in workouts],
        goals=_goals_out(user),
        count_watch_kcal=user.count_watch_kcal,
    )


@router.get("/me/fitness/history", response_model=FitnessHistoryOut)
def my_fitness_history(
    date: dt.date | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_adult),
):
    """The trailing 30 days, for the per-metric detail views. The client
    computes its own averages and bests from the raw days."""
    today = date or dt.date.today()
    return FitnessHistoryOut(days=_days_out(db, user, today - dt.timedelta(days=29), today))


@router.get("/me/fitness/intraday", response_model=FitnessIntradayOut)
def my_fitness_intraday(
    date: dt.date | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_adult),
):
    """One day's metrics bucketed to the hour, for the time-of-day charts.
    Each series is 24 slots (12AM..11PM), None where nothing landed."""
    day = date or dt.date.today()
    rows = db.scalars(
        select(FitnessIntraday).where(
            FitnessIntraday.user_id == user.id, FitnessIntraday.date_for == day
        )
    ).all()

    def series(metric: str) -> list[float | None]:
        out: list[float | None] = [None] * 24
        for r in rows:
            if r.metric == metric and 0 <= r.hour < 24:
                out[r.hour] = r.value
        return out

    return FitnessIntradayOut(
        steps=series("steps"),
        active_kcal=series("active_kcal"),
        distance=series("distance"),
        hr=series("hr"),
    )


@router.patch("/me/fitness/goals", response_model=FitnessGoalsOut)
def update_fitness_goals(
    payload: FitnessGoalsIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_adult),
):
    """Set (or, with an explicit null, reset) any of the member's ring goals.
    Fields not sent stay as they are."""
    sent = payload.model_dump(exclude_unset=True)
    if "steps" in sent:
        user.goal_steps = sent["steps"]
    if "active_kcal" in sent:
        user.goal_active_kcal = sent["active_kcal"]
    if "exercise_minutes" in sent:
        user.goal_exercise_min = sent["exercise_minutes"]
    db.commit()
    return _goals_out(user)


@router.put("/me/fitness/watch-kcal", response_model=WatchKcalIn)
def set_watch_kcal(
    payload: WatchKcalIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_adult),
):
    """Opt in (or out of) counting the watch's workout calories toward the
    day's food budget — deliberate workouts only, never the all-day active
    total. The diary takes the larger of the workout sum and the manual
    exercise log for a day, never the sum of both."""
    user.count_watch_kcal = payload.enabled
    db.commit()
    return WatchKcalIn(enabled=user.count_watch_kcal)


@router.post("/me/fitness/token", response_model=IngestTokenOut)
def mint_ingest_token(db: Session = Depends(get_db), user: User = Depends(require_adult)):
    """A fresh key for this member's exporter app, replacing any old one.
    The plaintext appears in this response and never again."""
    token = secrets.token_urlsafe(32)
    row = db.get(IngestToken, user.id)
    if row is None:
        row = IngestToken(user_id=user.id, token_hash=hash_code(token))
        db.add(row)
    else:
        row.token_hash = hash_code(token)
        row.last_used_at = None
    db.commit()
    return IngestTokenOut(token=token, path="/api/ingest/health")


@router.delete("/me/fitness/token", status_code=status.HTTP_204_NO_CONTENT)
def revoke_ingest_token(db: Session = Depends(get_db), user: User = Depends(require_adult)):
    row = db.get(IngestToken, user.id)
    if row is not None:
        db.delete(row)
        db.commit()
