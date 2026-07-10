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
from sqlalchemy.orm import Session

from app import throttle
from app.db import get_db
from app.deps import require_adult
from app.invitecodes import hash_code
from app.models import FitnessDaily, IngestToken, User, WeightEntry, Workout
from app.schemas import (
    FitnessDayOut,
    FitnessOut,
    FitnessWeekDayOut,
    IngestResultOut,
    IngestTokenOut,
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
    for entry in metrics if isinstance(metrics, list) else []:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        unit = entry.get("units", "") if isinstance(entry.get("units"), str) else ""
        points = entry.get("data") if isinstance(entry.get("data"), list) else []

        if name == WEIGHT_METRIC:
            touched += _import_weight(db, user, points, unit)
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
    return touched


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


def _import_workouts(db: Session, user: User, workouts) -> int:
    touched = 0
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
        touched += 1
    return touched


@router.post("/ingest/health", response_model=IngestResultOut)
def ingest_health(
    payload: dict,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    user = _ingest_user(db, authorization)
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    days = _import_metrics(db, user, data.get("metrics"))
    workouts = _import_workouts(db, user, data.get("workouts"))
    db.commit()
    return IngestResultOut(days=days, workouts=workouts)


# ---- the Fitness tab -------------------------------------------------------------


@router.get("/me/fitness", response_model=FitnessOut)
def my_fitness(
    date: dt.date | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_adult),
):
    today = date or dt.date.today()
    week_start = today - dt.timedelta(days=6)
    token = db.get(IngestToken, user.id)

    rows = db.scalars(
        select(FitnessDaily).where(
            FitnessDaily.user_id == user.id,
            FitnessDaily.date_for.between(week_start, today),
        )
    ).all()
    by_day_metric = {(r.date_for, r.metric): r.value for r in rows}

    def metric(day: dt.date, name: str) -> float | None:
        return by_day_metric.get((day, name))

    workouts = db.scalars(
        select(Workout)
        .where(Workout.user_id == user.id, Workout.started_at >= dt.datetime.combine(week_start, dt.time.min))
        .order_by(Workout.started_at.desc())
        .limit(20)
    ).all()

    return FitnessOut(
        connected=token is not None,
        last_sync=token.last_used_at if token else None,
        today=FitnessDayOut(
            steps=metric(today, "steps"),
            active_kcal=metric(today, "active_kcal"),
            exercise_minutes=metric(today, "exercise_minutes"),
            resting_hr=metric(today, "resting_hr"),
        ),
        week=[
            FitnessWeekDayOut(
                date_for=day,
                steps=metric(day, "steps"),
                active_kcal=metric(day, "active_kcal"),
                exercise_minutes=metric(day, "exercise_minutes"),
                resting_hr=metric(day, "resting_hr"),
            )
            for day in (week_start + dt.timedelta(days=i) for i in range(7))
        ],
        workouts=[WorkoutOut.model_validate(w) for w in workouts],
    )


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
