from collections.abc import Callable


def run_task(task: Callable[[], None]) -> None:
    task()
