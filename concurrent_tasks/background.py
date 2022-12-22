from __future__ import annotations

import asyncio
from contextlib import AbstractContextManager
from typing import Any, Callable, Coroutine, Generic, Optional, TypeVar

from typing_extensions import ParamSpec

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

    def __enter__(self) -> "BackgroundTask":
        self.create()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.cancel()

    def create(self) -> asyncio.Task[T]:
        if self._task:
            self._task.cancel()
        self._task = asyncio.create_task(self._func(*self._args, **self._kwargs))
        self._task.add_done_callback(self._done_callback)
        return self._task

    def cancel(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None

    def _done_callback(self, task: asyncio.Task[T]) -> None:
        """When a task is referenced, exception will be silenced
        Call result to raise the potential exception.
        """
        self._task = None
        if not task.cancelled():
            task.result()
