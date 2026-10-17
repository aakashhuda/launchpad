from __future__ import annotations

import enum
from datetime import date, datetime

from pydantic import BaseModel


class SearchSort(str, enum.Enum):
    NEWEST = "newest"
    MOST_VOTED = "most_voted"


class RankedProductRead(BaseModel):
    rank: int
    product_id: int
    name: str
    one_line_pitch: str
    vote_count: int
    score: float
    featured: bool = False


class DaySnapshotRead(BaseModel):
    launch_date: date
    frozen_at: datetime
    items: list[RankedProductRead]


class LeaderboardProductRead(BaseModel):
    rank: int
    product_id: int
    name: str
    one_line_pitch: str
    vote_count: int


class ProductSearchResult(BaseModel):
    product_id: int
    name: str
    one_line_pitch: str
    description: str
    website_url: str | None
    vote_count: int
    created_at: datetime
