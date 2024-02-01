# asyncio-concurrent-tasks

[![tests](https://github.com/gpajot/asyncio-concurrent-tasks/workflows/Test/badge.svg?branch=main&event=push)](https://github.com/gpajot/asyncio-concurrent-tasks/actions?query=workflow%3ATest+branch%3Amain+event%3Apush)
[![version](https://img.shields.io/pypi/v/concurrent_tasks?label=stable)](https://pypi.org/project/concurrent_tasks/)
[![python](https://img.shields.io/pypi/pyversions/concurrent_tasks)](https://pypi.org/project/concurrent_tasks/)

Tooling to run asyncio tasks.
- [Background task](#background-task)
- [Periodic task](#periodic-task)
- [Thread safe task pool](#thread-safe-task-pool)
- [Threaded task pool](#threaded-task-pool)
- [Restartable task](#restartable-task)

## Background task
Task that is running in the background until cancelled.
Can be used as a context manager.

Example usage:
```python
import asyncio
from typing import Callable, Awaitable
from concurrent_tasks import BackgroundTask


class HeartBeat(BackgroundTask):
    def __init__(self, interval: float, func: Callable[[], Awaitable]):
        super().__init__(self._run, interval, func)

    async def _run(self, interval: float, func: Callable[[], Awaitable]) -> None:
        while True:
            await func()
            await asyncio.sleep(interval)
```

## Periodic task
Task that is running periodically in the background until cancelled.
Can be used as a context manager.
There is no guarantee that the time between calls is strictly the interval if the function takes more time than the interval to execute.

Example usage:
```python
from typing import Callable, Awaitable
from concurrent_tasks import PeriodicTask


class HeartBeat(PeriodicTask):
    def __init__(self, interval: float, func: Callable[[], Awaitable]):
        super().__init__(interval, func)
```

## Thread safe task pool
The goal is to be able to safely run tasks from other threads.

Parameters:
- `size` can be a positive integer to limit the number of tasks concurrently running.
- `timeout` can be set to define a maximum running time for each time after which it will be cancelled.
Note: this excludes time spent waiting to be started (time spent in the buffer).

Example usage:
```python
from concurrent_tasks import ThreadSafeTaskPool


async def func():
    ...


async with ThreadSafeTaskPool() as pool:
    # Create and run the task.
    result = await pool.run(func())
    # Create a task, the `concurrent.Future` will hold information about completion.
    future = pool.create_task(func())
```

## Threaded task pool
Run async tasks in a dedicated thread. It will have its own event loop.
Under the hook, `ThreadSafeTaskPool` is used.

Parameters:
- `name` will be used as the thread's name.
- `size` and `timeout` see `ThreadSafeTaskPool`.
- `context_manager` can be optional context managers that will be entered when the loop has started
and exited before the loop is stopped.

> 💡 All tasks will be completed when the pool is stopped.

> 💡 Blocking and async version are the same, prefer the async version if client code is async.

### Loop initialization
> ⚠️ Asyncio primitives need to be instantiated with the proper event loop.

To achieve that, use a context manager wrapping instantiation of objects:
```python
from functools import partial

from concurrent_tasks import ThreadedPoolContextManagerWrapper, AsyncThreadedTaskPool

pool = AsyncThreadedTaskPool(context_manager=ThreadedPoolContextManagerWrapper(partial(MyObj, ...)))
```

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
    # Create a task, the `concurrent.Future` will hold information about completion.
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
    # Create a task, the asyncio.Future will hold information about completion.
    future = pool.create_task(func())
```

## Restartable task
Task that can be started and cancelled multiple times until it can finally be completed.
This is useful to handle pauses and retries when handling with a connection.

> 💡 Use `functools.partial` to pass parameters to the function.

Example usage:
```python
from functools import partial
from concurrent_tasks import RestartableTask

async def send(data): ...

task: RestartableTask[int] = RestartableTask(partial(send, b"\x00"), timeout=1)
task.start()
assert await task == 1

# Running in other tasks:

# On connection lost:
task.cancel()
# On connection resumed:
task.start()
# On response received:
task.set_result(1)
```
