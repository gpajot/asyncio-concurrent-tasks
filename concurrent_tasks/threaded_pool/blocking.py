from __future__ import annotations

from concurrent import futures
from contextlib import AbstractContextManager
from typing import (
    AsyncContextManager,
    Awaitable,
    ContextManager,
    Optional,
    TypeVar,
    Union,
)

from concurrent_tasks.threaded_pool.base import BaseThreadedTaskPool

T = TypeVar("T")


class BlockingThreadedTaskPool(AbstractContextManager):
    """Task pool running asynchronous tasks in another dedicated thread."""

    def __init__(
        self,
        name: Optional[str] = None,
        size: int = 0,
        timeout: Optional[float] = None,
        context_manager: Optional[Union[ContextManager, AsyncContextManager]] = None,
    ):
        self._base = BaseThreadedTaskPool(name, size, timeout, context_manager)

    def __enter__(self) -> "BlockingThreadedTaskPool":
        self._base.start()
        self._base.post_start().result()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self._base.pre_stop(exc_type, exc_val, exc_tb).result()
        self._base.stop()

    def start(self) -> None:
        self.__enter__()

    def stop(self) -> None:
        self.__exit__(None, None, None)

    def create_task(self, coro: Awaitable[T]) -> futures.Future[T]:
        """Create a task, not waiting for it to complete."""
        return self._base.create_task(coro)

    def run(self, coro: Awaitable[T]) -> T:
        """Create a task and wait for completion."""
        future = self._base.create_task(coro)
        return future.result()
