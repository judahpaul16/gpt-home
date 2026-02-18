"""Waveform display mode loop."""

import asyncio
import time
from typing import TYPE_CHECKING, Callable

from ..base import Color, DisplayMode
from ..renderers import draw_host_ip_overlay

if TYPE_CHECKING:
    from ..manager import DisplayManager


async def waveform_loop(
    manager: "DisplayManager",
    stop_check: Callable[[], bool],
    screensaver_check: Callable[[], bool],
) -> None:
    """Dedicated waveform loop for DisplayMode.WAVEFORM."""
    try:
        last_frame = time.perf_counter()

        while not stop_check() and not screensaver_check():
            if manager._mode != DisplayMode.WAVEFORM:
                break

            now = time.perf_counter()
            dt = min(0.05, now - last_frame)
            last_frame = now

            async with manager._render_lock:
                d = manager._display
                if not d or stop_check() or screensaver_check():
                    break

                d.clear_sync(Color(10, 12, 18))
                manager._render_waveform_inline(d, dt, voice_gated=False)
                draw_host_ip_overlay(d, manager._get_host_ip())
                d.show_sync()

            await asyncio.sleep(0.016)
    except asyncio.CancelledError:
        pass
