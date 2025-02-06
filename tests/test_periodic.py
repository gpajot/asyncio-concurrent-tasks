import asyncio
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta

if sys.version_info < (3, 11):
    from datetime import timezone

    UTC = timezone.utc
else:
    from datetime import UTC
from functools import partial
from zoneinfo import ZoneInfo

from concurrent_tasks.periodic import (
    OnTimePeriodicTask,
    PeriodicTask,
    _get_next_run_time,
)


@dataclass
class Sleeper:
    slept: float = 0

    async def sleep(self, delay: float) -> None:
        await asyncio.sleep(delay)
        self.slept += delay


class TestPeriodicTask:
    async def test_periodic(self):
        sleeper = Sleeper()
        with PeriodicTask(0.05, sleeper.sleep, 0.04):
            await asyncio.sleep(0.1)

        assert sleeper.slept == 0.08


class TestOnTimePeriodicTask:
    async def test_single(self):
        sleeper = Sleeper()
        with OnTimePeriodicTask(
            partial(sleeper.sleep, 0.04),
            datetime.now(UTC) + timedelta(milliseconds=40),
        ):
            await asyncio.sleep(0.1)

        assert sleeper.slept == 0.04

    async def test_single_overdue(self):
        sleeper = Sleeper()
        with OnTimePeriodicTask(
            partial(sleeper.sleep, 0.04),
            datetime.now(UTC) - timedelta(milliseconds=40),
        ):
            await asyncio.sleep(0.1)

        assert sleeper.slept == 0

        sleeper = Sleeper()
        with OnTimePeriodicTask(
            partial(sleeper.sleep, 0.04),
            datetime.now(UTC) - timedelta(milliseconds=40),
            ignore_overdue=False,
        ):
            await asyncio.sleep(0.1)

        assert sleeper.slept == 0.04

    async def test_repeat(self):
        sleeper = Sleeper()
        with OnTimePeriodicTask(
            partial(sleeper.sleep, 0.04),
            datetime.now(UTC) + timedelta(milliseconds=130),
            interval=timedelta(milliseconds=50),
        ):
            await asyncio.sleep(0.1)

        assert sleeper.slept == 0.04

    async def test_repeat_overdue(self):
        sleeper = Sleeper()
        with OnTimePeriodicTask(
            partial(sleeper.sleep, 0.04),
            datetime.now(UTC) - timedelta(milliseconds=90),
            interval=timedelta(milliseconds=35),
            ignore_overdue=False,
        ):
            await asyncio.sleep(0.1)

        assert sleeper.slept == 0.08

        sleeper = Sleeper()
        with OnTimePeriodicTask(
            partial(sleeper.sleep, 0.04),
            datetime.now(UTC) - timedelta(milliseconds=90),
            interval=timedelta(milliseconds=35),
        ):
            await asyncio.sleep(0.1)

        assert sleeper.slept == 0.04

    def test_dst(self):
        tz = ZoneInfo("Europe/Paris")
        now = datetime(2024, 10, 26, 23, tzinfo=tz)

        _, seconds_to = _get_next_run_time(now, now, timedelta(days=1))
        assert seconds_to == 25 * 3600

        _, seconds_to = _get_next_run_time(now, now, timedelta(hours=6))
        assert seconds_to == 6 * 3600
