from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from src.discovery.service import SnapshotService
from src.tasks.registry import register_job


@register_job("discovery.freeze_daily_snapshots")
def freeze_daily_snapshots(db: Session, on_date: date | None = None) -> list[date]:
    """Freeze the closed day's ranking into an immutable snapshot.

    Defaults to yesterday. Freezing is idempotent: an already-frozen day returns
    an empty list and is left untouched.
    """
    target = on_date or (datetime.now(timezone.utc).date() - timedelta(days=1))
    frozen = SnapshotService(db).freeze(target)
    return [target] if frozen is not None else []
