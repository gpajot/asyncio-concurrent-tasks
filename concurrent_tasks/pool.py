import asyncio
import sys
from contextvars import Context
from dataclasses import dataclass
from functools import partial
from typing import Awaitable, Generic, Optional, Set, TypeVar

from typing_extensions import Self  # 3.11

T = TypeVar("T")


@dataclass
class _Task(Generic[T]):
    awaitable: Awaitable[T]
    future: asyncio.Future[T]
    context: Optional[Context]


class TaskPool:
    """Simple non thread safe version of ThreadSafeTaskPool."""

    def __init__(
        self,
        size: int = 0,
        timeout: Optional[float] = None,
    ):
        self._size = size
        self.timeout = timeout

        # Buffer tasks if a max size is set.
        self._buffer: asyncio.Queue[_Task] = asyncio.Queue()
        # Currently running tasks.
        self._tasks: Set[asyncio.Task] = set()
        self._stopped = True

    async def __aenter__(self) -> Self:
        self._stopped = False
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self._stopped = True
        await self._drain_pool()

    async def stop(self):
        await self.__aexit__(None, None, None)

    @property
    def size(self) -> int:
        return self._size

    @size.setter
    def size(self, size: int) -> None:
        old = self._size
        self._size = size
        if size > old or not size and old:
            self._start_tasks()

    def create_task(
        self,
        coro: Awaitable[T],
        context: Optional[Context] = None,
    ) -> asyncio.Future[T]:
        """Create a new task in the pool. Response will be received through the future."""
        future: asyncio.Future[T] = asyncio.Future()
        if self._stopped:
            raise RuntimeError(f"{self.__class__.__name__} is not running")
        task = _Task(coro, future, context)
        if self._size:
            self._buffer.put_nowait(task)
            self._start_tasks()
        else:
            self._start_task(task)
        return future

    async def run(self, coro: Awaitable[T]) -> T:
        return await self.create_task(coro)

    def _start_tasks(self) -> None:
        """Start more tasks if the buffer isn't empty and size permits."""
        while not self._buffer.empty() and (
            not self._size or len(self._tasks) < self._size
        ):
            self._start_task(self._buffer.get_nowait())

    def _start_task(self, task: _Task) -> None:
        """Create and register the task."""
        if task.future.cancelled():
            # The task has been cancelled while waiting in the buffer.
            return
        coro = asyncio.wait_for(task.awaitable, timeout=self.timeout)
        if sys.version_info >= (3, 11):
            _task = asyncio.create_task(coro, context=task.context)
        else:
            _task = asyncio.create_task(coro)

        self._tasks.add(_task)
        _task.add_done_callback(
            partial(self._done_callback, task.future),
        )

        # Cancel the task when we cancel the future to be able to stop a task manually.
        def _fut_done(_):
            if not _task.done():
                _task.cancel()

        task.future.add_done_callback(_fut_done)

    def _done_callback(self, future: asyncio.Future[T], task: asyncio.Task[T]) -> None:
        """Complete the future and start more tasks if possible."""
        if not future.cancelled():
            exc = task.exception()
            if exc is not None:
                future.set_exception(exc)
            else:
                future.set_result(task.result())
        self._tasks.discard(task)
        self._start_tasks()

    async def _drain_pool(self) -> None:
        """Drain the buffer and complete all tasks."""
        while not self._buffer.empty():
            # Wait for buffer to flush.
            await self._drain_tasks(True)
        # Wait for last tasks to complete.
        await self._drain_tasks()

    async def _drain_tasks(self, start: bool = False) -> None:
        """Complete all currently running tasks."""
        if self._tasks:
            # Exceptions should be handled by client through the future.
            await asyncio.gather(*self._tasks, return_exceptions=True)
        elif start:
            # There might be something in the buffer but no running tasks yet.
            self._start_tasks()
