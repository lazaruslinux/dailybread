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

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.db import SessionLocal
from app.models import (
    DigestLog,
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


# ---- the morning digest ---------------------------------------------------------


def _is_recipient(item: Item, user: User) -> bool:
    """Same rule as _recipients, answered for one member without a query:
    assignees when named; otherwise the owner for a private card, the whole
    household for a family-visible (or ownerless) one."""
    if item.assignees:
        return any(a.id == user.id for a in item.assignees)
    if item.visibility == Visibility.family or item.owner_id is None:
        return True
    return item.owner_id == user.id


def _claim_digest(db: Session, user_id: int, day: dt.date) -> bool:
    """Claim the (member, day) pair; False means someone else already has."""
    db.add(DigestLog(user_id=user_id, date_for=day))
    try:
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False


def _todays_board(db: Session, user: User, now: dt.datetime) -> tuple[int, Item | None]:
    """One member's OPEN items today: routines landing today, cards dated
    today, and undated anytime tasks — completed ones excluded, exactly like
    the board. Returns (count, the next undone timed card still ahead)."""
    from app.routers.items import _completions_by_item, _occurs

    today = now.date()
    items = (
        db.scalars(
            select(Item)
            .options(selectinload(Item.assignees))
            .where(
                Item.family_id == user.family_id,
                or_(
                    Item.repeat_type.is_not(None),
                    Item.date_for == today,
                    Item.date_for.is_(None),
                ),
            )
        )
        .unique()
        .all()
    )
    mine = [
        item
        for item in items
        if _is_recipient(item, user)
        and (item.kind != ItemKind.routine or _occurs(item, today))
    ]
    comps = _completions_by_item(db, mine)

    open_items: list[Item] = []
    for item in mine:
        rows = comps[item.id]
        if item.kind == ItemKind.routine:
            # Their own occurrence; a pending mark counts as already acted.
            acted = any(uid == user.id and day == today for uid, day, _pend in rows)
        elif item.date_for is not None:
            # Dated one-shots are done once anyone checked them, whatever day.
            acted = any(not pend for _uid, _day, pend in rows)
        else:
            # Undated tasks: any check (today = done, earlier = archived).
            acted = any(not pend for _uid, _day, pend in rows)
        if not acted:
            open_items.append(item)

    upcoming = [
        item
        for item in open_items
        if item.time_of_day is not None and not item.all_day and item.time_of_day > now.time()
    ]
    next_item = min(upcoming, key=lambda i: i.time_of_day) if upcoming else None
    return len(open_items), next_item


def digest_tick(now: dt.datetime) -> int:
    """Once each morning, per adult with a subscribed device: a personal
    good-morning summary of their day. Runs from digest_hour on, so a server
    that was down at 7 still greets people when it comes back — but never
    after noon, when "good morning" has stopped being one. Empty boards stay
    quiet (the claim still lands, so a card added at 9 doesn't ping at 9:01)."""
    if not (settings.digest_hour <= now.hour < 12):
        return 0

    today = now.date()
    sent = 0
    with SessionLocal() as db:
        subscribed = (
            db.scalars(
                select(User)
                .join(PushSubscription, PushSubscription.user_id == User.id)
                .distinct()
            )
            .unique()
            .all()
        )
        handled = set(
            db.scalars(select(DigestLog.user_id).where(DigestLog.date_for == today))
        )
        due = [
            u
            for u in subscribed
            # Kid mode: minors get no digest — the board is the parents' to run.
            if u.id not in handled and u.family_id is not None and not u.is_minor
        ]

        for user in due:
            if not _claim_digest(db, user.id, today):
                continue
            count, next_item = _todays_board(db, user, now)
            if count == 0:
                continue
            body = f"{count} item{'' if count == 1 else 's'} on today's board."
            if next_item is not None:
                body += f" Next up: {next_item.title} at {_fmt(next_item.time_of_day)}."
            body += " Tap to review. Read your daily verses."
            payload = {
                "title": f"Good morning, {user.display_name.split()[0]}.",
                "body": body,
                "tag": f"digest-{today.isoformat()}",
                "url": "/",
            }
            sent += send_to_user(db, user.id, payload)
    return sent


async def reminder_loop() -> None:
    log.info(
        "push reminders on: checking every %ss, %s-minute lead, digest at %s:00",
        TICK_SECONDS,
        settings.reminder_lead_minutes,
        settings.digest_hour,
    )
    while True:
        try:
            n = await asyncio.to_thread(reminder_tick, dt.datetime.now())
            n += await asyncio.to_thread(digest_tick, dt.datetime.now())
            if n:
                log.info("pushes sent: %s", n)
        except Exception:  # never let one bad tick kill the loop
            log.exception("reminder tick failed")
        await asyncio.sleep(TICK_SECONDS)
