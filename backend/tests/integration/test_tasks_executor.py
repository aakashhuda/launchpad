from __future__ import annotations

from src.tasks.executor import TaskExecutor
from src.tasks.queue import TaskQueue
from src.tasks.registry import register_job
from src.tasks.retry import RetryPolicy


class _NoRedis:
    """A client whose every call fails, forcing the queue's in-memory fallback."""

    def __getattr__(self, name: str):
        raise RuntimeError("redis unavailable")


def _memory_queue() -> TaskQueue:
    return TaskQueue(client=_NoRedis())


def test_executor_runs_successful_job_and_empties_queue():
    state = {"ran": 0}

    @register_job("test.executor_success")
    def _job(db=None):
        state["ran"] += 1
        return "ok"

    queue = _memory_queue()
    queue.enqueue("test.executor_success", {})
    assert queue.size() == 1

    results = TaskExecutor(queue).run_pending()

    assert results == ["ok"]
    assert state["ran"] == 1
    assert queue.size() == 0
    assert queue.dead_letter_size() == 0


def test_executor_retries_then_dead_letters_failures():
    state = {"ran": 0}

    @register_job("test.executor_failure")
    def _job(db=None):
        state["ran"] += 1
        raise RuntimeError("boom")

    queue = _memory_queue()
    queue.enqueue("test.executor_failure", {})
    executor = TaskExecutor(queue, policy=RetryPolicy(max_attempts=2, base_delay_seconds=0.0))

    executor.run_pending()  # attempt 1 fails -> re-queued with backoff
    executor.run_pending()  # attempt 2 fails -> dead-lettered

    assert state["ran"] == 2
    assert queue.size() == 0
    assert queue.dead_letter_size() == 1


def test_executor_dead_letters_unknown_jobs():
    queue = _memory_queue()
    queue.enqueue("test.unknown_job", {})

    TaskExecutor(queue).run_pending()

    assert queue.dead_letter_size() == 1
    assert queue.size() == 0
