"""Durable, Redis-backed queue of background jobs.

Jobs are stored in a sorted set scored by their availability time, so a delayed
retry (provider backoff) is simply an entry with a future score. This keeps
work-in-flight durable across process restarts while leaving Redis
non-authoritative: the queue is a unit-of-work buffer, never source-of-truth
data. When Redis is unreachable the queue degrades to an in-process list so
callers never fail because of the queue itself.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, cast

from src.integrations.redis import get_redis_client
from src.tasks.base import DEAD_LETTER_KEY, QUEUE_KEY


@dataclass
class QueuedTask:
    """One enqueued job: its name, JSON payload, attempt, and due time."""

    job_name: str
    payload: dict
    attempt: int = 1
    job_id: str = ""
    available_at: float = 0.0
    last_error: str | None = None

    def to_json(self) -> str:
        return json.dumps(
            {
                "job_id": self.job_id,
                "job_name": self.job_name,
                "payload": self.payload,
                "attempt": self.attempt,
                "available_at": self.available_at,
                "last_error": self.last_error,
            },
            default=str,
        )

    @classmethod
    def from_json(cls, raw: str) -> QueuedTask:
        data = json.loads(raw)
        return cls(
            job_name=data["job_name"],
            payload=data.get("payload") or {},
            attempt=int(data.get("attempt", 1)),
            job_id=data.get("job_id") or uuid.uuid4().hex,
            available_at=float(data.get("available_at", 0.0)),
            last_error=data.get("last_error"),
        )


class TaskQueue:
    """Persist enqueued jobs and pop those that are due, in availability order."""

    def __init__(self, client: Any | None = None) -> None:
        self._client = client
        self._memory: list[QueuedTask] = []
        self._dead_memory: list[QueuedTask] = []

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = get_redis_client()
        return self._client

    def enqueue(
        self,
        job_name: str,
        payload: dict,
        *,
        delay_seconds: float = 0.0,
        attempt: int = 1,
        job_id: str | None = None,
    ) -> str:
        task = QueuedTask(
            job_name=job_name,
            payload=payload,
            attempt=attempt,
            job_id=job_id or uuid.uuid4().hex,
            available_at=time.time() + max(delay_seconds, 0.0),
        )
        try:
            self.client.zadd(QUEUE_KEY, {task.to_json(): task.available_at})
        except Exception:
            self._memory.append(task)
        return task.job_id

    def dequeue_due(self, *, now: float | None = None, limit: int = 50) -> list[QueuedTask]:
        cutoff = now if now is not None else time.time()
        try:
            raw = cast(
                "list[str]",
                self.client.zrangebyscore(QUEUE_KEY, "-inf", cutoff, start=0, num=limit),
            )
            if raw:
                self.client.zrem(QUEUE_KEY, *raw)
            return [QueuedTask.from_json(item) for item in raw]
        except Exception:
            due = [task for task in self._memory if task.available_at <= cutoff][:limit]
            for task in due:
                self._memory.remove(task)
            return due

    def size(self) -> int:
        try:
            return int(self.client.zcard(QUEUE_KEY))
        except Exception:
            return len(self._memory)

    def dead_letter(self, task: QueuedTask, error: str) -> None:
        task.last_error = error
        try:
            self.client.lpush(DEAD_LETTER_KEY, task.to_json())
        except Exception:
            self._dead_memory.append(task)

    def dead_letter_size(self) -> int:
        try:
            return int(self.client.llen(DEAD_LETTER_KEY))
        except Exception:
            return len(self._dead_memory)
