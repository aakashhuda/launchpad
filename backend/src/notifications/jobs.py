from __future__ import annotations

from sqlalchemy.orm import Session

from src.notifications.service import NotificationService
from src.tasks.registry import register_job


@register_job("notifications.dispatch_delivery")
def dispatch_delivery(db: Session, delivery_id: int) -> None:
    """Render and send one tracked email delivery.

    Retries with backoff on provider failure and is idempotent, so re-running a
    queued dispatch never double-sends.
    """
    NotificationService(db).dispatch(delivery_id)
