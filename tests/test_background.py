import asyncio
import time

import pytest

from concurrent_tasks.background import BackgroundTask


class TestBackgroundTask:
    @pytest.mark.asyncio()
    async def test_cancelled_error(self, sleep):
        # Simply test that cancelled error is not raised.
        with BackgroundTask(sleep, 1):
            await asyncio.sleep(0.001)

    @pytest.mark.asyncio()
    async def test_cancel(self, sleep):
        task = BackgroundTask(sleep, 1)
        _task = task.create()
        await asyncio.sleep(0.001)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await _task

    @pytest.mark.asyncio()
    async def test_output(self, sleep):
        output = await BackgroundTask(sleep, 0.01).create()
        assert output == 0.01

    @pytest.mark.asyncio()
    async def test_concurrency(self, sleep):
        start = time.monotonic()
        task1 = BackgroundTask(sleep, 0.01).create()
        task2 = BackgroundTask(sleep, 0.01).create()
        assert await asyncio.gather(task1, task2) == [0.01, 0.01]
        assert time.monotonic() - start < 0.02

    @pytest.mark.asyncio()
    async def test_restart(self, sleep):
        task = BackgroundTask(sleep, 0.01)
        task1 = task.create()
        task.cancel()
        task2 = task.create()
        assert await task2 == 0.01
        with pytest.raises(asyncio.CancelledError):
            await task1
