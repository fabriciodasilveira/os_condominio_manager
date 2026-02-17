import json

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Notification, PushSubscription

try:
    from pywebpush import WebPushException, webpush
except ImportError:  # pragma: no cover - opcional em ambiente sem dependência instalada
    WebPushException = Exception
    webpush = None


def create_notification(db: Session, user_id: int, title: str, message: str, work_order_id: int | None = None):
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        work_order_id=work_order_id,
    )
    db.add(notification)
    db.flush()
    return notification


def send_push_to_user(db: Session, user_id: int, title: str, message: str, work_order_id: int | None = None):
    if not webpush or not settings.vapid_private_key or not settings.vapid_public_key:
        return

    payload = {
        "title": title,
        "body": message,
        "workOrderId": work_order_id,
    }

    subscriptions = db.query(PushSubscription).filter(PushSubscription.user_id == user_id).all()
    for sub in subscriptions:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=json.dumps(payload),
                vapid_private_key=settings.vapid_private_key,
                vapid_claims={"sub": settings.vapid_claims_sub},
            )
        except WebPushException:
            db.delete(sub)
