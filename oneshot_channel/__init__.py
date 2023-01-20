"""
A one-shot channel is used for sending a single message between asynchronous tasks.
The `oneshot_channel` function is used to create
a `Sender` and `Receiver` handle pair that form the channel.

The `Sender` handle is used by the producer to send the value.
The `Receiver` handle is used by the consumer to receive the value.

Each handle can be used on separate tasks.

Since the `send` method is not async, it can be used anywhere.
This includes sending between two runtimes, and using it from non-async code.

# Examples
>>> from option_and_result import MatchesErr, MatchesOk

>>> async def producer(tx: Sender[int]):
...     if tx.send(3).is_err():
...         print("the receiver dropped")

>>> async def main():
...     tx, rx = oneshot_channel()
...
...     create_task(producer(tx))
...
...     match (await rx).to_matchable():
...         case MatchesOk(v):
...             print(f"got = {v!r}")
...         case MatchesErr(_):
...             print("the sender dropped")

>>> from asyncio import run
>>> run(main())
got = 3


If the sender is dropped without sending, the receiver will fail with `RecvError`:

>>> async def drop_tx(tx: Sender[int]):
...     del tx

>>> async def main():
...     tx, rx = oneshot_channel()
...
...     create_task(drop_tx(tx))
...     del tx # Remove this extra reference to the Sender to ensure proper RAII behavior
...
...     match (await rx).to_matchable():
...         case MatchesOk(_):
...             assert False, "This doesn't happen"
...         case MatchesErr(_):
...             print("the sender dropped")

>>> from asyncio import run
>>> run(main())
the sender dropped
"""


from asyncio import FIRST_COMPLETED, Event, Future, create_task, wait
from dataclasses import dataclass
from typing import Generic, TypeVar

from option_and_result import (
    Err,
    Ok,
    Result,
)

T = TypeVar("T")


@dataclass
class Sender(Generic[T]):
    """
    Sends a value to the associated `Receiver`.

    A pair of both a `Sender` and a `Receiver` are created by the `oneshot_channel` function.

    # Examples
    See the module-level documentation for examples
    """

    _future: Future[T]
    _closed: Event

    def send(self, value: T) -> Result[None, T]:
        """
        Attempts to send a value on this channel, returning it back if it could not be sent.

        Only one value may ever be sent on a oneshot channel.
        It is not marked async because sending a message to an oneshot channel
        never requires any form of waiting.

        A successful send occurs when it is determined that the other end
        of the channel has not hung up already.
        An unsuccessful send would be one where the corresponding receiver
        has already been deallocated.
        Note that a return value of `Err` means that the data will never be received,
        but a return value of Ok does not mean that the data will be received.
        It is possible for the corresponding receiver to hang up
        immediately after this function returns `Ok`.

        # Examples

        >>> from option_and_result import MatchesErr, MatchesOk

        >>> async def producer(tx: Sender[int]):
        ...     if tx.send(3).is_err():
        ...         print("the receiver dropped")

        >>> async def main():
        ...     tx, rx = oneshot_channel()
        ...
        ...     create_task(producer(tx))
        ...
        ...     match (await rx).to_matchable():
        ...         case MatchesOk(v):
        ...             print(f"got = {v!r}")
        ...         case MatchesErr(_):
        ...             print("the sender dropped")

        >>> from asyncio import run
        >>> run(main())
        got = 3
        """

        if self.is_closed():
            return Err(value)

        self._future.set_result(value)
        return Ok(None)

    async def closed(self):
        """
        Waits for the associated `Receiver` handle to close.

        A `Receiver` is closed by either calling `close` explicitly
        or the `Receiver` value is dropped.

        This function is useful when paired with `asyncio.wait` to abort a computation
        when the receiver is no longer interested in the result.

        # Return

        Returns a coroutine which must be awaited on.

        # Examples

        Basic usage

        >>> async def drop_rx(rx: Sender[None]):
        ...     del rx

        >>> async def main():
        ...     tx, rx = oneshot_channel()
        ...
        ...     create_task(drop_rx(rx))
        ...     del rx # Remove this extra reference to the Receiver to ensure proper RAII behavior
        ...
        ...     await tx.closed()
        ...     print("the receiver dropped")

        >>> from asyncio import run
        >>> run(main())
        the receiver dropped
        """

        await self._closed.wait()

    def is_closed(self) -> bool:
        """
        Returns `True` if the associated `Receiver` handle has been dropped.

        A `Receiver` is closed by either calling `close` explicitly
        or the `Receiver` value is dropped.

        If `True` is returned, a call to `send` will always result in an error.

        # Examples

        >>> async def main():
        ...     (tx, rx) = oneshot_channel();
        ...
        ...     assert not tx.is_closed()
        ...
        ...     del rx
        ...
        ...     assert tx.is_closed()
        ...     assert tx.send("never received").is_err()

        >>> from asyncio import run

        >>> run(main())
        """

        return self._closed.is_set()

    def __del__(self):
        self._closed.set()


@dataclass
class TryRecvErrorEmpty:
    """
    The send half of the channel has not yet sent a value.
    """

    def __str__(self):
        return "channel empty"


@dataclass
class TryRecvErrorClosed:
    """
    The send half of the channel was dropped without sending a value.
    """

    def __str__(self):
        return "channel closed"


@dataclass
class RecvError:
    """
    Error returned by `await`ing `Receiver`.

    This error is returned by the receiver when the sender is dropped without sending.
    """

    def __str__(self):
        return "channel closed"


async def _await_future(future: Future[T]) -> T:
    "Await the given future"
    return await future


@dataclass
class Receiver(Generic[T]):
    """
    Receives a value from the associated `Sender`.

    A pair of both a `Sender` and a `Receiver` are created by the `oneshot_channel` function.

    To receive a `Result[T, RecvError]`, `await` the `Receiver` object directly.

    # Examples
    See the module-level documentation for examples
    """

    _future: Future[T]
    _closed: Event
    _taken: bool

    async def _recv(self) -> Result[T, RecvError]:
        if self._taken:
            raise RuntimeError("_recv called more than once")
        self._taken = True

        closed_event = create_task(self._closed.wait())
        get_task = create_task(_await_future(self._future))
        done, _pending = await wait(
            [get_task, closed_event], return_when=FIRST_COMPLETED
        )

        if closed_event in done:
            get_task.cancel()
            return Err(RecvError())

        assert get_task in done
        closed_event.cancel()
        return Ok(get_task.result())

    def __await__(self):
        # Not actually an error but Pylint thinks it is
        return self._recv().__await__()  # pylint:disable=no-member

    def try_recv(self) -> Result[T, TryRecvErrorEmpty | TryRecvErrorClosed]:
        """
        Attempts to receive a value.

        If a pending value exists in the channel, it is returned.
        If no value has been sent, the current task **will not** be registered
        for future notification.

        This function is useful to call from outside the context of an asynchronous task.

        Any send or close event that happens before this call to `try_recv`
        will be correctly returned to the caller.

        # Return
        * `Ok(T)` if a value is pending in the channel.
        * `Err(TryRecvErrorEmpty())` if no value has been sent yet.
        * `Err(TryRecvErrorClosed())` if the sender has dropped without sending a value,
            or if the message has already been received.

        # Examples
        `try_recv` before a value is sent, then after.

        >>> from option_and_result import MatchesErr, MatchesOk

        >>> async def main():
        ...     (tx, rx) = oneshot_channel();
        ...
        ...     match rx.try_recv().to_matchable():
        ...         case MatchesErr(TryRecvErrorEmpty()):
        ...             pass
        ...         case _:
        ...             assert False, "unreachable"
        ...
        ...     tx.send("hello").unwrap()
        ...
        ...     match rx.try_recv().to_matchable():
        ...         case MatchesOk("hello"):
        ...             pass
        ...         case _:
        ...             assert False, "unreachable"

        >>> from asyncio import run
        >>> run(main())


        `try_recv` when the sender is dropped before sending a value

        >>> from option_and_result import MatchesErr

        >>> async def main():
        ...     (tx, rx) = oneshot_channel();
        ...
        ...     del tx
        ...
        ...     match rx.try_recv().to_matchable():
        ...         case MatchesErr(TryRecvErrorClosed()):
        ...             pass
        ...         case _:
        ...             assert False, "unreachable"

        >>> from asyncio import run
        >>> run(main())
        """

        if self._taken:
            # Not actually a type error but Pylance (in VS Code) thinks it is
            return Err(TryRecvErrorClosed())  # type: ignore

        if self._future.done():
            self._taken = True
            return Ok(self._future.result())

        if self._closed.is_set():
            # Not actually a type error but Pylance (in VS Code) thinks it is
            return Err(TryRecvErrorClosed())  # type: ignore

        # Not actually a type error but Pylance (in VS Code) thinks it is
        return Err(TryRecvErrorEmpty())  # type: ignore

    def close(self):
        """
        Prevents the associated `Sender` handle from sending a value.

        Any send operation which happens after calling `close` is guaranteed to fail.
        After calling close, `try_recv` should be called to receive a value
        if one was sent **before** the call to `close` completed.

        This function is useful to perform a graceful shutdown
        and ensure that a value will not be sent into the channel and never received.

        `close` is no-op if a message is already received or the channel is already closed.

        # Examples

        Prevent a value from being sent

        >>> from option_and_result import MatchesErr

        >>> async def main():
        ...     (tx, rx) = oneshot_channel();
        ...
        ...     assert not tx.is_closed()
        ...
        ...     rx.close()
        ...
        ...     assert tx.is_closed()
        ...     assert tx.send("never received").is_err()
        ...
        ...     match rx.try_recv().to_matchable():
        ...         case MatchesErr(value=TryRecvErrorClosed()):
        ...             pass
        ...         case _other:
        ...             assert False, "unreachable"

        >>> from asyncio import run
        >>> run(main())


        Receive a value sent **before** calling `close`

        >>> async def main():
        ...     (tx, rx) = oneshot_channel();
        ...
        ...     assert tx.send("will receive").is_ok()
        ...
        ...     rx.close()
        ...
        ...     msg = rx.try_recv().unwrap()
        ...     assert msg == "will receive"

        >>> from asyncio import run
        >>> run(main())
        """

        self._closed.set()

    def __del__(self):
        self.close()


def oneshot_channel() -> tuple[Sender[T], Receiver[T]]:
    """
    Creates a new one-shot channel for sending single values across asynchronous tasks.

    The function returns separate “send” and “receive” handles.
    The `Sender` handle is used by the producer to send the value.
    The `Receiver` handle is used by the consumer to receive the value.

    Each handle can be used on separate tasks.
    """

    future: Future[T] = Future()

    closed = Event()

    sender = Sender(future, closed)
    receiver = Receiver(future, closed, False)

    return (sender, receiver)
