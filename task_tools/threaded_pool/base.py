from __future__ import annotations

import asyncio
import threading
from concurrent import futures
from contextlib import AsyncExitStack
from dataclasses import dataclass
from functools import partial
from typing import (
    AsyncContextManager,
    Awaitable,
    ContextManager,
    Generic,
    Optional,
    Set,
    TypeVar,
    Union,
)

T = TypeVar("T")


@dataclass
class _Task(Generic[T]):
    awaitable: Awaitable[T]
    future: futures.Future[T]


class BaseThreadedTaskPool:
    """Task pool running asynchronous tasks in another dedicated thread."""

    def __init__(
        self,
        name: Optional[str] = None,
        size: int = 0,
        timeout: Optional[float] = None,
        context_manager: Optional[Union[ContextManager, AsyncContextManager]] = None,
    ):
        self._name = name

        # Pool parameters.
        self._size = size
        self._timeout = timeout

        # Context managers.
        self._stack = AsyncExitStack()
        self._context_manager = context_manager

        self._thread: Optional[threading.Thread] = None
        # Create an event loop for that thread.
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        # Set when the event loop is running.
        # Cleared when stopping to prevent receiving new tasks.
        self._initialized = threading.Event()

        # Use a buffer to limit time spent in thread safe operations.
        # Also used to buffer tasks if a max size is set.
        self._buffer: asyncio.Queue[_Task] = asyncio.Queue()
        # Reentrant lock to lock buffer and event access between threads.
        self._rlock = threading.RLock()
        # Currently running tasks.
        self._tasks: Set[asyncio.Task] = set()

    def start(self) -> None:
        """Start the thread and wait for the loop to start running."""
        if self._thread is not None:
            raise RuntimeError(f"task pool {self._name} is already running")
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(name=self._name, target=self._run_thread)
        self._thread.start()
        self._initialized.wait()

    async def _post_start(self) -> None:
        """Enter context managers in this tread's event loop."""
        if self._context_manager:
            try:
                await self._stack.enter_async_context(self._context_manager)  # type: ignore
            except (TypeError, AttributeError):
                self._stack.enter_context(self._context_manager)  # type: ignore
        self._stack.push_async_callback(self._drain_pool)

    def post_start(self) -> futures.Future:
        if not self._loop:
            raise RuntimeError(f"task pool {self._name} is not running")
        return asyncio.run_coroutine_threadsafe(self._post_start(), self._loop)

    async def _pre_stop(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context managers."""
        await self._stack.__aexit__(exc_type, exc_val, exc_tb)

    def pre_stop(self, exc_type, exc_val, exc_tb) -> futures.Future:
        if not self._loop:
            raise RuntimeError(f"task pool {self._name} is not running")
        return asyncio.run_coroutine_threadsafe(
            self._pre_stop(exc_type, exc_val, exc_tb), self._loop
        )

    def stop(self) -> None:
        """Stop the loop and thread."""
        if not self._loop or not self._thread:
            raise RuntimeError(f"task pool {self._name} is not running")
        # Stop the pool to break out of `run` method.
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join()
        self._thread = None
        self._loop = None

    def _run_thread(self) -> None:
        """Start the event loop."""
        if not self._loop:
            raise RuntimeError(f"task pool {self._name} is not running")
        asyncio.set_event_loop(self._loop)
        self._loop.call_soon(self._initialized.set)
        self._loop.run_forever()

    def create_task(self, coro: Awaitable[T]) -> futures.Future[T]:
        """Create a new task in the pool. Response will be received through the future."""
        with self._rlock:
            if not self._initialized.is_set() or not self._loop:
                raise RuntimeError(f"task pool {self._name} is not running")
            future: futures.Future[T] = futures.Future()
            self._buffer.put_nowait(_Task(coro, future))
        self._loop.call_soon_threadsafe(self._start_tasks)
        return future

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
        if not self._loop:
            raise RuntimeError(f"task pool {self._name} is not running")
        _task = self._loop.create_task(
            asyncio.wait_for(task.awaitable, timeout=self._timeout),
        )
        self._tasks.add(_task)
        _task.add_done_callback(
            partial(self._done_callback, task.future),
        )

    def _done_callback(self, future: futures.Future[T], task: asyncio.Task[T]) -> None:
        """Complete the future and start more tasks if possible."""
        exc = task.exception()
        if exc is not None:
            future.set_exception(exc)
        else:
            future.set_result(task.result())
        self._tasks.discard(task)
        self._start_tasks()

    async def _drain_pool(self) -> None:
        """Drain the buffer and complete all tasks."""
        with self._rlock:
            self._initialized.clear()
        while True:
            with self._rlock:
                if self._buffer.empty():
                    break
            # Wait for buffer to flush.
            await self._drain_tasks()
        # Wait for last tasks to complete.
        await self._drain_tasks()

    async def _drain_tasks(self) -> None:
        """Complete all currently running tasks."""
        if self._tasks:
            # Exceptions should be handled by client through the future.
            await asyncio.gather(*self._tasks, return_exceptions=True)
