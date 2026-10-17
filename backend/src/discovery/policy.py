from __future__ import annotations

import enum
from datetime import datetime

# Velocity-aware ranking. The score decays with time since launch so early
# votes count for more: twenty votes in the first hour outrank thirty spread
# across a whole day. Tune the gravity/offset here — this is the single source
# of truth for discovery scoring.
VELOCITY_GRAVITY = 1.8
VELOCITY_OFFSET_HOURS = 2.0


class LeaderboardWindow(str, enum.Enum):
    WEEK = "week"
    MONTH = "month"
    ALL_TIME = "all-time"


# Lookback in days per window; ``None`` means all-time (no lower bound).
WINDOW_DAYS: dict[LeaderboardWindow, int | None] = {
    LeaderboardWindow.WEEK: 7,
    LeaderboardWindow.MONTH: 30,
    LeaderboardWindow.ALL_TIME: None,
}


def ranking_score(vote_count: int, launched_at: datetime | None, now: datetime) -> float:
    """Velocity score: votes decayed by hours elapsed since launch.

    A product with no votes scores zero. When ``launched_at`` is unknown (e.g. a
    scheduled launch not yet activated) the raw vote count is used as a
    fallback so ranking stays deterministic.
    """
    if vote_count <= 0:
        return 0.0
    if launched_at is None:
        return float(vote_count)
    age_hours = max((now - launched_at).total_seconds() / 3600.0, 0.0)
    return vote_count / ((age_hours + VELOCITY_OFFSET_HOURS) ** VELOCITY_GRAVITY)
