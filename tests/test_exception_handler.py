import asyncio
import signal
from typing import List

import pytest

from concurrent_tasks.exception_handler import LoopExceptionHandler


async def run(stop_func, *coros, raise_exc=None, raise_sig=None, results=None):
    async with LoopExceptionHandler(stop_func):
        if raise_exc:

            async def _raise():
                raise raise_exc

            asyncio.create_task(_raise())
        if raise_sig:
            signal.raise_signal(raise_sig)
        res = await asyncio.gather(*[asyncio.create_task(coro) for coro in coros])
        if results is not None:
            results += res
        return res


async def sleep(d):
    await asyncio.sleep(d)
    return d


@pytest.fixture()
def stop_func(mocker):
    return mocker.AsyncMock()


def test_normal(stop_func):
    results = asyncio.run(
        run(stop_func, sleep(0.01), sleep(0.005)),
    )
    assert results == [0.01, 0.005]
    stop_func.assert_not_called()


def test_exception(stop_func):
    exc = ValueError("!")
    results: List[float] = []
    with pytest.raises(ValueError, match="!"):
        asyncio.run(
            run(stop_func, sleep(0.01), raise_exc=exc, results=results),
        )
    # Check that the other task has completed.
    assert results == [0.01]
    stop_func.assert_awaited_once()


def test_signal(stop_func):
    results = asyncio.run(
        run(stop_func, sleep(0.01), raise_sig=signal.SIGINT),
    )
    # Check that the other task are completed.
    assert results == [0.01]
    stop_func.assert_awaited_once()
