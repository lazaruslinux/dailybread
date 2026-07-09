"""Web Push: sending, plus the background loop that reminds about timed cards.

A reminder goes to the people a card is FOR (its assignees; the owner when
nobody is assigned; the whole household for an unassigned family-visible
card), a little before the card's start time. reminder_log keeps a row per
card per day so a restart or a racing tick never double-sends.

Card times are wall-clock local times, so the loop compares them against the
server's local clock - in a container that means setting the TZ environment
variable to the household's timezone.
"""

import asyncio
import datetime as dt
import json
import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.db import SessionLocal
from app.models import (
    Item,
    ItemKind,
    PushSubscription,
    ReminderLog,
    User,
    Visibility,
)

log = logging.getLogger("dailybread.push")

TICK_SECONDS = 60


def enabled() -> bool:
    return bool(settings.vapid_public_key and settings.vapid_private_key)


def _fmt(t: dt.time) -> str:
    suffix = "AM" if t.hour < 12 else "PM"
    hour = t.hour % 12 or 12
    return f"{hour}:{t.minute:02d} {suffix}"


def send_to_subscription(db: Session, sub: PushSubscription, payload: dict) -> bool:
    """Push one payload to one device. Returns True when the push service
    accepted it. A 404/410 means the browser dropped the subscription
    (uninstalled, permissions revoked) - the row is deleted on the spot."""
    # Imported here so the app (and its tests) work without push configured.
    from pywebpush import WebPushException, webpush

    try:
        webpush(
            subscription_info={
                "endpoint": sub.endpoint,
                "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
            },
            data=json.dumps(payload),
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": settings.vapid_subject},
            ttl=15 * 60,  # a reminder that can't be delivered soon is stale
        )
        return True
    except WebPushException as e:
        if e.response is not None and e.response.status_code in (404, 410):
            log.info("push endpoint gone, dropping subscription %s", sub.id)
            db.delete(sub)
            db.commit()
        else:
            log.warning("push send failed: %s", e)
        return False


def send_to_user(db: Session, user_id: int, payload: dict) -> int:
    subs = db.scalars(
        select(PushSubscription).where(PushSubscription.user_id == user_id)
    ).all()
    return sum(1 for sub in subs if send_to_subscription(db, sub, payload))


def _recipients(db: Session, item: Item) -> list[User]:
    """Who a card's reminder is for."""
    if item.assignees:
        return list(item.assignees)
    if item.visibility == Visibility.family or item.owner_id is None:
        return db.scalars(select(User).where(User.family_id == item.family_id)).all()
    owner = db.get(User, item.owner_id)
    return [owner] if owner is not None else []


def _already_reminded(db: Session, item: Item, day: dt.date) -> bool:
    """Claim the (item, day) pair; True means someone else already has."""
    db.add(ReminderLog(item_id=item.id, date_for=day))
    try:
        db.commit()
        return False
    except IntegrityError:
        db.rollback()
        return True


def reminder_tick(now: dt.datetime) -> int:
    """One pass: remind about timed cards starting within the lead window.
    Returns how many pushes the push services accepted (for the logs)."""
    # Local import for the same reason as in send_to_subscription: the items
    # router pulls in the whole schema graph, which tests may stub around.
    from app.routers.items import _completions_by_item, _occurs, _routine_participants

    today = now.date()
    window_start = now.time()
    window_end = (now + dt.timedelta(minutes=settings.reminder_lead_minutes)).time()
    if window_end < window_start:
        window_end = dt.time(23, 59, 59)  # clamp at midnight; next day's tick picks up the rest

    sent = 0
    with SessionLocal() as db:
        items = (
            db.scalars(
                select(Item)
                .options(selectinload(Item.assignees))
                .where(
                    Item.time_of_day.is_not(None),
                    Item.time_of_day > window_start,
                    Item.time_of_day <= window_end,
                    (Item.date_for == today) | (Item.repeat_type.is_not(None)),
                )
            )
            .unique()
            .all()
        )
        due = [
            item
            for item in items
            if item.kind != ItemKind.routine or _occurs(item, today)
        ]
        if not due:
            return 0
        comps = _completions_by_item(db, due)

        for item in due:
            rows = comps[item.id]
            # A pending row (kid mode: awaiting parent approval) counts as
            # "already acted" here — the kid did the thing; don't nag them.
            if item.kind == ItemKind.routine:
                done_today = {
                    uid for uid, day, _pending in rows if day == today and uid is not None
                }
                people = [p for p in _routine_participants(db, item) if p.id not in done_today]
            else:
                if rows:  # dated one-shots count as done regardless of the day checked
                    continue
                people = _recipients(db, item)
            if not people:
                continue
            if _already_reminded(db, item, today):
                continue

            when = _fmt(item.time_of_day)
            if item.end_time:
                when += f" – {_fmt(item.end_time)}"
            payload = {
                "title": item.title,
                "body": f"Coming up at {when}" if not item.end_time else f"Coming up: {when}",
                "tag": f"item-{item.id}-{today.isoformat()}",
                "url": "/",
            }
            for person in people:
                sent += send_to_user(db, person.id, payload)
    return sent


async def reminder_loop() -> None:
    log.info(
        "push reminders on: checking every %ss, %s-minute lead",
        TICK_SECONDS,
        settings.reminder_lead_minutes,
    )
    while True:
        try:
            n = await asyncio.to_thread(reminder_tick, dt.datetime.now())
            if n:
                log.info("reminders sent: %s", n)
        except Exception:  # never let one bad tick kill the loop
            log.exception("reminder tick failed")
        await asyncio.sleep(TICK_SECONDS)
