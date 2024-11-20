import asyncio
import threading
from concurrent import futures
from contextlib import AsyncExitStack
from typing import (
    AsyncContextManager,
    Awaitable,
    Callable,
    ContextManager,
    Optional,
    TypeVar,
    Union,
)

from concurrent_tasks.thread_safe_pool import ThreadSafeTaskPool

T = TypeVar("T")


class BaseThreadedTaskPool:
    """Task pool running asynchronous tasks in another dedicated thread."""

    def __init__(
        self,
        name: Optional[str] = None,
        size: int = 0,
        timeout: Optional[float] = None,
        context_manager: Optional[Union[ContextManager, AsyncContextManager]] = None,
        daemon: bool = False,
    ):
        self._name = name

        self._size = size
        self._timeout = timeout
        self._pool: Optional[ThreadSafeTaskPool] = None

        # Context managers.
        self._stack = AsyncExitStack()
        self._context_manager = context_manager

        self._thread: Optional[threading.Thread] = None
        self._daemon = daemon
        # Create an event loop for that thread.
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        # Set when the event loop is running.
        # Cleared when stopping to prevent receiving new tasks.
        self._initialized = threading.Event()

    def start(self) -> None:
        """Start the thread and wait for the loop to start running."""
        if self._thread is not None:
            raise RuntimeError(
                f"{self.__class__.__name__}({self._name}) is already running"
            )
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            name=self._name,
            target=self._run_thread,
            daemon=self._daemon,
        )
        self._thread.start()
        self._initialized.wait()

    async def _post_start(self) -> None:
        """Enter context managers in this tread's event loop."""
        if self._context_manager:
            try:
                await self._stack.enter_async_context(self._context_manager)  # type: ignore
            except (TypeError, AttributeError):
                self._stack.enter_context(self._context_manager)  # type: ignore
        # Create the pool in the right event loop.
        self._pool = ThreadSafeTaskPool(size=self._size, timeout=self._timeout)
        await self._stack.enter_async_context(self._pool)

    def post_start(self) -> futures.Future[None]:
        if not self._loop:
            raise RuntimeError(
                f"{self.__class__.__name__}({self._name}) is not running"
            )
        return asyncio.run_coroutine_threadsafe(self._post_start(), self._loop)

    async def _pre_stop(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context managers."""
        await self._stack.__aexit__(exc_type, exc_val, exc_tb)

    def pre_stop(self, exc_type, exc_val, exc_tb) -> futures.Future[None]:
        if not self._loop:
            raise RuntimeError(
                f"{self.__class__.__name__}({self._name}) is not running"
            )
        return asyncio.run_coroutine_threadsafe(
            self._pre_stop(exc_type, exc_val, exc_tb), self._loop
        )

    def stop(self) -> None:
        """Stop the loop and thread."""
        if not self._loop or not self._thread:
            raise RuntimeError(
                f"{self.__class__.__name__}({self._name}) is not running"
            )
        # Stop the pool to break out of `run` method.
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join()
        self._thread = None
        self._loop = None

    def _run_thread(self) -> None:
        """Start the event loop."""
        if not self._loop:
            raise RuntimeError(
                f"{self.__class__.__name__}({self._name}) is not running"
            )
        asyncio.set_event_loop(self._loop)
        self._loop.call_soon(self._initialized.set)
        self._loop.run_forever()

    def create_task(self, coro: Awaitable[T]) -> futures.Future[T]:
        """Create a new task in the pool. Response will be received through the future."""
        if not self._pool:
            raise RuntimeError(
                f"{self.__class__.__name__}({self._name}) is not running"
            )
        return self._pool.create_task(coro)


class ThreadedPoolContextManagerWrapper(AsyncExitStack):
    def __init__(self, get_context_manager: Callable[[], AsyncContextManager]):
        super().__init__()
        self._get_cm = get_context_manager

    async def __aenter__(self):
        await self.enter_async_context(self._get_cm())
        return self
