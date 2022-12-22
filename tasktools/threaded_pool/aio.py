from __future__ import annotations

import asyncio
from contextlib import AbstractAsyncContextManager
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


class AsyncThreadedTaskPool(AbstractAsyncContextManager):
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

    async def __aenter__(self) -> "AsyncThreadedTaskPool":
        self._base.start()
        await asyncio.wrap_future(self._base.post_start())
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await asyncio.wrap_future(self._base.pre_stop(exc_type, exc_val, exc_tb))
        self._base.stop()

    async def start(self) -> None:
        await self.__aenter__()

    async def stop(self) -> None:
        await self.__aexit__(None, None, None)

    def create_task(self, coro: Awaitable[T]) -> asyncio.Future[T]:
        return asyncio.wrap_future(self._base.create_task(coro))

    async def run(self, coro: Awaitable[T]) -> T:
        return await self.create_task(coro)
