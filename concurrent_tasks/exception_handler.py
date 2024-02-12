import asyncio
import functools
import logging
import os
import signal
from typing import Any, Callable, Coroutine, Dict, Optional, cast

logger = logging.getLogger(__name__)


class LoopExceptionHandler:
    """Shut down process when an unhandled exception is caught or a signal is received.
    To make this a graceful stop, pass a `stop_func`.

    When creating multiple background tasks, exceptions raised within those will be forwarded directly to the event loop.
    In order to act on those exceptions, we need to use `loop.set_exception_handler`.

    Example minimalistic implementation:
    >>> import asyncio
    >>> from concurrent_tasks import LoopExceptionHandler
    >>>
    >>> async def run():
    >>>     event = asyncio.Event()
    >>>     tasks = []
    >>>     async def _stop():
    >>>         event.set()
    >>>         await asyncio.gather(*tasks)
    >>>     async with LoopExceptionHandler(_stop):
    >>>         # Adding a bunch of tasks here...
    >>>         await event.wait()

    """

    def __init__(self, stop_func: Optional[Callable[[], Coroutine]]):
        self._stop_func = stop_func
        self._shutdown_task: Optional[asyncio.Task] = None
        self._exception_caught: Optional[Exception] = None

    async def __aenter__(self) -> None:
        loop = asyncio.get_running_loop()
        # Add exception/stop handling.
        for sig in (signal.SIGHUP, signal.SIGTERM, signal.SIGINT, signal.SIGQUIT):
            loop.add_signal_handler(
                sig,
                functools.partial(self._handle_exit_signal, sig),
            )
        loop.set_exception_handler(self._handle_exception)

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up any tasks we created."""
        if self._shutdown_task:
            await self._shutdown_task
            self._shutdown_task = None
        if self._exception_caught:
            # Reraise the exception to get proper exit code and stacktrace.
            raise self._exception_caught

    def _handle_exit_signal(self, sig: int) -> None:
        logger.info("received exit signal %r...", sig)
        self._shutdown()

    def _shutdown(self) -> None:
        if not self._stop_func:
            logger.critical("force killing process...")
            os.kill(os.getpid(), signal.SIGKILL)
        if self._shutdown_task:
            logger.critical("already shutting down, force killing process...")
            os.kill(os.getpid(), signal.SIGKILL)
        logger.info("gracefully stopping process...")
        self._shutdown_task = asyncio.create_task(
            cast(Callable[[], Coroutine], self._stop_func)(),
        )

    def _handle_exception(
        self,
        loop: asyncio.AbstractEventLoop,
        context: Dict[str, Any],
    ):
        """Shutdown when an unhandled exception is caught."""
        exc: Optional[Exception]
        try:
            # Try to get a traceback.
            if (future := context.get("future")) and isinstance(future, asyncio.Future):
                future.result()
        except Exception as e:
            exc = e
            logger.critical("caught exception:", exc_info=True)
        else:
            exc = context.get("exception")
            if not exc:
                exc = Exception(context["message"])
            logger.critical("caught exception: %r", exc)
        # Stop here if we are already shutting down, exceptions will have been logged already.
        if not self._shutdown_task:
            self._exception_caught = exc
            self._shutdown()
