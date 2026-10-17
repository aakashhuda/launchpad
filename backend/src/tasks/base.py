"""Shared constants for the background task layer.

The durable queue lives in ``src.tasks.queue``; the executor that drains it and
applies retry/backoff is ``src.tasks.executor``. Concrete domain jobs register
by string name via ``src.tasks.registry`` and are enqueued through
``src.tasks.scheduler``.
"""

from __future__ import annotations

QUEUE_KEY = "events:task_queue"
DEAD_LETTER_KEY = "events:task_dead_letter"
