from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from src.tasks.queue import TaskQueue
from src.tasks.registry import get_job

_queue = TaskQueue()


def enqueue_job(job_name: str, payload: dict, *, delay_seconds: float = 0.0) -> dict:
    """Persist a job on the durable queue and return its handle.

    Enqueueing never runs the job inline — the ``TaskExecutor`` drains the queue
    and applies retry/backoff. ``delay_seconds`` schedules a future availability
    (used by delivery backoff).
    """
    job_id = _queue.enqueue(job_name, payload, delay_seconds=delay_seconds)
    return {
        "job_id": job_id,
        "job_name": job_name,
        "payload": payload,
        "status": "queued",
    }


def run_job(job_name: str, payload: dict, *, db: Session | None = None) -> Any:
    """Resolve a registered job by name and run it synchronously.

    ``db`` is forwarded to jobs that need a session (the job's own signature
    decides whether it accepts one). Raises ``KeyError`` for unknown names.
    Used by tests and by the executor; normal callers enqueue by name.
    """
    job = get_job(job_name)
    if job is None:
        raise KeyError(f"Unknown job: {job_name}")
    if db is not None:
        return job(db, **payload)
    return job(**payload)
