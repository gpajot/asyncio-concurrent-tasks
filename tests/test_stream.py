import asyncio
from unittest.mock import call

import pytest

from concurrent_tasks.stream import RobustStream


@pytest.fixture
def transport(mocker):
    return mocker.Mock(spec=asyncio.WriteTransport)


@pytest.fixture
def connector(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def backoff(mocker):
    return mocker.AsyncMock()


@pytest.fixture
async def protocol(connector, backoff, transport):
    proto = RobustStream(connector, backoff=backoff)
    connector.side_effect = lambda _: proto.connection_made(transport)
    transport.close.side_effect = lambda: proto.connection_lost(None)
    return proto


async def test_connect(protocol, connector, backoff):
    async with protocol:
        # Write to make sure we wait to be connected.
        await protocol.write(b"a")
    assert connector.call_count == 1
    assert backoff.call_count == 1


async def test_connect_with_error(protocol, transport, connector, backoff, key_error):
    raised = False
    orig_connector_side_effect = connector.side_effect

    def _connect(_):
        nonlocal raised
        if not raised:
            raised = True
            raise ConnectionError()
        orig_connector_side_effect(_)

    connector.side_effect = _connect
    async with protocol:
        # Write to make sure we wait to be connected.
        await protocol.write(b"a")
    assert connector.call_count == 2
    assert backoff.call_count == 2


async def test_reconnect(protocol, transport, connector):
    async with protocol:
        await protocol.write(b"a")
        protocol.connection_lost(ConnectionError())
        await protocol.write(b"b")
    assert connector.call_count == 2
    assert transport.write.call_args_list == [call(b"a"), call(b"b")]


async def test_reader_not_connected(protocol):
    with pytest.raises(RuntimeError, match="is closed"):
        _ = protocol.reader


async def test_read(protocol):
    received_data: list[bytes] = []
    exit_task = None
    async with protocol:
        # Should be ignored as no reader is present yet.
        protocol.data_received(b"a")
        reader = protocol.reader
        asyncio.get_running_loop().call_soon(protocol.data_received, b"bz")
        while True:
            received_data.append(await reader.readuntil(b"z"))
            if len(received_data) >= 2:
                break
            if len(received_data) == 1:
                protocol.data_received(b"c")
                protocol.connection_lost(ConnectionError())
                asyncio.get_running_loop().call_soon(protocol.data_received, b"dz")
            elif len(received_data) == 2:
                protocol.data_received(b"e")
                exit_task = asyncio.create_task(protocol.__aexit__(None, None, None))
    if exit_task:
        await exit_task
    assert received_data == [b"bz", b"cdz"]


async def test_write_not_connected(protocol):
    with pytest.raises(RuntimeError, match="is closed"):
        await protocol.write(b"a")


async def test_write_connected(protocol, transport):
    async with protocol:
        await protocol.write(b"a")
    transport.write.assert_called_once_with(b"a")


async def test_write_pausing(protocol, transport):
    async with protocol:
        protocol.pause_writing()
        asyncio.get_running_loop().call_soon(protocol.resume_writing)
        await protocol.write(b"a")
