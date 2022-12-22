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

from tasktools.threaded_pool.base import BaseThreadedTaskPool

T = TypeVar("T")


class BlockingThreadedTaskPool(AbstractContextManager):
    """Task pool running asynchronous tasks in another dedicated thread.

    `name` will be used as the thread's name.

    `size` can be a positive integer to limit the number of tasks concurrently running.

    `timeout` can be set to define a maximum running time for each time after which it will be cancelled.
    Note: this excludes time spent waiting to be started (time spent in the buffer).

    `context_manager` can be optional context managers that will be entered when the loop has started
    and exited before the loop is stopped.
    """

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
        return self._base.create_task(coro)

    def run(self, coro: Awaitable[T]) -> T:
        future = self._base.create_task(coro)
        return future.result()
