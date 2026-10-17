from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from src.discovery import crud
from src.discovery.service import RankingService, SnapshotService
from src.notifications import crud as notifications_crud
from src.notifications.models import NotificationEventType
from src.notifications.service import NotificationService
from src.tasks.registry import register_job


def _coerce_date(value: date | str | None, *, default: date) -> date:
    if value is None:
        return default
    if isinstance(value, str):
        return date.fromisoformat(value)
    return value


@register_job("discovery.freeze_daily_snapshots")
def freeze_daily_snapshots(db: Session, on_date: date | str | None = None) -> list[date]:
    """Freeze the closed day's ranking into an immutable snapshot.

    Defaults to yesterday. Freezing is idempotent: an already-frozen day returns
    an empty list and is left untouched.
    """
    target = _coerce_date(on_date, default=datetime.now(timezone.utc).date() - timedelta(days=1))
    frozen = SnapshotService(db).freeze(target)
    return [target] if frozen is not None else []


@register_job("discovery.send_daily_top_five")
def send_daily_top_five(db: Session, on_date: date | str | None = None) -> int:
    """Notify opted-in members of the previous day's top five launches.

    Returns the number of members notified. Preference gating happens in
    ``emit``, so a member with ``daily_top_five_enabled`` off gets the in-app
    record but no email.
    """
    target = _coerce_date(on_date, default=datetime.now(timezone.utc).date() - timedelta(days=1))
    ranked = RankingService(db).for_date(target, limit=5, offset=0)
    items = [
        {
            "rank": item.rank,
            "product_id": item.product_id,
            "name": item.name,
            "vote_count": item.vote_count,
        }
        for item in ranked
    ]
    notifications = NotificationService(db)
    recipients = notifications_crud.list_profiles_with_flag(db, "daily_top_five_enabled")
    for profile_id in recipients:
        notifications.emit(
            recipient_profile_id=profile_id,
            event_type=NotificationEventType.RANKING_DAILY_TOP_FIVE,
            payload={"date": target.isoformat(), "items": items},
        )
    db.commit()
    return len(recipients)


@register_job("discovery.send_weekly_best")
def send_weekly_best(db: Session, on_date: date | str | None = None) -> int:
    """Notify opted-in members of the best launches of the past week."""
    today = _coerce_date(on_date, default=datetime.now(timezone.utc).date())
    since = today - timedelta(days=6)
    rows = crud.list_ranked_products_since(db, since=since, today=today, limit=5)
    items = [
        {
            "rank": index + 1,
            "product_id": product.id,
            "name": product.name,
            "vote_count": int(vote_count),
        }
        for index, (product, vote_count) in enumerate(rows)
    ]
    notifications = NotificationService(db)
    recipients = notifications_crud.list_profiles_with_flag(db, "weekly_best_enabled")
    for profile_id in recipients:
        notifications.emit(
            recipient_profile_id=profile_id,
            event_type=NotificationEventType.RANKING_WEEKLY_BEST,
            payload={"week_ending": today.isoformat(), "items": items},
        )
    db.commit()
    return len(recipients)
