"""Web Push: sending, plus the background loop that reminds about timed cards.

A reminder goes to the people a card is FOR (its assignees; the owner when
nobody is assigned; the whole household for an unassigned family-visible
card), a little before the card's start time. reminder_log keeps a row per
card per day so a restart or a racing tick never double-sends.

Card times are wall-clock local times. The loop compares them against each
FAMILY's clock: families.timezone when set, otherwise the server's own local
clock (the TZ environment variable) - so households in different timezones
on one install each get their reminders and digests at their own hours.
"""

import asyncio
import datetime as dt
import json
import logging

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.clock import family_now
from app.config import settings
from app.db import SessionLocal
from app.models import (
    DigestLog,
    Family,
    IngestToken,
    Item,
    ItemKind,
    PushSubscription,
    ReminderLog,
    User,
    Visibility,
)

log = logging.getLogger("dailybread.push")

TICK_SECONDS = 60

# How late a timed reminder may still fire when the server was down through
# its lead window. A flat bound for both appointment_lead_minutes and
# reminder_lead_minutes: the point is only that a card's start slipped past
# during downtime, not the length of its runway.
CATCHUP_MINUTES = 30

# Every notification kind a member can turn off individually. Board updates
# and meal picks share one switch ("family"): they're all "someone changed
# something you can see", and ten-plus toggles is where people stop reading.
# "verse" is additionally gated on verses_enabled — no verses, no streak to
# protect.
PREF_KINDS = frozenset(
    {
        "timed",  # the lead-time ping before anything timed (Before Events)
        "overdue",  # a nudge 24 hours after something goes past due
        "morning",  # the morning summary
        "evening",  # the evening check-in
        "family",  # board updates + dinner lock-ins
        "workouts",  # a family member finished a workout
        "approvals",  # a kid's check-off awaiting a parent (Kid Tasks)
        "sync",  # health sync went quiet (Health Sync Timeout)
        "verse",  # verse streak about to end (Streak Reminders)
        "village",  # anything crossing the family wall: event invites, RSVPs,
        # changes, call-offs — a separate consent surface from "family",
        # which only ever means your own household's board.
        "household",  # an invited household finished setting up (server owner only)
    }
)


def wants(user: User, kind: str) -> bool:
    """Whether this member takes this kind of push. Only OFF is ever stored,
    so a missing key (or a NULL column) reads as on — see User.push_prefs."""
    return bool((user.push_prefs or {}).get(kind, True))


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
            log.warning(
                "push send failed for user %s (sub %s, tag %s): %s",
                sub.user_id,
                sub.id,
                payload.get("tag"),
                e,
            )
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


def _family_clocks(db: Session, now: dt.datetime) -> dict[int, dt.datetime]:
    """Every family's local "now", from the server's."""
    return {
        family_id: family_now(now, tz)
        for family_id, tz in db.execute(select(Family.id, Family.timezone))
    }


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

    sent = 0
    with SessionLocal() as db:
        clocks = _family_clocks(db, now)
        # Near midnight, "today" can differ between families; fetch dated
        # cards for every family's calendar date and settle per item below.
        candidate_days = {local.date() for local in clocks.values()} or {now.date()}
        items = (
            db.scalars(
                select(Item)
                .options(selectinload(Item.assignees))
                .where(
                    Item.time_of_day.is_not(None),
                    Item.date_for.in_(candidate_days) | Item.repeat_type.is_not(None),
                )
            )
            .unique()
            .all()
        )
        # Each card is judged on ITS family's clock: inside the lead window,
        # and (for anything recurring) on a day its schedule lands on. The
        # lead depends on the kind: appointments get an hour of runway (shoes
        # on, drive somewhere), everything else the short heads-up.
        due: list[tuple[Item, dt.date, bool]] = []
        for item in items:
            local = clocks.get(item.family_id, now)
            today = local.date()
            lead = (
                settings.appointment_lead_minutes
                if item.kind == ItemKind.appointment
                else settings.reminder_lead_minutes
            )
            window_start = local.time()
            window_end = (local + dt.timedelta(minutes=lead)).time()
            if window_end < window_start:
                window_end = dt.time(23, 59, 59)  # clamp at midnight; the next day picks up the rest
            if window_start < item.time_of_day <= window_end:
                late = False
            else:
                # Catch-up: start slipped past while the server was down. Fire up to
                # CATCHUP_MINUTES late, never after the event has ended, never across
                # midnight (yesterday's miss is the past-due pass's problem).
                catch_start = (local - dt.timedelta(minutes=CATCHUP_MINUTES)).time()
                if catch_start > window_start:  # subtraction crossed midnight
                    catch_start = dt.time(0, 0)
                if not (catch_start < item.time_of_day <= window_start):
                    continue
                if item.end_time is not None and item.end_time <= window_start:
                    continue  # already over; a late ping is noise
                late = True
            if item.repeat_type is None:
                if item.date_for != today:
                    continue
            elif not _occurs(item, today):
                continue
            due.append((item, today, late))
        if not due:
            return 0
        comps = _completions_by_item(db, [item for item, _, _ in due])

        for item, today, late in due:
            rows = comps[item.id]
            # A pending row (kid mode: awaiting parent approval) counts as
            # "already acted" here — the kid did the thing; don't nag them.
            if item.kind == ItemKind.routine:
                done_today = {
                    uid for uid, day, _pending, _canc in rows if day == today and uid is not None
                }
                people = [p for p in _routine_participants(db, item) if p.id not in done_today]
            elif item.date_for is not None:
                if rows:  # done or cancelled, whichever day it was marked
                    continue
                people = _recipients(db, item)
            else:
                # A repeating appointment: this occurrence is resolved only by
                # a mark (done or cancelled) on today itself.
                if any(day == today for _uid, day, _pending, _canc in rows):
                    continue
                people = _recipients(db, item)
            # Kid mode: no notifications for minors at all — their day is the
            # parents' to run, and the phone in question is a parent's anyway.
            people = [p for p in people if not p.is_minor and wants(p, "timed")]
            if not people:
                continue
            if _already_reminded(db, item, today):
                continue

            when = _fmt(item.time_of_day)
            if item.end_time:
                when += f" – {_fmt(item.end_time)}"
            if late:
                body = f"Started at {_fmt(item.time_of_day)}"
            else:
                body = f"Coming up at {when}" if not item.end_time else f"Coming up: {when}"
            payload = {
                "title": item.title,
                "body": body,
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


def _claim_digest(db: Session, user_id: int, day: dt.date, kind: str) -> bool:
    """Claim the (member, day, push) triple; False means someone already has."""
    db.add(DigestLog(user_id=user_id, date_for=day, kind=kind))
    try:
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False


def _due_users(
    db: Session, kind: str, clocks: dict[int, dt.datetime], now: dt.datetime
) -> list[tuple[User, dt.datetime]]:
    """Adults with a subscribed device whose `kind` push hasn't been handled
    on their family's current date, each paired with their family's local
    "now". Minors never receive anything scheduled — the board is the
    parents' to run."""
    # No SQL DISTINCT here: since push_prefs, a User row carries a json
    # column, and Postgres json has no equality operator to dedupe on.
    # .unique() collapses the join's duplicates by ORM identity instead.
    subscribed = (
        db.scalars(select(User).join(PushSubscription, PushSubscription.user_id == User.id))
        .unique()
        .all()
    )
    candidate_days = {local.date() for local in clocks.values()} or {now.date()}
    handled = {
        (user_id, day)
        for user_id, day in db.execute(
            select(DigestLog.user_id, DigestLog.date_for).where(
                DigestLog.date_for.in_(candidate_days), DigestLog.kind == kind
            )
        )
    }
    due: list[tuple[User, dt.datetime]] = []
    for u in subscribed:
        if u.family_id is None or u.is_minor:
            continue
        local = clocks.get(u.family_id, now)
        if (u.id, local.date()) in handled:
            continue
        due.append((u, local))
    return due


def _has_passed(item: Item, now: dt.datetime) -> bool:
    """A timed appointment or activity whose end time has gone by. There is
    nothing left to do about it, so it stops counting as open — unlike a task
    or a routine, which wait for someone. A span is judged on its LAST day; an
    all-day or untimed entry has no moment to be past."""
    if item.kind not in (ItemKind.appointment, ItemKind.activity):
        return False
    if item.all_day or item.end_time is None:
        return False
    last_day = item.end_date or item.date_for
    if last_day is not None and last_day > now.date():
        return False
    return item.end_time <= now.time()


def _open_today(db: Session, user: User, now: dt.datetime) -> list[Item]:
    """One member's OPEN items today: routines landing today, cards dated
    today (a multi-day card on every day it covers), and undated anytime
    tasks — completed ones excluded, exactly like the board, and finished
    appointments and activities with them."""
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
                    and_(
                        Item.date_for <= today,
                        func.coalesce(Item.end_date, Item.date_for) >= today,
                    ),
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
        # Recurring cards (routines, repeating appointments) count only on
        # days their schedule lands on.
        and (item.repeat_type is None or _occurs(item, today))
    ]
    comps = _completions_by_item(db, mine)

    open_items: list[Item] = []
    for item in mine:
        rows = comps[item.id]
        if item.kind == ItemKind.routine:
            # Their own occurrence; a pending mark counts as already acted.
            acted = any(uid == user.id and day == today for uid, day, _pend, _canc in rows)
        elif item.date_for is not None:
            # Dated one-shots are resolved once anyone checked or cancelled
            # them, whatever day.
            acted = any(not pend or canc for _uid, _day, pend, canc in rows)
        elif item.repeat_type is not None:
            # A repeating appointment: only a mark on today's occurrence counts.
            acted = any(day == today and (not pend or canc) for _uid, day, pend, canc in rows)
        else:
            # Undated tasks: any check (today = done, earlier = archived).
            acted = any(not pend for _uid, _day, pend, _canc in rows)
        if not acted and not _has_passed(item, now):
            open_items.append(item)
    return open_items


def _todays_board(db: Session, user: User, now: dt.datetime) -> tuple[int, Item | None]:
    """The morning digest's numbers: how many open items today, and the next
    undone timed card still ahead."""
    open_items = _open_today(db, user, now)
    upcoming = [
        item
        for item in open_items
        if item.time_of_day is not None
        and not item.all_day
        and item.time_of_day > now.time()
        # A span's start time belonged to the day it began; on a later day of
        # the run it reads like an all-day card and is nobody's "next up".
        and not (item.date_for is not None and item.date_for < now.date())
    ]
    next_item = min(upcoming, key=lambda i: i.time_of_day) if upcoming else None
    return len(open_items), next_item


def _past_due_pass(db: Session, clocks: dict[int, dt.datetime], now: dt.datetime) -> int:
    """One nudge, 24 hours after a dated card's moment passed with nobody
    marking it: "Past due: Call the plumber". TASKS only — a task is the one
    kind still waiting on someone, while an appointment or activity has simply
    been and gone and a routine comes round again. A multi-day card is judged on
    its LAST day — a trip isn't late while it's still running. Claimed on
    (item, the day AFTER that last day) via ReminderLog, which can't collide:
    a dated card only ever claims its own start day for the before-hand
    reminder. An alert more than a day stale (a long server outage, or the
    feature arriving over an existing backlog) claims quietly instead of
    dogpiling old cards."""
    from app.routers.items import _completions_by_item

    sent = 0
    candidate_days = {local.date() - dt.timedelta(days=1) for local in clocks.values()}
    items = (
        db.scalars(
            select(Item)
            .options(selectinload(Item.assignees))
            .where(
                Item.kind == ItemKind.task,
                Item.repeat_type.is_(None),
                func.coalesce(Item.end_date, Item.date_for).in_(candidate_days),
                # A shared-event copy can't be acted on by its family (only the
                # host drives it), so it must never nag them as "past due". The
                # organizer's own source still nags the host family.
                Item.village_event_id.is_(None),
            )
        )
        .unique()
        .all()
    )
    if not items:
        return 0
    comps = _completions_by_item(db, items)
    for item in items:
        local = clocks.get(item.family_id, now)
        last_day = item.end_date or item.date_for
        # The moment it came due: a single day's start time, but a span isn't
        # finished until its LAST day's END time — a trip ending Sunday at 4 PM
        # nags Monday at 4, not Monday at the hour it set off on Friday.
        moment = item.time_of_day
        if last_day != item.date_for and item.end_time is not None:
            moment = item.end_time
        due_at = dt.datetime.combine(
            last_day, moment if moment and not item.all_day else dt.time(23, 59)
        )
        alert_at = due_at + dt.timedelta(hours=24)
        if local < alert_at:
            continue
        if comps[item.id]:  # done or cancelled, whenever it was marked
            continue
        if _already_reminded(db, item, last_day + dt.timedelta(days=1)):
            continue
        if local - alert_at > dt.timedelta(hours=24):
            continue  # claimed quietly: too stale to nag about now
        when = "yesterday"
        if moment and not item.all_day:
            when += f" at {_fmt(moment)}"
        people = [
            p for p in _recipients(db, item) if not p.is_minor and wants(p, "overdue")
        ]
        payload = {
            "title": f"Past due: {item.title}",
            "body": f"Was due {when} and it's still open.",
            "tag": f"pastdue-{item.id}",
            "url": "/",
        }
        for person in people:
            sent += send_to_user(db, person.id, payload)
    return sent


def digest_tick(now: dt.datetime) -> int:
    """The day's scheduled pushes, each once per adult with a subscribed
    device, each within a window so a server that was down at the slot still
    catches up while the message makes sense — and never later.

    morning (digest_hour → noon): a personal summary of the day's board.
    Alongside it, "sync went quiet" for members whose health import stalled.
    evening (evening_hour → 22:00): "How was your day?" for every adult —
    the day's sign-off, pointing at mood, status, and journal. Alongside it,
    the verse-streak-at-risk nudge for opted-in readers.
    past-due: not an hour window — a per-item nudge 24 hours after a dated
    card's moment passed unmarked.

    Empty boards stay quiet, but still claim their row, so a card added at
    9:01 doesn't ring a belated good-morning. A turned-off preference is
    checked after the claim for the same reason: flipping a kind back on
    mid-window must not fire a stale push.

    Every window and date is the FAMILY's, not the server's: a household
    three timezones over gets its good-morning at its own 7am."""
    sent = 0
    with SessionLocal() as db:
        clocks = _family_clocks(db, now)
        for user, local in _due_users(db, "morning", clocks, now):
            if settings.digest_hour <= local.hour < 12:
                today = local.date()
                if not _claim_digest(db, user.id, today, "morning"):
                    continue
                if not wants(user, "morning"):
                    continue
                count, next_item = _todays_board(db, user, local)
                if count == 0:
                    continue
                body = f"{count} item{'' if count == 1 else 's'} on today's board."
                if next_item is not None:
                    body += f" Next up: {next_item.title} at {_fmt(next_item.time_of_day)}."
                body += " Tap to review & read your Daily Bread!"
                sent += send_to_user(
                    db,
                    user.id,
                    {
                        "title": f"Good morning, {user.display_name.split()[0]}!",
                        "body": body,
                        "tag": f"digest-{today.isoformat()}",
                        "url": "/",
                    },
                )

        for user, local in _due_users(db, "evening", clocks, now):
            if settings.evening_hour <= local.hour < 22:
                today = local.date()
                if not _claim_digest(db, user.id, today, "evening"):
                    continue
                if not wants(user, "evening"):
                    continue
                sent += send_to_user(
                    db,
                    user.id,
                    {
                        "title": "Evening check-in",
                        "body": "How was your day?",
                        "tag": f"evening-{today.isoformat()}",
                        "url": "/",
                    },
                )

        sent += _past_due_pass(db, clocks, now)
        sent += _sync_quiet_pass(db, clocks, now)
        sent += _verse_pass(db, clocks, now)
    return sent


def _sync_quiet_pass(db: Session, clocks: dict[int, dt.datetime], now: dt.datetime) -> int:
    """Tell a member their phone's health sync stalled — the rings just look
    wrong until someone notices otherwise. Morning window, and at most one
    nudge a week: the claim row is written only when a nudge actually goes
    out, and any 'sync' row in the last seven days keeps things quiet."""
    sent = 0
    now_utc = dt.datetime.now(dt.timezone.utc)
    cutoff = now_utc - dt.timedelta(hours=settings.sync_stale_hours)
    for user, local in _due_users(db, "sync", clocks, now):
        if settings.digest_hour <= local.hour < 12:
            today = local.date()
            if not wants(user, "sync"):
                continue
            token = db.get(IngestToken, user.id)
            if token is None:
                continue
            last = token.last_used_at or token.created_at
            if last.tzinfo is None:  # SQLite hands tz-aware columns back naive
                last = last.replace(tzinfo=dt.timezone.utc)
            if last > cutoff:
                continue
            recently_told = db.scalar(
                select(DigestLog.id)
                .where(
                    DigestLog.user_id == user.id,
                    DigestLog.kind == "sync",
                    DigestLog.date_for > today - dt.timedelta(days=7),
                )
                .limit(1)
            )
            if recently_told is not None:
                continue
            if not _claim_digest(db, user.id, today, "sync"):
                continue
            days = max((now_utc - last).days, 2)
            sent += send_to_user(
                db,
                user.id,
                {
                    "title": "Health sync has gone quiet",
                    "body": (
                        f"No health data from your phone in {days} days."
                        " Open your sync app and check its automation."
                    ),
                    "tag": f"sync-{today.isoformat()}",
                    "url": "/",
                },
            )
    return sent


def _verse_pass(db: Session, clocks: dict[int, dt.datetime], now: dt.datetime) -> int:
    """An evening word to opted-in readers with a real streak (2+ days) who
    haven't finished today's verses. An invitation, not a guilt trip — and a
    phone already past midnight that checked off "tomorrow" counts as read,
    exactly like the streak itself (see verses.streaks_for)."""
    from sqlalchemy import func

    from app.models import VerseCheck
    from app.routers.verses import VERSES_PER_DAY, streaks_for

    sent = 0
    for user, local in _due_users(db, "verse", clocks, now):
        if settings.evening_hour <= local.hour < 22:
            today = local.date()
            if not _claim_digest(db, user.id, today, "verse"):
                continue
            if not user.verses_enabled or not wants(user, "verse"):
                continue
            read_already = db.execute(
                select(VerseCheck.date_for)
                .where(VerseCheck.user_id == user.id, VerseCheck.date_for >= today)
                .group_by(VerseCheck.date_for)
                .having(func.count() >= VERSES_PER_DAY)
            ).first()
            if read_already is not None:
                continue
            streak = streaks_for(db, [user.id], today).get(user.id, 0)
            if streak < 2:
                continue
            sent += send_to_user(
                db,
                user.id,
                {
                    "title": "Tonight's reading",
                    "body": f"Your {streak}-day verse streak ends at midnight.",
                    "tag": f"verse-{today.isoformat()}",
                    "url": "/",
                },
            )
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
