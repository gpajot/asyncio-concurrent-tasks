import asyncio
import sys
import types

import pytest

from concurrent_tasks.restartable import RestartableTask


class TestRestartableTask:
    @pytest.fixture()
    def func(self, mocker):
        return mocker.Mock()

    @pytest.fixture()
    def task(self, func):
        return RestartableTask(func, timeout=0.01)

    @pytest.mark.asyncio()
    async def test_not_started(self, task):
        with pytest.raises(RuntimeError, match="has not been started"):
            await task

    @pytest.mark.asyncio()
    async def test_already_started(self, task):
        task.start()
        with pytest.raises(RuntimeError, match="is already running"):
            task.start()
        task.cancel()

    @pytest.mark.asyncio()
    async def test_timeout(self, task):
        task.start()
        with pytest.raises(asyncio.TimeoutError):
            await task

    @pytest.mark.asyncio()
    async def test_restart(self, task, func):
        task.start()
        await asyncio.sleep(0)  # context switch to let the task start
        task.cancel()
        await asyncio.sleep(0.015)
        task.start()
        task.set_result(1)
        await task
        assert func.call_count == 2

    @pytest.mark.asyncio()
    async def test_success(self, task):
        task.start()
        task.set_result(1)
        assert await task == 1

    @pytest.mark.asyncio()
    async def test_failure(self, task):
        task.start()
        task.set_exception(ValueError("error"))
        with pytest.raises(ValueError, match="error"):
            await task

    @pytest.mark.skipif(
        sys.version_info < (3, 8), reason="requires python3.8 or higher for AsyncMock"
    )
    @pytest.mark.asyncio()
    async def test_async_func(self, mocker):
        func = mocker.AsyncMock(spec=types.FunctionType)
        task = RestartableTask(func, timeout=0.01)
        task.start()
        await asyncio.sleep(0)  # context switch to let the task start
        task.cancel()
        await asyncio.sleep(0)  # context switch to let the task cancel
        await asyncio.sleep(0)  # context switch to let the task cancel
        func.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_external_cancel(self, task):
        task.start()
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(task, 0.001)
        if sys.version_info >= (3, 8):
            with pytest.raises(asyncio.CancelledError):
                await task
