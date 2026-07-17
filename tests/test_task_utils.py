import asyncio
import logging

import pytest

from src.task_utils import _background_tasks, spawn_background_task


@pytest.fixture(autouse=True)
def _clear_tasks():
    _background_tasks.clear()
    yield
    _background_tasks.clear()


async def _raise():
    raise RuntimeError("boom")


async def _false():
    return False


async def _true():
    return True


def test_reference_held_then_drained():
    async def main():
        task = spawn_background_task(_true())
        assert task in _background_tasks
        await task
        await asyncio.sleep(0)  # let the done callback run
        assert task not in _background_tasks

    asyncio.run(main())


def test_exception_is_logged(caplog):
    async def main():
        with caplog.at_level(logging.ERROR):
            task = spawn_background_task(_raise(), name="prov")
            await asyncio.gather(task, return_exceptions=True)
            await asyncio.sleep(0)

    asyncio.run(main())
    assert any(
        r.levelname == "ERROR" and "raised" in r.getMessage() for r in caplog.records
    )


def test_false_result_warns(caplog):
    async def main():
        with caplog.at_level(logging.WARNING):
            task = spawn_background_task(_false(), name="prov")
            await asyncio.gather(task, return_exceptions=True)
            await asyncio.sleep(0)

    asyncio.run(main())
    assert any(
        r.levelname == "WARNING" and "failure" in r.getMessage()
        for r in caplog.records
    )


def test_true_result_is_silent(caplog):
    async def main():
        with caplog.at_level(logging.WARNING):
            task = spawn_background_task(_true())
            await asyncio.gather(task, return_exceptions=True)
            await asyncio.sleep(0)

    asyncio.run(main())
    assert not any(r.levelname == "WARNING" for r in caplog.records)
