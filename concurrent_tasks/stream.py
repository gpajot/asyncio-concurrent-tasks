import asyncio
import logging
import weakref
from collections import deque
from typing import Awaitable, Callable, Optional

from concurrent_tasks.background import BackgroundTask

logger = logging.getLogger(__name__)


class RobustStreamReader(asyncio.StreamReader):
    def __init__(self, connected_waiter: Callable[[], Awaitable]):
        super().__init__()
        self._connected_waiter = connected_waiter
        self._transport: Optional[asyncio.BaseTransport] = None

    def set_transport(self, transport: asyncio.BaseTransport) -> None:
        self._transport = transport

    def clear_transport(self) -> None:
        self._transport = None

    async def _wait_for_data(self, func_name: str) -> None:
        if not self._transport:
            await self._connected_waiter()
            assert self._transport
        else:
            await super()._wait_for_data(func_name)  # type: ignore[misc]

    async def readuntil(self, separator=b"\n"):
        while True:
            try:
                return await super().readuntil(separator)
            except asyncio.IncompleteReadError as e:
                # If transport disconnected, ignore the error.
                if self._transport:
                    raise
                elif e.partial:
                    logger.warning("connection closed before finishing reading: %r", e)


class RobustStream(asyncio.Protocol):
    """Robust stream around asyncio connections.
    Reconnection will be made seamlessly for readers and writers."""

    def __init__(
        self,
        connector: Callable[[Callable[[], asyncio.Protocol]], Awaitable],
        name: str = "",
        backoff: Optional[Callable[[], Awaitable]] = None,
        timeout: Optional[float] = None,
    ):
        self._connector = connector
        self._name = name or self.__class__.__name__
        self._backoff = backoff
        self._timeout = timeout

        self._closing = False
        self._closed = asyncio.Event()
        self._closed.set()
        self._last_exc: Optional[Exception] = None
        self._connected = asyncio.Event()
        self._connect_task = BackgroundTask(self._connect)

        self._transport: Optional[asyncio.Transport] = None
        self._reader_wr: Optional[weakref.ReferenceType[RobustStreamReader]] = None
        self._writing_paused = False
        self._write_waiters: deque[asyncio.Future[None]] = deque()

    async def __aenter__(self):
        self._closing = False
        self._closed.clear()
        self._connect_task.create()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self._closing = True
        self._connect_task.cancel()
        if self._transport:
            self._transport.close()
            # Wait until `connection_lost` was called.
            try:
                await asyncio.wait_for(self._closed.wait(), timeout=self._timeout)
            except asyncio.TimeoutError:
                logger.error(
                    "%s: timeout waiting for transport to close",
                    self._name,
                )
        if reader := self._reader():
            # Reader should have been cleared in `connection_lost`,
            # but in case it finished because of a timeout, make sure.
            reader.feed_eof()
            reader.clear_transport()
            self._reader_wr = None
        for waiter in self._write_waiters:
            if not waiter.done():
                if exc_val:
                    waiter.set_exception(exc_val)
                else:
                    waiter.set_result(None)

    def _reader(self) -> Optional[RobustStreamReader]:
        if self._reader_wr:
            return self._reader_wr()
        return None

    async def _connect(self) -> None:
        self._last_exc = None
        while True:
            if self._backoff:
                await self._backoff()
            try:
                await asyncio.wait_for(self._connector(lambda: self), self._timeout)
                break
            except Exception:
                logger.warning(
                    "%s: could not connect, retrying...",
                    self._name,
                    exc_info=True,
                )

    def connection_made(self, transport: asyncio.Transport) -> None:  # type: ignore[override]
        self._transport = transport
        if reader := self._reader():
            reader.set_transport(transport)
        self._connected.set()
        for waiter in self._write_waiters:
            if not waiter.done():
                waiter.set_result(None)
        logger.debug("%s: connected", self._name)

    def connection_lost(self, exc: Optional[Exception]) -> None:
        # Store errors to allow subclasses to handle them in `_connect` as this function is not async.
        self._last_exc = exc
        self._connected.clear()
        self._transport = None
        self._connect_task.cancel()
        if self._closing:
            logger.debug("%s: disconnected", self._name)
            if reader := self._reader():
                reader.feed_eof()
                reader.clear_transport()
            # Notify the transport was properly closed.
            self._closed.set()
        else:
            logger.warning(
                "%s: connection lost: %s, reconnecting...",
                self._name,
                exc or "(no exception)",
            )
            # Attempt to reconnect.
            if reader := self._reader():
                reader.clear_transport()
            self._connect_task.create()

    def data_received(self, data: bytes) -> None:
        if reader := self._reader():
            reader.feed_data(data)

    @property
    def reader(self) -> asyncio.StreamReader:
        if self._reader():
            raise RuntimeError(f"{self._name} already has a reader")
        if self._closed.is_set():
            raise RuntimeError(f"{self._name} is closed")
        if self._closing:
            raise RuntimeError(f"{self._name} is closing")
        reader = RobustStreamReader(self._connected.wait)
        self._reader_wr = weakref.ref(reader)
        if self._transport:
            reader.set_transport(self._transport)
        return reader

    def pause_writing(self) -> None:
        self._writing_paused = True

    def resume_writing(self) -> None:
        self._writing_paused = False
        for waiter in self._write_waiters:
            if not waiter.done():
                waiter.set_result(None)

    async def write(self, data: bytes) -> None:
        if self._closed.is_set():
            raise RuntimeError(f"{self._name} is closed")
        if self._closing:
            raise RuntimeError(f"{self._name} is closing")
        await self._connected.wait()
        assert self._transport
        self._transport.write(data)
        # Flow control.
        if self._writing_paused:
            waiter = asyncio.get_running_loop().create_future()
            self._write_waiters.append(waiter)
            try:
                await waiter
            finally:
                self._write_waiters.remove(waiter)
