import asyncio
from typing import Awaitable, Callable

import pytest
from typing_extensions import Never


@pytest.fixture(scope="session")
def sleep() -> Callable[[float], Awaitable[float]]:
    async def _sleep(duration: float) -> float:
        await asyncio.sleep(duration)
        return duration

    return _sleep


@pytest.fixture(scope="session")
def key_error() -> Callable[[], Awaitable[Never]]:
    async def _error() -> Never:
        raise KeyError()

    return _error
