"""Best-effort JSON cache over Redis.

Cache reads/writes never raise: a missing or unavailable Redis simply degrades
to no caching, keeping Redis non-authoritative for source-of-truth data.
"""

from __future__ import annotations

import json
from typing import Any, cast

from src.integrations.redis import get_redis_client


def get_cached_json(key: str) -> Any | None:
    try:
        raw = cast("str | None", get_redis_client().get(key))
    except Exception:
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def set_cached_json(key: str, value: Any, *, ttl_seconds: int) -> None:
    try:
        get_redis_client().set(key, json.dumps(value), ex=ttl_seconds)
    except Exception:
        return
