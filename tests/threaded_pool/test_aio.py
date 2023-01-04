from concurrent_tasks.threaded_pool.aio import AsyncThreadedTaskPool


async def test_methods(sleep):
    async with AsyncThreadedTaskPool() as pool:
        assert await pool.create_task(sleep(0.01)) == 0.01
        assert await pool.run(sleep(0.01)) == 0.01
