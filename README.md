# asyncio-concurrent-tasks

[![tests](https://github.com/gpajot/asyncio-concurrent-tasks/workflows/Test/badge.svg?branch=main&event=push)](https://github.com/gpajot/asyncio-concurrent-tasks/actions?query=workflow%3ATest+branch%3Amain+event%3Apush)
[![version](https://img.shields.io/pypi/v/concurrent_tasks?label=stable)](https://pypi.org/project/concurrent_tasks/)
[![python](https://img.shields.io/pypi/pyversions/concurrent_tasks)](https://pypi.org/project/concurrent_tasks/)

Tooling to run asyncio tasks.

## Background task
Task that is running in the background until cancelled.
Can be used as a context manager.

Example usage:

```python
import asyncio
from typing import Callable, Awaitable
from concurrent_tasks import BackgroundTask


class HeartBeat(BackgroundTask):
    def __init__(self, interval: float, func: Callable[[], None]):
        super().__init__(self._run, interval, func)

    async def _run(self, interval: float, func: Callable[[], Awaitable]) -> None:
        while True:
            await func()
            await asyncio.sleep(interval)
```

## Threaded task pool
Run async tasks in a dedicated thread. It will have its own event loop.

Parameters:
- `name` will be used as the thread's name.
- `size` can be a positive integer to limit the number of tasks concurrently running.
- `timeout` can be set to define a maximum running time for each time after which it will be cancelled.
Note: this excludes time spent waiting to be started (time spent in the buffer).
- `context_manager` can be optional context managers that will be entered when the loop has started
and exited before the loop is stopped.

> 💡 All tasks will be completed when the pool is stopped.

> 💡Blocking and async version are the same, prefer the async version if client code is async.

### Blocking
This can be used to run async functions in a dedicated event loop, while keeping it running to handle background tasks

Example usage:

```python
from concurrent_tasks import BlockingThreadedTaskPool


async def func():
    ...


with BlockingThreadedTaskPool() as pool:
    # Create and run the task.
    result = pool.run(func())
    # Create a task, the future will hold information about completion.
    future = pool.create_task(func())
```

### Async
Threads can be useful in cooperation with asyncio to let the OS guarantee fair resource distribution between threads.
This is especially useful in case you cannot know if called code will properly cooperate with the event loop.

Example usage:

```python
from concurrent_tasks import AsyncThreadedTaskPool


async def func():
    ...


async with AsyncThreadedTaskPool() as pool:
    # Create and run the task.
    result = await pool.run(func())
    # Create a task, the future will hold information about completion.
    future = pool.create_task(func())
```
