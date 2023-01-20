"""
A one-shot channel is used for sending a single message between asynchronous tasks.
The `oneshot_channel` function is used to create
a `Sender` and `Receiver` handle pair that form the channel.

The `Sender` handle is used by the producer to send the value.
The `Receiver` handle is used by the consumer to receive the value.

Each handle can be used on separate tasks.

Since the `send` method is not async, it can be used anywhere.
This includes sending between two runtimes, and using it from non-async code.
"""


from asyncio import FIRST_COMPLETED, Event, Future, Queue, create_task, wait
from dataclasses import dataclass
from typing import AsyncIterator, Generic, TypeVar

from option_and_result import (
    Err,
    MatchesNone,
    MatchesSome,
    NONE,
    Ok,
    Option,
    Result,
    Some,
)

T = TypeVar("T")


@dataclass
class SendError(Generic[T]):
    "Error returned by the `Sender`"

    value: T

    def __str__(self):
        return "channel closed"


@dataclass
class Sender(Generic[T]):
    "Sends values to the associated `Receiver`"

    _future: Future[T]
    _closed: Event

    def send(self, value: T) -> Result[None, SendError[T]]:
        """
        TODO
        """

        raise RuntimeError("TODO")

    async def closed(self):
        """
        TODO
        """

        raise RuntimeError("TODO")

    def is_closed(self):
        """
        TODO
        """

        return self._closed.is_set()

    def __del__(self):
        self._closed.set()


@dataclass
class TryRecvErrorEmpty:
    """
    TODO
    """

    def __str__(self):
        return "TODO"


@dataclass
class TryRecvErrorClosed:
    """
    TODO
    """

    def __str__(self):
        return "TODO"


@dataclass
class RecvError:
    """
    TODO
    """

    def __str__(self):
        return "TODO"


@dataclass
class Receiver(Generic[T]):
    "TODO"

    _future: Future[T]
    _closed: Event

    async def recv(self) -> Result[T, RecvError]:
        """
        TODO
        """

        raise RuntimeError("TODO")

    def try_recv(self) -> Result[T, TryRecvErrorEmpty | TryRecvErrorClosed]:
        """
        TODO
        """

        raise RuntimeError("TODO")

    def close(self):
        """
        TODO
        """

        raise RuntimeError("TODO")

    def __del__(self):
        self.close()


def oneshot_channel() -> tuple[Sender[T], Receiver[T]]:
    """
    TODO
    """

    future: Future[T] = Future()

    closed = Event()

    sender = Sender(future, closed)
    receiver = Receiver(future, closed)

    return (sender, receiver)
