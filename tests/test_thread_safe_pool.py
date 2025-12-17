import asyncio
import contextlib
import threading
import time

import pytest

from concurrent_tasks.thread_safe_pool import ThreadSafeTaskPool


async def test_concurrency(sleep):
    async with ThreadSafeTaskPool() as pool:
        start = time.monotonic()
        assert await asyncio.gather(
            pool.run(sleep(0.01)),
            pool.run(sleep(0.01)),
        ) == [0.01, 0.01]
        assert time.monotonic() - start < 0.02


async def test_size(sleep):
    async with ThreadSafeTaskPool(size=1) as pool:
        start = time.monotonic()
        assert await asyncio.gather(
            pool.run(sleep(0.01)),
            pool.run(sleep(0.01)),
        ) == [0.01, 0.01]
        assert time.monotonic() - start >= 0.02


async def test_timeout(sleep):
    async with ThreadSafeTaskPool(timeout=0.015) as pool:
        start = time.monotonic()
        res1, res2 = await asyncio.gather(
            pool.run(sleep(0.01)),
            pool.run(sleep(0.02)),
            return_exceptions=True,
        )
        assert time.monotonic() - start < 0.02
        assert res1 == 0.01
        assert isinstance(res2, asyncio.TimeoutError)


async def test_thread(sleep):
    event = threading.Event()
    async with ThreadSafeTaskPool(timeout=0.015) as pool:

        def _run():
            future = pool.create_task(sleep(0.01))
            event.set()
            assert future.result(0.015) == 0.01

        thread = threading.Thread(target=_run)
        thread.start()
        # Wait until the task was created.
        event.wait(0.01)

    thread.join(0.02)

    assert event.is_set()


async def test_fire_and_forget(sleep):
    async with ThreadSafeTaskPool() as pool:
        future = pool.create_task(sleep(0.01))

    assert future.done()
    assert future.result() == 0.01


async def test_fire_and_forget_error(key_error):
    async with ThreadSafeTaskPool() as pool:
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

    task = _task()
    async with ThreadSafeTaskPool() as pool:
        future = pool.create_task(task)
        future.cancel()

    assert not started
    assert not completed
    with contextlib.suppress(asyncio.CancelledError):
        await task


async def test_cancel_later():
    started = False
    completed = False

    async def _task():
        nonlocal started, completed
        started = True
        await asyncio.sleep(0.1)
        completed = True

    async with ThreadSafeTaskPool() as pool:
        future = pool.create_task(_task())
        await asyncio.sleep(0.01)
        future.cancel()

    assert started
    assert not completed
