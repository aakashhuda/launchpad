"""Redis-backed rate limiting for abuse-prone endpoints.

A fixed-window counter per (bucket, client) lives under a ``limits:`` key with a
window TTL. The limiter is non-authoritative and fails open: if Redis is
unreachable the request is allowed rather than blocking all traffic. Limits and
the enable flag come from ``Settings`` so they are environment-tunable, and the
whole layer can be switched off in tests.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import HTTPException, Request, status

from src.core.config import settings
from src.integrations.redis import get_redis_client


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _increment(key: str, window_seconds: int) -> tuple[int, int]:
    """Increment the window counter, returning ``(count, retry_after)``.

    Fails open by returning ``(0, 0)`` when Redis is unavailable.
    """
    try:
        client = get_redis_client()
        pipe = client.pipeline()
        pipe.incr(key)
        pipe.ttl(key)
        count, ttl = pipe.execute()
        count = int(count)
        if ttl is None or int(ttl) < 0:
            client.expire(key, window_seconds)
            ttl = window_seconds
        return count, max(int(ttl), 0)
    except Exception:
        return 0, 0


def check_rate_limit(request: Request, *, bucket: str, limit: int, window_seconds: int) -> None:
    if not settings.rate_limit_enabled or limit <= 0:
        return
    key = f"limits:{bucket}:{_client_key(request)}"
    count, retry_after = _increment(key, window_seconds)
    if count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )


def rate_limit(bucket: str, *, limit_setting: str) -> Callable[[Request], None]:
    """Dependency factory: enforce the named ``Settings`` limit for a bucket."""

    def _dependency(request: Request) -> None:
        check_rate_limit(
            request,
            bucket=bucket,
            limit=int(getattr(settings, limit_setting)),
            window_seconds=settings.rate_limit_window_seconds,
        )

    return _dependency
