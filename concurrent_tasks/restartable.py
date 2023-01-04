from __future__ import annotations

import asyncio
import inspect
from typing import Any, Callable, Generic, Optional, TypeVar, cast

T = TypeVar("T")


class RestartableTask(Generic[T]):
    """Task that can be cancelled and restarted.
    Awaiting will wait for the task to complete or timeout.
    Completing the task is done by resolving it with `set_exception` or `set_result`.
    """

    def __init__(
        self,
        func: Callable[[], Any],
        timeout: Optional[float] = None,
    ):
        self._timeout = timeout
        self._func = func
        self._task: Optional[asyncio.Task[T]] = None
        self._future: Optional[asyncio.Future[T]] = None
        self._done = asyncio.Event()
        self._cancelled = False

    def __await__(self):
        return self._wait().__await__()

    def start(self) -> None:
        """Start one attempt of the task."""
        if self._task and not self._task.cancelled():
            raise RuntimeError(
                f"restartable task for func {self._func} is already running"
            )
        self._cancelled = False
        self._future = asyncio.Future()
        self._task = asyncio.create_task(self._run())

    def cancel(self) -> None:
        """Cancel the current task if started."""
        if self._task:
            self._cancelled = True
            self._task.cancel()

    def set_result(self, result: T) -> None:
        """Complete the task with the result."""
        if not self._future:
            raise RuntimeError(
                f"restartable task for func {self._func} has not been started"
            )
        self._future.set_result(result)

    def set_exception(self, exception: BaseException) -> None:
        """Complete the task by raising an exception."""
        if not self._future:
            raise RuntimeError(
                f"restartable task for func {self._func} has not been started"
            )
        self._future.set_exception(exception)

    async def _wait(self) -> T:
        """Wait for the full task to complete."""
        if not self._task:
            raise RuntimeError(
                f"restartable task for func {self._func} has not been started"
            )
        # Keep waiting until the task has completed without being manually cancelled.
        while True:
            self._done.clear()
            try:
                await self._done.wait()
            finally:
                # Manually cancel the task if this is externally cancelled.
                if not self._task.done():
                    self._task.cancel()
            if not self._cancelled:
                # The task has completed.
                break
        return await self._task

    async def _run(self) -> T:
        # Partial isn't recognized as coroutine function in python 3.7.
        call = self._func()
        if inspect.iscoroutine(call):
            await call
        try:
            return await asyncio.wait_for(
                cast("asyncio.Future[T]", self._future), self._timeout
            )
        finally:
            self._done.set()
