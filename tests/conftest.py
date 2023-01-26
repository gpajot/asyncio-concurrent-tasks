import asyncio
from typing import Any, Callable, Coroutine

import pytest


@pytest.fixture(scope="session")
def sleep() -> Callable[[float], Coroutine[Any, Any, float]]:
    async def _sleep(duration: float) -> float:
        await asyncio.sleep(duration)
        return duration

    return _sleep


@pytest.fixture(scope="session")
def key_error():
    async def _error() -> None:
        raise KeyError()

    return _error()
