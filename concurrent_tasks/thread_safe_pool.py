import asyncio
import threading
from concurrent import futures
from dataclasses import dataclass
from functools import partial
from typing import Awaitable, Generic, Optional, Set, TypeVar

from typing_extensions import Self  # 3.11

T = TypeVar("T")


@dataclass
class _Task(Generic[T]):
    awaitable: Awaitable[T]
    future: futures.Future[T]


class ThreadSafeTaskPool:
    """Task pool running asynchronous tasks that can be scheduled from other threads."""

    def __init__(
        self,
        size: int = 0,
        timeout: Optional[float] = None,
    ):
        self._size = size
        self.timeout = timeout

        # Keep a reference to this thread's loop to be able to start tasks from other loops.
        self._loop = asyncio.get_event_loop()
        # Use a buffer to limit time spent in thread safe operations.
        # Also used to buffer tasks if a max size is set.
        self._buffer: asyncio.Queue[_Task] = asyncio.Queue()
        # Reentrant lock to lock buffer and event access between threads.
        self._rlock = threading.RLock()
        # Currently running tasks.
        self._tasks: Set[asyncio.Task] = set()
        self._stopped = True

    async def __aenter__(self) -> Self:
        self._stopped = False
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        with self._rlock:
            self._stopped = True
        await self._drain_pool()

    async def stop(self):
        await self.__aexit__(None, None, None)

    @property
    def size(self) -> int:
        return self._size

    @size.setter
    def size(self, size: int) -> None:
        if size > self._size or not size and self._size:
            self._loop.call_soon_threadsafe(self._start_tasks)
        self._size = size

    def create_task(self, coro: Awaitable[T]) -> futures.Future[T]:
        """Create a new task in the pool. Response will be received through the future."""
        future: futures.Future[T] = futures.Future()
        with self._rlock:
            if self._stopped:
                raise RuntimeError(f"{self.__class__.__name__} is not running")
            self._buffer.put_nowait(_Task(coro, future))
        self._loop.call_soon_threadsafe(self._start_tasks)
        return future

    async def run(self, coro: Awaitable[T]) -> T:
        return await asyncio.wrap_future(self.create_task(coro))

    def _start_tasks(self) -> None:
        """Start more tasks if the buffer isn't empty and size permits."""
        while not self._size or len(self._tasks) < self._size:
            task: Optional[_Task] = None
            with self._rlock:
                # Check the size to avoid waiting while locking.
                if not self._buffer.empty():
                    # We are checking the size within the lock so no need to wait.
                    task = self._buffer.get_nowait()
            if task:
                self._start_task(task)
            else:
                break

    def _start_task(self, task: _Task) -> None:
        """Create and register the task."""
        if task.future.cancelled():
            # The task has been cancelled while waiting in the buffer.
            return
        _task = asyncio.create_task(
            asyncio.wait_for(task.awaitable, timeout=self.timeout),
        )
        self._tasks.add(_task)
        _task.add_done_callback(
            partial(self._done_callback, task.future),
        )

        # Cancel the task when we cancel the future to be able to stop a task manually.
        def _fut_done(_):
            if not _task.done():
                _task.cancel()

        task.future.add_done_callback(_fut_done)

    def _done_callback(self, future: futures.Future[T], task: asyncio.Task[T]) -> None:
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
        while True:
            with self._rlock:
                if self._buffer.empty():
                    break
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
