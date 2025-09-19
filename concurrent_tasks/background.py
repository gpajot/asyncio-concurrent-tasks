import asyncio
import sys
from contextlib import AbstractContextManager
from contextvars import Context
from typing import Any, Callable, Coroutine, Generator, Generic, Optional, TypeVar

from typing_extensions import ParamSpec, Self  # 3.10, 3.11

T = TypeVar("T")
P = ParamSpec("P")


class BackgroundTask(AbstractContextManager, Generic[T]):
    """Run an async task in the background."""

    def __init__(
        self,
        func: Callable[P, Coroutine[Any, Any, T]],
        *args: P.args,
        **kwargs: P.kwargs,
    ):
        self._func = func
        self._args = args
        self._kwargs = kwargs
        self._task: Optional[asyncio.Task[T]] = None

    def __enter__(self) -> Self:
        self.create()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.cancel()

    def __await__(self) -> Generator[Any, None, Optional[T]]:
        if self._task:
            return self._task.__await__()
        return _empty_gen()

    def create(self, context: Optional[Context] = None) -> asyncio.Task[T]:
        if self._task:
            self._task.cancel()
        coro = self._func(*self._args, **self._kwargs)
        if sys.version_info >= (3, 11):
            self._task = asyncio.create_task(coro, context=context)
        else:
            self._task = asyncio.create_task(coro)
        self._task.add_done_callback(self._done_callback)
        return self._task

    def cancel(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None

    def _done_callback(self, task: asyncio.Task[T]) -> Optional[T]:
        """When a task is referenced, exception will be silenced
        Call result to raise the potential exception.
        """
        self._task = None
        if not task.cancelled():
            return task.result()
        return None


def _empty_gen() -> Generator[Any, None, None]:
    yield
