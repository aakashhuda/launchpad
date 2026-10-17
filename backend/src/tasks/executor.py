"""Executor that drains the durable queue with retry/backoff and dead-lettering.

The executor owns the process boundary for background work: it pops due tasks,
resolves their job by name through ``src.tasks.registry``, runs each with a
fresh DB session, and on failure applies the shared ``RetryPolicy`` — re-queue
with backoff while attempts remain, otherwise move the task to the dead-letter
list with its error.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from src.core.database import SessionLocal
from src.tasks.queue import QueuedTask, TaskQueue
from src.tasks.registry import get_job
from src.tasks.retry import RetryPolicy

logger = logging.getLogger("src.tasks.executor")


class TaskExecutor:
    """Pops due jobs off the queue and runs them, retrying with backoff."""

    def __init__(
        self,
        queue: TaskQueue | None = None,
        *,
        policy: RetryPolicy | None = None,
        session_factory: Callable[[], Session] | None = None,
    ) -> None:
        self.queue = queue or TaskQueue()
        self.policy = policy or RetryPolicy()
        self.session_factory = session_factory or SessionLocal

    def run_pending(self, *, now: float | None = None, max_tasks: int = 50) -> list[Any]:
        """Drain up to ``max_tasks`` due jobs and return one result per task."""
        return [self._run(task) for task in self.queue.dequeue_due(now=now, limit=max_tasks)]

    def _run(self, task: QueuedTask) -> Any:
        job = get_job(task.job_name)
        if job is None:
            self.queue.dead_letter(task, f"Unknown job: {task.job_name}")
            return None

        db: Session = self.session_factory()
        try:
            result = job(db, **task.payload)
            db.commit()
            return result
        except Exception as exc:  # noqa: BLE001 - the executor is the failure boundary
            db.rollback()
            logger.exception("Job %s failed (attempt %s)", task.job_name, task.attempt)
            if self.policy.should_retry(task.attempt):
                self.queue.enqueue(
                    task.job_name,
                    task.payload,
                    delay_seconds=self.policy.delay_for(task.attempt),
                    attempt=task.attempt + 1,
                    job_id=task.job_id,
                )
            else:
                self.queue.dead_letter(task, str(exc))
            return None
        finally:
            db.close()
