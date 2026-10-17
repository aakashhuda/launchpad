from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from src.notifications.models import NotificationEventType
from src.notifications.service import NotificationService
from src.products import crud
from src.products.service import FounderExportService, ProductLaunchService
from src.tasks.registry import register_job


def _coerce_date(value: date | str | None, *, default: date) -> date:
    if value is None:
        return default
    if isinstance(value, str):
        return date.fromisoformat(value)
    return value


@register_job("products.activate_daily_launches")
def activate_daily_launches(db: Session, on_date: date | str | None = None) -> list[int]:
    """Activate every launch scheduled to arrive on ``on_date`` (default: today).

    Wraps the idempotent ``ProductLaunchService.activate`` seam: already-live
    launches are skipped by the service, cancelled launches are never selected.
    Each activated launch notifies its founder that the product is live.
    """
    target = _coerce_date(on_date, default=datetime.now(timezone.utc).date())
    service = ProductLaunchService(db)
    notifications = NotificationService(db)
    activated: list[int] = []
    for product_id in crud.list_scheduled_product_ids_for_date(db, target):
        service.activate(product_id)
        product = crud.get_product(db, product_id)
        if product is not None:
            notifications.emit(
                recipient_profile_id=product.profile_id,
                event_type=NotificationEventType.LAUNCH_ACTIVATED,
                payload={"product_id": product.id, "product_name": product.name},
            )
        activated.append(product_id)
    db.commit()
    return activated


@register_job("products.send_launch_reminders")
def send_launch_reminders(db: Session, on_date: date | str | None = None) -> list[int]:
    """Remind founders whose product launches on ``on_date`` (default: tomorrow).

    Only still-``scheduled`` launches are selected, so cancelled launches are
    never reminded.
    """
    target = _coerce_date(on_date, default=datetime.now(timezone.utc).date() + timedelta(days=1))
    notifications = NotificationService(db)
    reminded: list[int] = []
    for product_id in crud.list_scheduled_product_ids_for_date(db, target):
        product = crud.get_product(db, product_id)
        if product is None:
            continue
        notifications.emit(
            recipient_profile_id=product.profile_id,
            event_type=NotificationEventType.LAUNCH_REMINDER,
            payload={
                "product_id": product.id,
                "product_name": product.name,
                "launch_date": target.isoformat(),
            },
        )
        reminded.append(product_id)
    db.commit()
    return reminded


@register_job("products.generate_founder_export")
def generate_founder_export(db: Session, export_id: int) -> None:
    """Build a founder's product export artifact and notify on completion."""
    FounderExportService(db).generate(export_id)
