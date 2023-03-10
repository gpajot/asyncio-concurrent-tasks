import asyncio
import sys
import types
from functools import partial

import pytest

from concurrent_tasks.restartable import RestartableTask


class TestRestartableTask:
    @pytest.fixture()
    def func(self, mocker):
        return mocker.Mock(return_value=None)

    @pytest.fixture()
    def task(self, func):
        return RestartableTask(func, timeout=0.01)

    async def test_not_started(self, task):
        with pytest.raises(RuntimeError, match="has not been started"):
            await task

    async def test_already_started(self, task):
        task.start()
        with pytest.raises(RuntimeError, match="is already running"):
            task.start()
        task.cancel()

    async def test_timeout(self, task):
        task.start()
        with pytest.raises(asyncio.TimeoutError):
            await task

    async def test_restart(self, task, func):
        task.start()
        await asyncio.sleep(0)  # context switch to let the task start
        task.cancel()
        await asyncio.sleep(0.015)
        task.start()
        task.set_result(1)
        await task
        assert func.call_count == 2

    async def test_success(self, task):
        task.start()
        task.set_result(1)
        assert await task == 1

    async def test_failure(self, task):
        task.start()
        task.set_exception(ValueError("error"))
        with pytest.raises(ValueError, match="error"):
            await task

    async def test_partial_func(self, mocker):
        func = mocker.Mock()
        task: RestartableTask[None] = RestartableTask(partial(func, 1), timeout=0.01)
        task.start()
        await asyncio.sleep(0)  # context switch to let the task start
        task.cancel()
        await asyncio.sleep(0)  # context switch to let the task cancel
        func.assert_called_with(1)

    async def test_partial_async_func(self):
        called = False

        async def func(arg: int):
            assert arg == 1
            nonlocal called
            called = True

        task: RestartableTask[None] = RestartableTask(partial(func, 1), timeout=0.01)
        task.start()
        await asyncio.sleep(0)  # context switch to let the task start
        task.cancel()
        await asyncio.sleep(0)  # context switch to let the task cancel
        assert called is True

    async def test_partial_async_method(self):
        called = False

        class A:
            async def func(self, arg: int):
                assert arg == 1
                nonlocal called
                called = True

        task: RestartableTask[None] = RestartableTask(
            partial(A().func, 1), timeout=0.01
        )
        task.start()
        await asyncio.sleep(0)  # context switch to let the task start
        task.cancel()
        await asyncio.sleep(0)  # context switch to let the task cancel
        assert called is True

    async def test_partial_async_func_mock(self, mocker):
        func = mocker.AsyncMock(spec=types.FunctionType)
        task: RestartableTask[None] = RestartableTask(partial(func, 1), timeout=0.01)
        task.start()
        await asyncio.sleep(0)  # context switch to let the task start
        task.cancel()
        await asyncio.sleep(0)  # context switch to let the task cancel
        func.assert_awaited_once_with(1)

    async def test_external_cancel(self, task):
        task.start()
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(task, 0.001)
        if sys.version_info >= (3, 8):
            with pytest.raises(asyncio.CancelledError):
                await task
