import asyncio
import contextlib
import functools
import time
from typing import Any, Callable, Coroutine, Generic, Optional, TypeVar, cast

from typing_extensions import ParamSpec

T = TypeVar("T")
P = ParamSpec("P")


class Debouncer(contextlib.AbstractAsyncContextManager, Generic[P, T]):
    def __init__(
        self,
        func: Callable[P, Coroutine[Any, Any, T]],
        duration: float,
        *,
        eager: bool = False,
        lazy: bool = False,
    ):
        if not eager and not lazy:
            raise ValueError("at least one of (`eager`, `lazy`) should be true")
        self._func = func
        self._duration = duration
        self._eager = eager
        self._lazy = lazy

        self._lock = asyncio.Lock()
        self._last_call: Optional[float] = None
        self._future: Optional[asyncio.Future[T]] = None
        self._next_params: tuple[tuple[Any, ...], dict[str, Any]] = ((), {})

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._future and not self._future.done():
            with contextlib.suppress(Exception):
                await self._future

    async def __call__(self, *args: P.args, **kwargs: P.kwargs) -> T:
        self._next_params = (args, kwargs)
        tick = time.monotonic()
        debounced = bool(self._last_call and tick - self._last_call < self._duration)
        async with self._lock:
            if self._last_call and self._last_call > tick:
                # Params already taken into account in last call.
                return await cast(asyncio.Future[T], self._future)
            if not self._lazy and debounced:
                return await cast(asyncio.Future[T], self._future)
            return (await self._call(wait=not self._eager or debounced)).result()

    async def _call(self, *, wait: bool = False) -> asyncio.Future[T]:
        self._future = asyncio.Future()
        if wait:
            wait_time = self._duration
            if self._eager and self._last_call:
                wait_time -= time.monotonic() - self._last_call
            if wait_time > 0:
                await asyncio.sleep(wait_time)
        self._last_call = time.monotonic()
        try:
            self._future.set_result(
                await self._func(
                    *self._next_params[0],
                    **self._next_params[1],
                )
            )
        except Exception as e:
            self._future.set_exception(e)
        return self._future


def debounce(
    duration: float,
    *,
    eager: bool = False,
    lazy: bool = False,
) -> Callable[
    [Callable[P, Coroutine[Any, Any, T]]], Callable[P, Coroutine[Any, Any, T]]
]:
    def outer(
        func: Callable[P, Coroutine[Any, Any, T]],
    ) -> Callable[P, Coroutine[Any, Any, T]]:
        debouncer: Debouncer[P, T] = Debouncer(func, duration, eager=eager, lazy=lazy)
        return functools.wraps(func)(debouncer)

    return outer
