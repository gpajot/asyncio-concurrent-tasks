import asyncio

from concurrent_tasks.periodic import PeriodicTask


class TestPeriodicTask:
    async def test_periodic(self, sleep):
        total_runs = 0

        async def increment(value: int):
            await asyncio.sleep(0.04)
            nonlocal total_runs
            total_runs += value

        with PeriodicTask(0.05, increment, 1):
            await asyncio.sleep(0.1)

        assert total_runs == 2
