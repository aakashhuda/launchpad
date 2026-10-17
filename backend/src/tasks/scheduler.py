from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from src.tasks.registry import get_job


def enqueue_job(job_name: str, payload: dict) -> dict:
    return {"job_name": job_name, "payload": payload, "status": "queued"}


def run_job(job_name: str, payload: dict, *, db: Session | None = None) -> Any:
    """Resolve a registered job by name and run it synchronously.

    ``db`` is forwarded to jobs that need a session (the job's own signature
    decides whether it accepts one). Raises ``KeyError`` for unknown names.
    """
    job = get_job(job_name)
    if job is None:
        raise KeyError(f"Unknown job: {job_name}")
    if db is not None:
        return job(db, **payload)
    return job(**payload)
