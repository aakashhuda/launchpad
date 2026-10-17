"""Worker entrypoint that continuously drains the durable job queue.

Run with ``python -m src.tasks.worker`` (or under a process manager). The loop
polls the queue, runs due jobs through ``TaskExecutor``, and sleeps between
polls; because the queue is Redis-backed, work enqueued before a restart is
still picked up afterwards.
"""

from __future__ import annotations

import logging
import time

from src.core.logging import configure_logging

logger = logging.getLogger("src.tasks.worker")

POLL_INTERVAL_SECONDS = 5.0


def _register_jobs() -> None:
    # Importing the domains' jobs modules populates the in-process registry so
    # job names resolve; the model registry is imported for mapper resolution.
    import src.discovery.jobs  # noqa: F401
    import src.notifications.jobs  # noqa: F401
    import src.products.jobs  # noqa: F401
    import src.shared.registry  # noqa: F401


def main() -> None:
    from src.tasks.executor import TaskExecutor

    configure_logging()
    _register_jobs()
    executor = TaskExecutor()
    logger.info("task worker started")
    while True:
        processed = executor.run_pending()
        if processed:
            logger.info("processed %d task(s)", len(processed))
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
