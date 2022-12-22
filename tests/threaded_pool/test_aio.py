import pytest

from task_tools.threaded_pool.aio import AsyncThreadedTaskPool


@pytest.mark.asyncio()
async def test_methods(sleep):
    async with AsyncThreadedTaskPool() as pool:
        assert await pool.create_task(sleep(0.01)) == 0.01
        assert await pool.run(sleep(0.01)) == 0.01
