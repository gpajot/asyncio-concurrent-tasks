import asyncio
import time

import pytest

from concurrent_tasks.pool import TaskPool


async def test_concurrency(sleep):
    async with TaskPool() as pool:
        start = time.monotonic()
        assert await asyncio.gather(
            pool.run(sleep(0.01)),
            pool.run(sleep(0.01)),
        ) == [0.01, 0.01]
        assert time.monotonic() - start < 0.02


async def test_size(sleep):
    async with TaskPool(size=1) as pool:
        start = time.monotonic()
        assert await asyncio.gather(
            pool.run(sleep(0.01)),
            pool.run(sleep(0.01)),
        ) == [0.01, 0.01]
        assert time.monotonic() - start >= 0.02


async def test_timeout(sleep):
    async with TaskPool(timeout=0.015) as pool:
        start = time.monotonic()
        res1, res2 = await asyncio.gather(
            pool.run(sleep(0.01)),
            pool.run(sleep(0.02)),
            return_exceptions=True,
        )
        assert time.monotonic() - start < 0.02
        assert res1 == 0.01  # type: ignore[has-type]
        assert isinstance(res2, asyncio.TimeoutError)  # type: ignore[has-type]


async def test_fire_and_forget(sleep):
    async with TaskPool() as pool:
        future = pool.create_task(sleep(0.01))

    assert future.done()
    assert future.result() == 0.01


async def test_fire_and_forget_error(key_error):
    async with TaskPool() as pool:
        future = pool.create_task(key_error())

    assert future.done()
    with pytest.raises(KeyError):
        future.result()


async def test_cancel_immediate():
    started = False
    completed = False

    async def _task():
        nonlocal started, completed
        started = True
        await asyncio.sleep(0.1)
        completed = True

    async with TaskPool() as pool:
        future = pool.create_task(_task())
        future.cancel()

    assert started
    assert not completed


async def test_cancel_later():
    started = False
    completed = False

    async def _task():
        nonlocal started, completed
        started = True
        await asyncio.sleep(0.1)
        completed = True

    async with TaskPool() as pool:
        future = pool.create_task(_task())
        await asyncio.sleep(0.01)
        future.cancel()

    assert started
    assert not completed
