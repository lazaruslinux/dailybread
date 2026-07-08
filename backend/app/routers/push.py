from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import push
from app.config import settings
from app.db import get_db
from app.deps import require_family
from app.models import PushSubscription, User
from app.schemas import PushKeyOut, PushSubscriptionIn, PushTestOut, PushUnsubscribeIn

router = APIRouter(prefix="/push", tags=["push"])


def _require_configured() -> None:
    # Push is optional per install; without VAPID keys the feature is simply off.
    if not push.enabled():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Push is not configured on this server"
        )


@router.get("/key", response_model=PushKeyOut)
def vapid_key(user: User = Depends(require_family)):
    """The server's public VAPID key, which the browser needs to subscribe."""
    _require_configured()
    return PushKeyOut(key=settings.vapid_public_key)


@router.put("/subscription", status_code=status.HTTP_204_NO_CONTENT)
def subscribe(
    data: PushSubscriptionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_family),
):
    """Register this device for the signed-in member. A device that changes
    hands (family tablet, someone else logs in) re-registers its endpoint
    under the new member rather than duplicating it."""
    _require_configured()
    sub = db.scalar(
        select(PushSubscription).where(PushSubscription.endpoint == data.endpoint)
    )
    if sub is None:
        sub = PushSubscription(endpoint=data.endpoint)
        db.add(sub)
    sub.user_id = user.id
    sub.family_id = user.family_id
    sub.p256dh = data.keys.p256dh
    sub.auth = data.keys.auth
    db.commit()


@router.delete("/subscription", status_code=status.HTTP_204_NO_CONTENT)
def unsubscribe(
    data: PushUnsubscribeIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_family),
):
    """Drop this device. Scoped to the member's own rows, so nobody can guess
    away another member's subscriptions."""
    sub = db.scalar(
        select(PushSubscription).where(
            PushSubscription.endpoint == data.endpoint,
            PushSubscription.user_id == user.id,
        )
    )
    if sub is not None:
        db.delete(sub)
        db.commit()


@router.post("/test", response_model=PushTestOut)
def send_test(
    db: Session = Depends(get_db),
    user: User = Depends(require_family),
):
    """Ring the member's own devices, so enabling can be checked on the spot."""
    _require_configured()
    sent = push.send_to_user(
        db,
        user.id,
        {
            "title": "dailybread",
            "body": "Notifications are working on this device.",
            "tag": "test",
            "url": "/",
        },
    )
    return PushTestOut(sent=sent)
