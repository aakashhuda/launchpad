"""In-process job registry.

Domains register their concrete jobs here by string name; the task layer
resolves names to callables without importing domain modules. Durable queue,
retry, and backoff are Phase 6 — this is the minimal dispatch seam.
"""

from __future__ import annotations

from collections.abc import Callable

JobCallable = Callable[..., object]

_JOBS: dict[str, JobCallable] = {}


def register_job(name: str) -> Callable[[JobCallable], JobCallable]:
    def _decorator(fn: JobCallable) -> JobCallable:
        _JOBS[name] = fn
        return fn

    return _decorator


def get_job(name: str) -> JobCallable | None:
    return _JOBS.get(name)


def registered_job_names() -> frozenset[str]:
    return frozenset(_JOBS)
