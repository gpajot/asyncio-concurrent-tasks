import asyncio
import functools
import math
import sys
from datetime import datetime, timedelta

if sys.version_info < (3, 11):
    from datetime import timezone

    UTC = timezone.utc
else:
    from datetime import UTC
from time import monotonic
from typing import Callable, Coroutine, Generic, Optional, TypeVar

from typing_extensions import ParamSpec  # 3.10

from concurrent_tasks.background import BackgroundTask

T = TypeVar("T")
P = ParamSpec("P")


class PeriodicTask(BackgroundTask[None], Generic[P]):
    """Run an async task periodically in the background.

    Note: there is no guarantee that the time between calls is strictly the interval
    if the function takes more time than the interval to execute.
    """

    def __init__(
        self,
        interval: float,
        func: Callable[P, Coroutine],
        *args: P.args,
        **kwargs: P.kwargs,
    ):
        super().__init__(
            functools.partial(_run_periodic, interval, func),
            *args,
            **kwargs,
        )


async def _run_periodic(
    interval: float,
    func: Callable[P, Coroutine],
    *args: P.args,
    **kwargs: P.kwargs,
) -> None:
    while True:
        start = monotonic()
        await func(*args, **kwargs)
        if (remaining := interval - (monotonic() - start)) > 0:
            await asyncio.sleep(remaining)


class OnTimePeriodicTask(BackgroundTask[None]):
    """Compared to `PeriodicTask`, this runs consistently on a specific time.
    When DST switch occurs, when `timedelta(days=x)` or above is used, time will remain the same.

    Note: use `functools.partial` to pass arguments if necessary.

    If using `ignore_overdue`, if the function execution time makes us miss the next run,
    it will be ignored.
    """

    def __init__(
        self,
        func: Callable[[], Coroutine],
        on: datetime,
        *,
        interval: Optional[timedelta] = None,
        ignore_overdue: bool = True,
    ):
        if not on.tzinfo:
            raise ValueError("a timezone is required")
        super().__init__(_run_on_time, func, on, interval, ignore_overdue)


async def _sleep(delay: float, ignore_overdue: bool) -> bool:
    if delay < 0 and ignore_overdue:
        return False
    if delay > 0:
        await asyncio.sleep(delay)
    return True


def _get_next_run_time(
    now: datetime,
    dt: datetime,
    interval: Optional[timedelta] = None,
) -> tuple[datetime, float]:
    if not interval:
        # Compare in UTC to ensure proper sleep time event with DST.
        return dt, (dt.astimezone(UTC) - now).total_seconds()

    next_dt = dt + interval
    if interval.total_seconds() < 86400:
        # Compare in local timezone to ensure interval is consistent.
        return next_dt, (next_dt - now.astimezone(dt.tzinfo)).total_seconds()
    # Compare in UTC to ensure proper sleep time event with DST.
    return next_dt, (next_dt.astimezone(UTC) - now).total_seconds()


async def _run_on_time(
    func: Callable[[], Coroutine],
    on: datetime,
    interval: Optional[timedelta],
    ignore_overdue: bool,
) -> None:
    if not interval:
        # Simply run on a specific time.
        _, seconds_to = _get_next_run_time(datetime.now(UTC), on)
        if await _sleep(seconds_to, ignore_overdue):
            await func()
        return

    now = datetime.now(tz=on.tzinfo)
    # Ensure we are at the previous run.
    prev_run_time = on + math.floor((now - on) / interval) * interval
    while True:
        prev_run_time, seconds_to = _get_next_run_time(
            datetime.now(UTC), prev_run_time, interval
        )
        if await _sleep(seconds_to, ignore_overdue):
            await func()
