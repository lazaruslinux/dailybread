"""The Inbox: a member's persistent notification history.

record() is the whole write side. It runs at the same call sites that build
pushes (plus crumb earns), but deliberately ignores push prefs and whether
push is configured at all — prefs decide what interrupts a phone, the inbox
is the history of what happened. It never commits: each caller decides the
transaction boundary, so an event that fails to save never leaves a phantom
inbox row, and crumbs.award() can fold the entry into its own atomic commit.
"""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import InboxEntry

# Newest rows kept per member, pruned on insert. Count-based, not age-based:
# the storage bound is hard and a quiet member's inbox never empties out.
MAX_PER_USER = 100


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
