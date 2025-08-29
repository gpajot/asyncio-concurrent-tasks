# asyncio-concurrent-tasks

[![tests](https://github.com/gpajot/asyncio-concurrent-tasks/actions/workflows/test.yml/badge.svg?branch=main&event=push)](https://github.com/gpajot/asyncio-concurrent-tasks/actions/workflows/test.yml?query=branch%3Amain+event%3Apush)
[![PyPi](https://img.shields.io/pypi/v/concurrent_tasks?label=stable)](https://pypi.org/project/concurrent_tasks/)
[![python](https://img.shields.io/pypi/pyversions/concurrent_tasks)](https://pypi.org/project/concurrent_tasks/)

Tooling to run asyncio tasks.
- [Background task](#background-task)
- [Periodic task](#periodic-task)
- [On time periodic task](#on-time-periodic-task)
- [Thread safe task pool](#thread-safe-task-pool)
- [Task pool](#task-pool)
- [Threaded task pool](#threaded-task-pool)
- [Restartable task](#restartable-task)
- [Loop exception handler](#loop-exception-handler)
- [Debouncer](#debouncer)
- [Robust protocol](#robust-protocol)

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

## On time periodic task

Compared to `PeriodicTask`, this runs consistently on a specific time.
When DST switch occurs, intervals greater or equal to 1 day will be run at the same time in the timezone,
intervals of less than a day will be run at a consistent interval.
It can be used either without an interval to un on a specific time, or regularly.

> [!TIP]
> Use `functools.partial` to pass arguments if necessary.

> [!NOTE]
>  If `ignore_overdue` is set to `True`, if the function execution time makes us miss the next run, it will be ignored.

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
    # Create a task, the `concurrent.futures.Future` will hold information about completion.
    future = pool.create_task(func())
```

## Task pool

See `ThreadSafeTaskPool`, the interface is the same except:
- it is not thread safe
- `asyncio.Future` is used instead of `concurrent.futures.Future`

## Threaded task pool

Run async tasks in a dedicated thread. It will have its own event loop.
Under the hook, `ThreadSafeTaskPool` is used.

Parameters:
- `name` will be used as the thread's name.
- `size` and `timeout` see `ThreadSafeTaskPool`.
- `context_manager` can be optional context managers that will be entered when the loop has started
and exited before the loop is stopped.

> [!NOTE]
> All tasks will be completed when the pool is stopped.

> [!TIP]
> Blocking and async version are the same, prefer the async version if client code is async.

### Loop initialization

> [!WARNING]
> Asyncio primitives need to be instantiated with the proper event loop.

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

> [!TIP]
> Use `functools.partial` to pass parameters to the function.

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

## Loop exception handler

Shut down process when an unhandled exception is caught or a signal is received.
To make this a graceful stop, pass a `stop_func`.

When creating multiple background tasks, exceptions raised within those will be forwarded directly to the event loop.
In order to act on those exceptions, we need to use `loop.set_exception_handler`.

> [!IMPORTANT]
> When a signal is received and the process is already shutting down, it will be force killed.

Example minimalistic implementation:

```python
import asyncio
from concurrent_tasks import LoopExceptionHandler

async def run():
    event = asyncio.Event()
    tasks = []
    async def _stop():
        await asyncio.gather(*tasks)
        event.set()
    async with LoopExceptionHandler(_stop):
        # Adding a bunch of tasks here...
        await event.wait()
```

## Debouncer

Can be used either through the class `Debouncer` (which can be gracefully ended through its `__aexit__` method) or with the decorator `debounce`.

- `eager` calls the function immediately unless debounced. Debounced calls will return the last result.
- `lazy` will call the function at the end of the debounce duration, with the last parameters. All calls will block until the period is over.
- when both options are used, the first call will return immediately, and subsequent debounced calls will block until the end.

If the output of the debounced function isn't important, `AsyncDebouncer` can be used.


## Robust protocol

Automatically reconnects unless closed purposefully. To be used with asyncio connections and transports.

> [!WARNING]
> When reading data, reconnections will be transparent, so it's up to the consumer to handle incomplete data.

```python
import asyncio
from functools import partial
from concurrent_tasks import RobustStream


async def run():
    async with RobustStream(partial(
        asyncio.get_running_loop().create_connection,
        address="127.0.0.1",
        port=8000,
    )) as protocol:
        await protocol.write(b"...")
        reader = protocol.reader
        data = await reader.readline()
```
