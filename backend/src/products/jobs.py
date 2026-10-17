from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from src.products import crud
from src.products.service import ProductLaunchService
from src.tasks.registry import register_job


@register_job("products.activate_daily_launches")
def activate_daily_launches(db: Session, on_date: date | None = None) -> list[int]:
    """Activate every launch scheduled to arrive on ``on_date`` (default: today).

    Wraps the idempotent ``ProductLaunchService.activate`` seam: already-live
    launches are skipped by the service, cancelled launches are never selected.
    """
    target = on_date or datetime.now(timezone.utc).date()
    service = ProductLaunchService(db)
    activated: list[int] = []
    for product_id in crud.list_scheduled_product_ids_for_date(db, target):
        service.activate(product_id)
        activated.append(product_id)
    return activated
