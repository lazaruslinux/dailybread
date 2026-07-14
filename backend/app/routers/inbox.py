"""The Inbox read side: a member's own history, an unread count for the
badges, and a bulk read-all fired when the page opens. Everything filters on
the current member, so cross-family isolation is structural, and everything
is require_family — kids read their own Inbox (crumb earns and approval
payoffs are theirs)."""

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_family
from app.models import InboxEntry, User
from app.schemas import InboxEntryOut, InboxUnreadOut

router = APIRouter(prefix="/me/inbox", tags=["inbox"])


@router.get("", response_model=list[InboxEntryOut])
def list_inbox(
    db: Session = Depends(get_db),
    user: User = Depends(require_family),
):
    # No pagination: retention caps the table at inbox.MAX_PER_USER rows.
    return db.scalars(
        select(InboxEntry)
        .where(InboxEntry.user_id == user.id)
        .order_by(InboxEntry.created_at.desc(), InboxEntry.id.desc())
    ).all()


@router.get("/unread", response_model=InboxUnreadOut)
def unread_count(
    db: Session = Depends(get_db),
    user: User = Depends(require_family),
):
    count = db.scalar(
        select(func.count()).where(
            InboxEntry.user_id == user.id, InboxEntry.read.is_(False)
        )
    )
    return InboxUnreadOut(count=count or 0)


@router.post("/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_all_read(
    db: Session = Depends(get_db),
    user: User = Depends(require_family),
):
    db.execute(
        update(InboxEntry)
        .where(InboxEntry.user_id == user.id, InboxEntry.read.is_(False))
        .values(read=True)
    )
    db.commit()
