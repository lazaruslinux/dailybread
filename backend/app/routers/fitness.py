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
import secrets
from collections import defaultdict

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import throttle
from app.db import get_db
from app.deps import require_adult
from app.invitecodes import hash_code
from app.models import (
    Completion,
    FitnessDaily,
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
    FitnessOut,
    FitnessWeekDayOut,
    IngestResultOut,
    IngestTokenOut,
    WatchKcalIn,
    WorkoutOut,
)

router = APIRouter(tags=["fitness"])

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

# One shared bucket for bad tokens, same reasoning as signup invites: the
# tokens are long random secrets, so every wrong guess is a fresh key and
# per-token buckets would throttle nothing.
INGEST_THROTTLE_KEY = "ingest-health"
INGEST_MAX_FAILURES = 30

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


def _distance_m(raw) -> float | None:
    qty = _qty(raw)
    if qty is None:
        return None
    unit = _units(raw).lower()
    if unit in ("km", "kilometers"):
        return qty * 1000.0
    if unit in ("mi", "miles"):
        return qty * MILE_M
    return qty  # meters, or a bare number we take at face value


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


def _upsert_daily(
    db: Session, user: User, day: dt.date, metric: str, value: float, unit: str
) -> None:
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
    row.value = round(value, 2)
    row.unit = unit


def _import_metrics(db: Session, user: User, metrics) -> int:
    touched = 0
    # Body fat rides on the day's weight entry, so its points wait until every
    # other metric (weight included) has landed — the exporter doesn't promise
    # an order within one payload.
    bodyfat_points: list = []
    for entry in metrics if isinstance(metrics, list) else []:
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
        if name not in METRIC_MAP:
            continue  # metrics we don't track yet are silently fine
        metric, combine = METRIC_MAP[name]
        by_day: dict[dt.date, list[float]] = defaultdict(list)
        for point in points:
            when = _parse_when(point.get("date")) if isinstance(point, dict) else None
            qty = _qty(point.get("qty")) if isinstance(point, dict) else None
            if when is None or qty is None:
                continue
            by_day[when.date()].append(qty)
        for day, values in by_day.items():
            value = sum(values) if combine == "sum" else sum(values) / len(values)
            _upsert_daily(db, user, day, metric, value, unit)
            touched += 1
    return touched + _import_body_fat(db, user, bodyfat_points)


def _import_weight(db: Session, user: User, points, unit: str) -> int:
    """Weigh-ins flow into the existing weight log so the calorie math picks
    them up — but only onto days with no entry yet: a deliberate in-app
    weigh-in always beats the scale sync."""
    last_by_day: dict[dt.date, tuple[dt.datetime, float]] = {}
    for point in points if isinstance(points, list) else []:
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
    for point in points:
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


def _import_workouts(db: Session, user: User, workouts) -> tuple[int, set[dt.date]]:
    """Returns (workouts touched, the days they started on) — the days feed
    the routine auto-complete pass."""
    touched = 0
    days: set[dt.date] = set()
    for entry in workouts if isinstance(workouts, list) else []:
        if not isinstance(entry, dict):
            continue
        started = _parse_when(entry.get("start"))
        activity = entry.get("name")
        if started is None or not isinstance(activity, str) or not activity.strip():
            continue
        activity = activity.strip()[:80]
        external = entry.get("id") if isinstance(entry.get("id"), str) else None
        if external:
            external = external[:64]
            row = db.scalar(
                select(Workout).where(
                    Workout.user_id == user.id, Workout.external_id == external
                )
            )
        else:
            row = db.scalar(
                select(Workout).where(
                    Workout.user_id == user.id,
                    Workout.started_at == started,
                    Workout.activity == activity,
                )
            )
        if row is None:
            row = Workout(family_id=user.family_id, user_id=user.id, external_id=external)
            db.add(row)
        row.activity = activity
        row.started_at = started
        row.ended_at = _parse_when(entry.get("end"))
        row.duration_s = _qty(entry.get("duration"))
        row.kcal = _qty(entry.get("activeEnergyBurned"))
        row.distance_m = _distance_m(entry.get("distance"))
        heart = entry.get("heartRate")
        row.avg_hr = _qty(heart.get("avg")) if isinstance(heart, dict) else None
        # A re-send without route data must not erase a trace we already have
        # (the exporter's route toggle can be flipped either way later).
        route = _parse_route(entry.get("route"))
        if route is not None:
            row.route = route
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
def ingest_health(
    payload: dict,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    user = _ingest_user(db, authorization)
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    days = _import_metrics(db, user, data.get("metrics"))
    workouts, workout_days = _import_workouts(db, user, data.get("workouts"))
    routines = _auto_complete_routines(db, user, workout_days)
    db.commit()
    return IngestResultOut(days=days, workouts=workouts, routines_completed=routines)


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
