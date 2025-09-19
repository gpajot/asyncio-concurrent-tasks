import asyncio
import inspect
import sys
from contextvars import Context
from typing import Any, Callable, Generator, Generic, Optional, TypeVar, cast

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
        self._started = asyncio.Event()

    def __await__(self) -> Generator[Any, None, T]:
        return self._wait().__await__()

    def start(self, context: Optional[Context] = None) -> None:
        """Start one attempt of the task."""
        if self._task:
            return
        self._future = asyncio.Future()
        self._started.set()
        if sys.version_info >= (3, 11):
            self._task = asyncio.create_task(self._run(), context=context)
        else:
            self._task = asyncio.create_task(self._run())

    def cancel(self) -> None:
        """Cancel the current task if started."""
        if not self._task:
            return
        self._task.cancel()
        self._task = None
        self._started.clear()
        self._future = None

    def set_result(self, result: T) -> None:
        """Complete the task with the result."""
        if self._future:
            self._future.set_result(result)

    def set_exception(self, exception: BaseException) -> None:
        """Complete the task by raising an exception."""
        if self._future:
            self._future.set_exception(exception)

    async def _wait(self) -> T:
        """Wait for the full task to complete."""
        if not self._task:
            raise RuntimeError(
                f"restartable task for func {self._func} has not been started"
            )
        # Keep waiting until the task has completed without being manually cancelled.
        while True:
            await self._started.wait()
            assert self._task
            try:
                return await self._task
            except asyncio.CancelledError:
                # The task was cancelled.
                if not self._started.is_set():
                    continue
                raise

    async def _run(self) -> T:
        # partial called on method isn't recognized as coroutine func until 3.10.
        call = self._func()
        if inspect.iscoroutine(call):
            await call
        return await asyncio.wait_for(
            cast("asyncio.Future[T]", self._future),
            self._timeout,
        )
