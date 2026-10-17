"""Suspicious-behavior monitoring.

A rolling per-user counter (Redis-backed, ``abuse:`` prefix) records how often a
member performs a sensitive action within a window. Crossing the configured
threshold enqueues a ``staff.evaluate_abuse_signal`` review job. This is
monitoring only — it never blocks the request (that is the rate limiter's job)
and never takes automated action.
"""

from __future__ import annotations

from src.integrations.redis import get_redis_client


def note_activity(action: str, subject: str, *, window_seconds: int) -> int:
    """Increment the ``action`` counter for ``subject`` and return the new count.

    Fails closed to ``0`` when Redis is unreachable so monitoring never breaks a
    request.
    """
    key = f"abuse:{action}:{subject}"
    try:
        client = get_redis_client()
        pipe = client.pipeline()
        pipe.incr(key)
        pipe.ttl(key)
        count, ttl = pipe.execute()
        if ttl is None or int(ttl) < 0:
            client.expire(key, window_seconds)
        return int(count)
    except Exception:
        return 0


def flag_if_suspicious(action: str, *, user_id: int, threshold: int, window_seconds: int) -> bool:
    """Enqueue a staff review signal when ``user_id`` crosses ``threshold``."""
    if threshold <= 0:
        return False
    count = note_activity(action, f"user:{user_id}", window_seconds=window_seconds)
    if count < threshold:
        return False

    from src.tasks.scheduler import enqueue_job

    enqueue_job(
        "staff.evaluate_abuse_signal",
        {
            "action": action,
            "user_id": user_id,
            "count": count,
            "window_seconds": window_seconds,
        },
    )
    return True
