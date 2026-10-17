from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.discovery.policy import WINDOW_DAYS, LeaderboardWindow, ranking_score

_NOW = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)


def _hours_ago(hours: float) -> datetime:
    return _NOW - timedelta(hours=hours)


def test_velocity_beats_raw_total():
    # 20 votes in the first hour outranks 30 spread across the whole day.
    early = ranking_score(20, _hours_ago(1), _NOW)
    spread = ranking_score(30, _hours_ago(24), _NOW)
    assert early > spread


def test_score_decays_with_age():
    fresh = ranking_score(10, _hours_ago(1), _NOW)
    stale = ranking_score(10, _hours_ago(5), _NOW)
    assert fresh > stale


def test_zero_votes_scores_zero():
    assert ranking_score(0, _hours_ago(1), _NOW) == 0.0


def test_unknown_launch_time_falls_back_to_raw_count():
    assert ranking_score(7, None, _NOW) == 7.0


def test_future_launch_time_is_clamped():
    # A launch "in the future" is treated as age zero, never negative-inflated.
    assert ranking_score(5, _hours_ago(-3), _NOW) == ranking_score(5, _NOW, _NOW)


def test_window_lookback_mapping():
    assert WINDOW_DAYS[LeaderboardWindow.WEEK] == 7
    assert WINDOW_DAYS[LeaderboardWindow.MONTH] == 30
    assert WINDOW_DAYS[LeaderboardWindow.ALL_TIME] is None
