from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.discovery.policy import LeaderboardWindow
from src.discovery.schemas import (
    DaySnapshotRead,
    LeaderboardProductRead,
    ProductSearchResult,
    RankedProductRead,
    SearchSort,
)
from src.discovery.service import LeaderboardService, RankingService, SearchService, SnapshotService

router = APIRouter()


@router.get("/today", response_model=list[RankedProductRead])
def read_today(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[RankedProductRead]:
    return RankingService(db).today(limit=limit, offset=offset)


@router.get("/launches/{on_date}", response_model=DaySnapshotRead)
def read_day(
    on_date: date,
    db: Session = Depends(get_db),
) -> DaySnapshotRead:
    return SnapshotService(db).get_day(on_date)


@router.get("/topics/{slug}/leaderboard", response_model=list[LeaderboardProductRead])
def read_leaderboard(
    slug: str,
    window: LeaderboardWindow = Query(LeaderboardWindow.WEEK),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[LeaderboardProductRead]:
    return LeaderboardService(db).leaderboard(slug, window, limit=limit, offset=offset)


@router.get("/products/search", response_model=list[ProductSearchResult])
def search_products(
    q: str = Query(..., min_length=1, max_length=200),
    topic: str | None = Query(None),
    sort: SearchSort = Query(SearchSort.NEWEST),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[ProductSearchResult]:
    return SearchService(db).search(query=q, topic=topic, sort=sort, limit=limit, offset=offset)
