import asyncio
import time

import pytest

from concurrent_tasks.debounce import debounce


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
    _assert_func_calls(func, 1)


async def test_debounce_eager_debounced(func):
    debounced = debounce(0.01, eager=True)(func)
    task1 = asyncio.create_task(debounced(1))
    task2 = asyncio.create_task(debounced(2))
    start = time.monotonic()
    assert await asyncio.gather(task1, task2) == [1, 1]
    assert time.monotonic() - start < 0.01
    _assert_func_calls(func, 1)


async def test_debounce_eager_subsequent(func):
    debounced = debounce(0.01, eager=True)(func)
    assert await debounced(1) == 1
    await asyncio.sleep(0.01)
    assert await debounced(2) == 2
    _assert_func_calls(func, 1, 2)


async def test_debounce_lazy_use_last_params(func):
    debounced = debounce(0.01, lazy=True)(func)
    task1 = asyncio.create_task(debounced(1))
    task2 = asyncio.create_task(debounced(2))
    start = time.monotonic()
    assert await asyncio.gather(task1, task2) == [2, 2]
    assert time.monotonic() - start >= 0.01
    _assert_func_calls(func, 2)


async def test_debounce_lazy_subsequent(func):
    debounced = debounce(0.01, lazy=True)(func)
    assert await debounced(1) == 1
    await asyncio.sleep(0.01)
    assert await debounced(2) == 2
    _assert_func_calls(func, 1, 2)


async def test_debounce_full(func):
    debounced = debounce(0.01, eager=True, lazy=True)(func)
    task1 = asyncio.create_task(debounced(1))
    task2 = asyncio.create_task(debounced(2))
    task3 = asyncio.create_task(debounced(3))
    start = time.monotonic()
    assert await asyncio.gather(task1, task2, task3) == [1, 3, 3]
    assert time.monotonic() - start >= 0.01
    _assert_func_calls(func, 1, 3)


def _assert_func_calls(func, *args):
    func.assert_has_calls(tuple(((i,), {}) for i in args))
