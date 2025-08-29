import logging

from concurrent_tasks.background import BackgroundTask
from concurrent_tasks.debounce import AsyncDebouncer, Debouncer, debounce
from concurrent_tasks.exception_handler import LoopExceptionHandler
from concurrent_tasks.periodic import OnTimePeriodicTask, PeriodicTask
from concurrent_tasks.pool import TaskPool
from concurrent_tasks.restartable import RestartableTask
from concurrent_tasks.stream import RobustStream, RobustStreamReader
from concurrent_tasks.thread_safe_pool import ThreadSafeTaskPool
from concurrent_tasks.threaded_pool import (
    AsyncThreadedTaskPool,
    BlockingThreadedTaskPool,
    ThreadedPoolContextManagerWrapper,
)

logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = [
    "AsyncDebouncer",
    "AsyncThreadedTaskPool",
    "BackgroundTask",
    "BlockingThreadedTaskPool",
    "Debouncer",
    "LoopExceptionHandler",
    "OnTimePeriodicTask",
    "PeriodicTask",
    "RestartableTask",
    "RobustStream",
    "RobustStreamReader",
    "TaskPool",
    "ThreadSafeTaskPool",
    "ThreadedPoolContextManagerWrapper",
    "debounce",
]
