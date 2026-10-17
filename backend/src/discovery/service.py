from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from src.core.config import settings
from src.discovery import crud, policy
from src.discovery.models import DaySnapshot
from src.discovery.policy import LeaderboardWindow
from src.discovery.schemas import (
    DaySnapshotRead,
    LeaderboardProductRead,
    ProductSearchResult,
    RankedProductRead,
    SearchSort,
)
from src.integrations import cache
from src.products.models import Product, ProductLaunch
from src.staff.models import AuditEntityType, AuditEventType
from src.staff.service import AuditLogService
from src.topics import crud as topics_crud


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> date:
    return _utcnow().date()


def _day_close(on_date: date) -> datetime:
    """UTC midnight ending ``on_date`` — the instant a day's ranking is frozen."""
    return datetime.combine(on_date + timedelta(days=1), time.min, tzinfo=timezone.utc)


def _rank_rows(
    rows: list[tuple[Product, ProductLaunch, int]], *, now: datetime
) -> list[tuple[Product, int, float]]:
    """Score and order ``(product, launch, vote_count)`` rows, best first."""
    scored = [
        (
            product,
            int(vote_count),
            policy.ranking_score(int(vote_count), launch.launched_at, now),
        )
        for product, launch, vote_count in rows
    ]
    scored.sort(key=lambda item: (-item[2], -item[1], item[0].id))
    return scored


def _ranked_read(rank: int, product: Product, vote_count: int, score: float) -> RankedProductRead:
    return RankedProductRead(
        rank=rank,
        product_id=product.id,
        name=product.name,
        one_line_pitch=product.one_line_pitch,
        vote_count=vote_count,
        score=round(score, 6),
    )


class RankingService:
    """Live, velocity-ranked front page for the current launch day."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def today(self, *, limit: int, offset: int) -> list[RankedProductRead]:
        rows = crud.list_launches_for_date(self.db, _today())
        ranked = _rank_rows(rows, now=_utcnow())
        page = ranked[offset : offset + limit]
        return [
            _ranked_read(rank=offset + index + 1, product=product, vote_count=count, score=score)
            for index, (product, count, score) in enumerate(page)
        ]

    def for_date(self, on_date: date, *, limit: int, offset: int) -> list[RankedProductRead]:
        """Rank a specific day's launches, scored at that day's close (digests)."""
        rows = crud.list_launches_for_date(self.db, on_date, today=on_date)
        ranked = _rank_rows(rows, now=_day_close(on_date))
        page = ranked[offset : offset + limit]
        return [
            _ranked_read(rank=offset + index + 1, product=product, vote_count=count, score=score)
            for index, (product, count, score) in enumerate(page)
        ]


class LeaderboardService:
    """Per-topic leaderboards for week/month/all-time windows (Redis-cached)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def leaderboard(
        self, slug: str, window: LeaderboardWindow, *, limit: int, offset: int
    ) -> list[LeaderboardProductRead]:
        topic = topics_crud.get_topic_by_slug(self.db, slug)
        if topic is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")

        key = f"cache:discovery:leaderboard:{slug}:{window.value}:{limit}:{offset}"
        cached = cache.get_cached_json(key)
        if cached is not None:
            return [LeaderboardProductRead.model_validate(item) for item in cached]

        days = policy.WINDOW_DAYS[window]
        since = None if days is None else _today() - timedelta(days=days - 1)
        rows = crud.list_topic_launches(
            self.db, topic.id, today=_today(), since=since, limit=limit, offset=offset
        )
        results = [
            LeaderboardProductRead(
                rank=offset + index + 1,
                product_id=product.id,
                name=product.name,
                one_line_pitch=product.one_line_pitch,
                vote_count=int(vote_count),
            )
            for index, (product, _launch, vote_count) in enumerate(rows)
        ]
        cache.set_cached_json(
            key,
            [item.model_dump(mode="json") for item in results],
            ttl_seconds=settings.discovery_cache_ttl_seconds,
        )
        return results


class SearchService:
    """Full-text search over public products with topic filter and sort."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def search(
        self,
        *,
        query: str,
        topic: str | None,
        sort: SearchSort,
        limit: int,
        offset: int,
    ) -> list[ProductSearchResult]:
        topic_id: int | None = None
        if topic:
            topic_obj = topics_crud.get_topic_by_slug(self.db, topic)
            if topic_obj is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Topic not found")
            topic_id = topic_obj.id

        rows = crud.search_products(
            self.db,
            query=query,
            topic_id=topic_id,
            order_by_votes=sort == SearchSort.MOST_VOTED,
            today=_today(),
            limit=limit,
            offset=offset,
        )
        return [
            ProductSearchResult(
                product_id=product.id,
                name=product.name,
                one_line_pitch=product.one_line_pitch,
                description=product.description,
                website_url=product.website_url,
                vote_count=int(vote_count),
                created_at=product.created_at,
            )
            for product, vote_count in rows
        ]


class SnapshotService:
    """Freezes closed-day rankings into immutable snapshots and reads them back."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditLogService(db)

    def get_day(self, on_date: date) -> DaySnapshotRead:
        snapshot = crud.get_snapshot_by_date(self.db, on_date)
        if snapshot is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Day snapshot not found"
            )
        return self._read(snapshot)

    def freeze(self, on_date: date) -> DaySnapshot | None:
        """Freeze ``on_date`` once. Returns ``None`` if a snapshot already exists."""
        if crud.get_snapshot_by_date(self.db, on_date) is not None:
            return None

        rows = crud.list_launches_for_date(self.db, on_date, today=on_date)
        ranked = _rank_rows(rows, now=_day_close(on_date))
        frozen_at = _utcnow()

        snapshot = crud.create_snapshot(self.db, on_date=on_date, frozen_at=frozen_at)
        for rank, (product, vote_count, score) in enumerate(ranked, start=1):
            crud.create_snapshot_item(
                self.db,
                snapshot_id=snapshot.id,
                product_id=product.id,
                rank=rank,
                vote_count=vote_count,
                score=score,
            )
        crud.stamp_launches_frozen(self.db, on_date, frozen_at)
        self.audit.record(
            actor_profile_id=None,
            event_type=AuditEventType.SNAPSHOT_FROZEN,
            entity_type=AuditEntityType.SNAPSHOT,
            entity_id=snapshot.id,
            after_state={"launch_date": on_date.isoformat(), "items": len(ranked)},
        )
        self.db.commit()
        self.db.refresh(snapshot)
        return snapshot

    @staticmethod
    def _read(snapshot: DaySnapshot) -> DaySnapshotRead:
        return DaySnapshotRead(
            launch_date=snapshot.launch_date,
            frozen_at=snapshot.frozen_at,
            items=[
                _ranked_read(
                    rank=item.rank,
                    product=item.product,
                    vote_count=item.vote_count,
                    score=item.score,
                )
                for item in snapshot.items
            ],
        )
