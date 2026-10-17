"""Explicit exponential-backoff policy for background jobs.

Kept separate from the queue and executor so the retry schedule is a single,
tunable source of truth and can be unit-tested in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetryPolicy:
    """Retry/backoff/dead-letter policy shared by the executor and delivery jobs.

    Attempts are 1-based: the first run is attempt 1. ``should_retry`` returns
    ``None``-safe guidance for whether another attempt is allowed, and
    ``delay_for`` returns the exponential delay before retrying a given attempt.
    """

    max_attempts: int = 3
    base_delay_seconds: float = 5.0
    max_delay_seconds: float = 300.0

    def should_retry(self, attempt: int) -> bool:
        """True when ``attempt`` (the one that just failed) may be retried."""
        return attempt < self.max_attempts

    def delay_for(self, attempt: int) -> float:
        """Delay in seconds before retrying; exponential, capped at the max."""
        delay = self.base_delay_seconds * (2 ** max(attempt - 1, 0))
        return min(delay, self.max_delay_seconds)
