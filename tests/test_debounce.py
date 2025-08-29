import asyncio
import time
from unittest.mock import call

import pytest

from concurrent_tasks.debounce import AsyncDebouncer, debounce


async def test_debounce_exception(key_error):
    debounced = debounce(1, eager=True)(key_error)
    with pytest.raises(KeyError):
        await debounced()


@pytest.fixture
def func(mocker):
    async def _f(i: int) -> int:
        await asyncio.sleep(0.001)
        return i

    return mocker.Mock(wraps=_f)


async def test_debounce_eager_fire_immediately(func):
    debounced = debounce(0.01, eager=True)(func)
    start = time.monotonic()
    assert await debounced(1) == 1
    assert time.monotonic() - start < 0.01
    assert func.call_args_list == [call(1)]


async def test_debounce_eager_debounced(func):
    debounced = debounce(0.01, eager=True)(func)
    task1 = asyncio.create_task(debounced(1))
    task2 = asyncio.create_task(debounced(2))
    start = time.monotonic()
    assert await asyncio.gather(task1, task2) == [1, 1]
    assert time.monotonic() - start < 0.01
    assert func.call_args_list == [call(1)]


async def test_debounce_eager_subsequent(func):
    debounced = debounce(0.01, eager=True)(func)
    assert await debounced(1) == 1
    await asyncio.sleep(0.01)
    assert await debounced(2) == 2
    assert func.call_args_list == [call(1), call(2)]


async def test_debounce_lazy_use_last_params(func):
    debounced = debounce(0.01, lazy=True)(func)
    task1 = asyncio.create_task(debounced(1))
    task2 = asyncio.create_task(debounced(2))
    start = time.monotonic()
    assert await asyncio.gather(task1, task2) == [2, 2]
    assert time.monotonic() - start >= 0.01
    assert func.call_args_list == [call(2)]


async def test_debounce_lazy_subsequent(func):
    debounced = debounce(0.01, lazy=True)(func)
    assert await debounced(1) == 1
    await asyncio.sleep(0.01)
    assert await debounced(2) == 2
    assert func.call_args_list == [call(1), call(2)]


async def test_debounce_full(func):
    debounced = debounce(0.01, eager=True, lazy=True)(func)
    task1 = asyncio.create_task(debounced(1))
    task2 = asyncio.create_task(debounced(2))
    task3 = asyncio.create_task(debounced(3))
    start = time.monotonic()
    assert await asyncio.gather(task1, task2, task3) == [1, 3, 3]
    assert time.monotonic() - start >= 0.01
    assert func.call_args_list == [call(1), call(3)]


async def test_async(func):
    async with AsyncDebouncer(func, 0.01) as debounced:
        assert await debounced(1) is False
        assert await debounced(2) is True
        assert await debounced(3) is True
        await asyncio.sleep(0.025)
        assert await debounced(4) is False
    assert func.call_args_list == [call(1), call(3), call(4)]
