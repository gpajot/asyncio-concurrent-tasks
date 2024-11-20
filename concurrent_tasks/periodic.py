import asyncio
from time import monotonic
from typing import Awaitable, Callable, Generic, TypeVar

from typing_extensions import ParamSpec

from concurrent_tasks.background import BackgroundTask

T = TypeVar("T")
P = ParamSpec("P")


class PeriodicTask(BackgroundTask, Generic[P]):
    """Run an async task periodically in the background.

    Note: there is no guarantee that the time between calls is strictly the interval
    if the function takes more time than the interval to execute.
    """

    def __init__(
        self,
        interval: float,
        func: Callable[P, Awaitable],
        *args: P.args,
        **kwargs: P.kwargs,
    ):
        super().__init__(self._run, interval, *args, **kwargs)
        self._initial_func = func

    async def _run(self, interval: float, *args: P.args, **kwargs: P.kwargs):
        while True:
            start = monotonic()
            await self._initial_func(*args, **kwargs)
            if (remaining := interval - (monotonic() - start)) > 0:
                await asyncio.sleep(remaining)
