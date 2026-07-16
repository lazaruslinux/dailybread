"""The Inbox: a member's persistent notification history.

record() is the whole write side. It runs at the same call sites that build
pushes (plus crumb earns), but deliberately ignores push prefs and whether
push is configured at all — prefs decide what interrupts a phone, the inbox
is the history of what happened. It never commits: each caller decides the
transaction boundary, so an event that fails to save never leaves a phantom
inbox row, and crumbs.award() can fold the entry into its own atomic commit.
"""

import logging

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import InboxEntry, User

log = logging.getLogger("dailybread.inbox")

# Newest rows kept per member, pruned on insert. Count-based, not age-based:
# the storage bound is hard and a quiet member's inbox never empties out.
MAX_PER_USER = 300


def record(
    db: Session,
    user_id: int,
    family_id: int,
    kind: str,
    title: str,
    body: str = "",
) -> None:
    """Add one entry for one member and prune them past MAX_PER_USER."""
    keep = (
        select(InboxEntry.id)
        .where(InboxEntry.user_id == user_id)
        .order_by(InboxEntry.id.desc())
        .limit(MAX_PER_USER - 1)
    )
    db.execute(
        delete(InboxEntry).where(
            InboxEntry.user_id == user_id, InboxEntry.id.not_in(keep)
        )
    )
    db.add(
        InboxEntry(
            family_id=family_id,
            user_id=user_id,
            kind=kind,
            title=title[:200],
            body=body[:200],
        )
    )


def other_adults(db: Session, actor: User) -> list[User]:
    """The actor's family adults minus the actor: the default audience for a
    family-activity line. Board-item lines are the exception — they use
    _board_change_recipients so private cards never leak to the other parent."""
    return [
        u
        for u in db.scalars(select(User).where(User.family_id == actor.family_id))
        if not u.is_minor and u.id != actor.id
    ]


def record_all(
    db: Session, users: list[User], kind: str, title: str, body: str = ""
) -> None:
    """One record() per recipient then a SINGLE commit, always AFTER the
    endpoint's own commit. Wrapped so an inbox write can never fail the action
    it describes or leave a phantom row: a failure rolls the inbox insert back
    and logs, the already-committed action stands."""
    if not users:
        return
    try:
        for u in users:
            record(db, u.id, u.family_id, kind, title, body)
        db.commit()
    except Exception:
        db.rollback()
        log.exception("inbox write failed (the action itself is saved)")
