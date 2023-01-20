"Test oneshot channels"

from asyncio import create_task, wait_for

import pytest
from option_and_result import MatchesErr

from oneshot_channel import Receiver, TryRecvErrorClosed, oneshot_channel


@pytest.mark.asyncio
async def test_async_send_recv():
    "Test a basic send and receive"

    sender, receiver = oneshot_channel()

    assert sender.send(1).is_ok()
    assert (await receiver).unwrap() == 1


async def drop_rx(receiver: Receiver[None]):
    "Drop the only referenece to the receiver"

    del receiver


@pytest.mark.asyncio
async def test_async_rx_closed():
    """
    Test that waiting for the channel to be closed finishes immediately
    if the channel is already closed
    """

    (sender, receiver) = oneshot_channel()

    create_task(drop_rx(receiver))
    # Remove this extra reference so RAII can work correctly
    del receiver

    await wait_for(sender.closed(), 0.1)


@pytest.mark.asyncio
async def test_close_after_receive():
    "Test that the receiver can be closed even after receiving a value"

    sender, receiver = oneshot_channel()

    sender.send(17).unwrap()

    assert receiver.try_recv().unwrap() == 17
    receiver.close()


@pytest.mark.asyncio
async def test_try_recv_after_completion():
    "Test that attempts to try_recv after getting a value yield closed errors"

    sender, receiver = oneshot_channel()

    sender.send(17).unwrap()

    assert receiver.try_recv().unwrap() == 17

    match (receiver.try_recv()).to_matchable():
        case MatchesErr(TryRecvErrorClosed()):
            pass
        case other:
            assert False, f"received {other!r}"
