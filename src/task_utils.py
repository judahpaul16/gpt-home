"""Run fire-and-forget coroutines while retaining a strong reference and
logging their exceptions and failure results."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Coroutine, Optional

_default_logger = logging.getLogger(__name__)

_background_tasks: set[asyncio.Task[Any]] = set()


def spawn_background_task(
    coro: Coroutine[Any, Any, Any],
    *,
    name: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
) -> asyncio.Task[Any]:
    """Schedule ``coro``, keep a reference until it finishes, and log any
    exception it raises or a ``False`` result."""
    log = logger or _default_logger
    task = asyncio.create_task(coro, name=name)
    _background_tasks.add(task)
    task.add_done_callback(lambda t: _handle_done(t, log))
    return task


def _handle_done(task: asyncio.Task[Any], log: logging.Logger) -> None:
    _background_tasks.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        log.error("Background task %s raised: %s", task.get_name(), exc, exc_info=exc)
    elif task.result() is False:
        log.warning("Background task %s reported failure", task.get_name())
