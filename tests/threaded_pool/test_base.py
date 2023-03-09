import asyncio
import time
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncIterator, Iterator

import pytest

from concurrent_tasks.threaded_pool.base import BaseThreadedTaskPool


@contextmanager
def pool_cm(pool: BaseThreadedTaskPool) -> Iterator[BaseThreadedTaskPool]:
    pool.start()
    try:
        pool.post_start().result()
    except Exception:
        pool.stop()
        raise
    try:
        yield pool
    finally:
        pool.pre_stop(None, None, None).result()
        pool.stop()


class TestBaseThreadedTaskPool:
    def test_concurrency(self, sleep):
        with pool_cm(BaseThreadedTaskPool()) as pool:
            start = time.monotonic()
            future1 = pool.create_task(sleep(0.01))
            future2 = pool.create_task(sleep(0.01))
            assert future1.result() == 0.01
            assert future2.result() == 0.01
            assert time.monotonic() - start < 0.02

    def test_size(self, sleep):
        with pool_cm(BaseThreadedTaskPool(size=1)) as pool:
            start = time.monotonic()
            future1 = pool.create_task(sleep(0.01))
            future2 = pool.create_task(sleep(0.01))
            assert future1.result() == 0.01
            assert future2.result() == 0.01
            assert time.monotonic() - start >= 0.02

    def test_timeout(self, sleep):
        with pool_cm(BaseThreadedTaskPool(timeout=0.015)) as pool:
            start = time.monotonic()
            future1 = pool.create_task(sleep(0.01))
            future2 = pool.create_task(sleep(0.02))
            assert future1.result() == 0.01
            with pytest.raises(asyncio.TimeoutError):
                future2.result()
            assert time.monotonic() - start < 0.02

    def test_context_manager(self, mocker):
        enter_sentinel = mocker.Mock()
        exit_sentinel = mocker.Mock()

        @contextmanager
        def cm() -> Iterator[None]:
            enter_sentinel()
            try:
                yield None
            finally:
                exit_sentinel()

        pool = BaseThreadedTaskPool(context_manager=cm())
        assert enter_sentinel.call_count == 0
        assert exit_sentinel.call_count == 0
        with pool_cm(pool):
            assert enter_sentinel.call_count == 1
            assert exit_sentinel.call_count == 0
        assert enter_sentinel.call_count == 1
        assert exit_sentinel.call_count == 1

    def test_async_context_manager(self, mocker):
        enter_sentinel = mocker.AsyncMock()
        exit_sentinel = mocker.AsyncMock()

        @asynccontextmanager
        async def cm() -> AsyncIterator[None]:
            await enter_sentinel()
            try:
                yield None
            finally:
                await exit_sentinel()

        pool = BaseThreadedTaskPool(context_manager=cm())
        assert enter_sentinel.call_count == 0
        assert exit_sentinel.call_count == 0
        with pool_cm(pool):
            assert enter_sentinel.call_count == 1
            assert exit_sentinel.call_count == 0
        assert enter_sentinel.call_count == 1
        assert exit_sentinel.call_count == 1

    async def test_lifecycle(self, sleep):
        pool = BaseThreadedTaskPool()

        with pytest.raises(RuntimeError, match="is not running"):
            pool.post_start().result()

        with pytest.raises(RuntimeError, match="is not running"):
            pool.pre_stop(None, None, None).result()

        with pytest.raises(RuntimeError, match="is not running"):
            pool.stop()

        task = sleep(0.01)
        with pytest.raises(RuntimeError, match="is not running"):
            pool.create_task(task)
        await task  # remove warnings about coroutine not awaited.

        with pool_cm(pool):
            with pytest.raises(RuntimeError, match="is already running"):
                pool.start()
            assert pool.create_task(sleep(0.01)).result() == 0.01

        task = sleep(0.01)
        with pytest.raises(RuntimeError, match="is not running"):
            pool.create_task(task)
        await task  # remove warnings about coroutine not awaited.

        with pool_cm(pool):
            assert pool.create_task(sleep(0.01)).result() == 0.01

        task = sleep(0.01)
        with pytest.raises(RuntimeError, match="is not running"):
            pool.create_task(task)
        await task  # remove warnings about coroutine not awaited.

    @pytest.mark.skip(reason="benchmark")
    def test_bench(self, sleep):
        iterations = 100

        loop = asyncio.new_event_loop()
        start = time.monotonic()
        i = 0
        while i < iterations:
            loop.run_until_complete(sleep(0.01))
            i += 1
        no_thread_time = time.monotonic() - start
        print(f"no thread, {iterations} iterations: {no_thread_time}")

        start = time.monotonic()
        i = 0
        with pool_cm(BaseThreadedTaskPool()) as pool:
            while i < iterations:
                pool.create_task(sleep(0.01)).result()
                i += 1
        with_thread_time = time.monotonic() - start
        print(
            f"with thread, {iterations} iterations: {with_thread_time} ({with_thread_time / no_thread_time * 100:.1f}%)"
        )
