import pytest

from oneshot_channel import oneshot_channel


@pytest.mark.asyncio
async def test_case_1():
    (sender, receiver) = oneshot_channel()

    # Remove extra references so RAII can work correctly
    del sender
    del receiver


@pytest.mark.asyncio
async def test_case_2():
    (sender, receiver) = oneshot_channel()

    # Remove extra references so RAII can work correctly
    del sender
    del receiver
