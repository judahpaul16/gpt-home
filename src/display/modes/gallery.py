"""Gallery display mode loop."""

import asyncio
import time
from typing import TYPE_CHECKING, Callable, List

from ..base import Color, DisplayMode
from ..palette import Palette
from ..renderers import draw_gradient_bg, draw_host_ip_overlay

if TYPE_CHECKING:
    from ..manager import DisplayManager


async def gallery_loop(
    manager: "DisplayManager",
    stop_check: Callable[[], bool],
    screensaver_check: Callable[[], bool],
) -> None:
    """Main gallery display loop for cycling through images."""
    try:
        last_change = time.time()
        last_frame = time.perf_counter()

        while not stop_check() and not screensaver_check():
            if manager._mode != DisplayMode.GALLERY:
                break

            now_time = time.perf_counter()
            dt = min(0.05, now_time - last_frame)
            last_frame = now_time

            async with manager._render_lock:
                d = manager._display
                if not d or stop_check() or screensaver_check():
                    break

                if not manager._gallery_images:
                    _render_no_images(d, manager)
                else:
                    await _render_gallery_image(d, manager)

            # Check if time to advance to next image
            if time.time() - last_change >= manager._gallery_interval:
                if manager._gallery_images:
                    manager._gallery_index = (manager._gallery_index + 1) % len(
                        manager._gallery_images
                    )
                last_change = time.time()

            await asyncio.sleep(0.5)
    except asyncio.CancelledError:
        pass


def _render_no_images(d, manager: "DisplayManager") -> None:
    """Render placeholder when no images are available."""
    draw_gradient_bg(d)
    cx, cy = d.get_center()
    d.draw_text_sync(
        "No images",
        cx - d.scale_x(55),
        cy,
        Palette.TEXT_MUTED,
        d.scale_font(24),
    )
    draw_host_ip_overlay(d, manager._get_host_ip())
    d.show_sync()


async def _render_gallery_image(d, manager: "DisplayManager") -> None:
    """Render the current gallery image."""
    from loguru import logger

    img_path = manager._gallery_images[manager._gallery_index]
    try:
        d.clear_sync(Color(0, 0, 0))
        await d.draw_image(img_path, 0, 0, d.width, d.height)
        draw_host_ip_overlay(d, manager._get_host_ip())
        d.show_sync()
    except Exception as e:
        logger.debug(f"Failed to display image: {e}")
        draw_gradient_bg(d)
        draw_host_ip_overlay(d, manager._get_host_ip())
        d.show_sync()
