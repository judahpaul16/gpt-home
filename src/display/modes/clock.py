"""Clock display mode loop."""

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, Callable

from ..base import Color, DisplayMode
from ..renderers import draw_host_ip_overlay, render_waveform_bars

if TYPE_CHECKING:
    from ..manager import DisplayManager


async def clock_loop(
    manager: "DisplayManager",
    stop_check: Callable[[], bool],
    screensaver_check: Callable[[], bool],
) -> None:
    try:
        while not stop_check() and not screensaver_check():
            if manager._mode not in (DisplayMode.CLOCK, DisplayMode.SMART):
                break

            manager._frame += 1

            if stop_check() or screensaver_check():
                break

            is_smart = manager._mode == DisplayMode.SMART

            async with manager._render_lock:
                d = manager._display
                if not d:
                    break
                if stop_check() or screensaver_check():
                    break

                d.clear_sync(Color(12, 14, 18))
                if is_smart:
                    _render_smart_face(d, manager)
                else:
                    _render_clock_face(d, manager)
                draw_host_ip_overlay(d, manager._get_host_ip())
                d.show_sync()

            await asyncio.sleep(0.016 if is_smart else 0.25)
    except asyncio.CancelledError:
        pass


def _render_smart_face(d, manager: "DisplayManager") -> None:
    now = datetime.now()
    hour_str = now.strftime("%I").lstrip("0")
    minute_str = now.strftime("%M")
    ampm = now.strftime("%p")
    seconds_str = now.strftime("%S")
    date_str = now.strftime("%A, %B %d")

    cx = d.width // 2
    time_size = d.scale_font(70)
    time_y = d.scale_y(35)

    hour_w, hour_h = d.get_text_size(hour_str, time_size)
    minute_w, minute_h = d.get_text_size(minute_str, time_size)
    colon_w, _ = d.get_text_size(":", time_size)

    total_time_w = hour_w + colon_w + minute_w
    time_start_x = cx - total_time_w // 2

    d.draw_text_sync(hour_str, time_start_x + 2, time_y + 2, Color(0, 0, 0), time_size)
    d.draw_text_sync(hour_str, time_start_x, time_y, Color(255, 255, 255), time_size)

    colon_x = time_start_x + hour_w
    d.draw_text_sync(":", colon_x + 2, time_y + 2, Color(0, 0, 0), time_size)
    d.draw_text_sync(":", colon_x, time_y, Color(255, 255, 255), time_size)

    minute_x = colon_x + colon_w
    d.draw_text_sync(minute_str, minute_x + 2, time_y + 2, Color(0, 0, 0), time_size)
    d.draw_text_sync(minute_str, minute_x, time_y, Color(255, 255, 255), time_size)

    ampm_size = d.scale_font(20)
    ampm_w, ampm_h = d.get_text_size(ampm, ampm_size)
    padding_x = d.scale_x(8)
    padding_y = d.scale_y(5)
    pill_w = int(ampm_w + padding_x * 2)
    pill_h = int(ampm_h + padding_y * 2)

    ampm_x = time_start_x + total_time_w + d.scale_x(10)
    ampm_y = time_y + d.scale_y(20)

    d.draw_rounded_rect_sync(
        ampm_x, ampm_y, pill_w, pill_h, d.scale_x(8), Color(45, 55, 72)
    )
    d.draw_text_sync(
        ampm, ampm_x + padding_x, ampm_y + padding_y, Color(99, 179, 237), ampm_size
    )

    sec_size = d.scale_font(14)
    sec_w, _ = d.get_text_size(f":{seconds_str}", sec_size)
    sec_x = ampm_x + (pill_w - sec_w) // 2
    sec_y = ampm_y + pill_h + d.scale_y(4)
    d.draw_text_sync(f":{seconds_str}", sec_x, sec_y, Color(113, 128, 150), sec_size)

    date_size = d.scale_font(20)
    date_w, date_h = d.get_text_size(date_str, date_size)
    date_x = cx - date_w // 2
    date_y = time_y + max(hour_h, minute_h) + d.scale_y(12)
    d.draw_text_sync(date_str, date_x, date_y, Color(160, 174, 192), date_size)

    divider_y = date_y + date_h + d.scale_y(12)
    divider_margin = d.scale_x(40)
    d.fill_rect_sync(divider_margin, divider_y, d.width - divider_margin * 2, 1, Color(40, 50, 60))

    waveform_zone_top = divider_y + d.scale_y(8)
    waveform_zone_bottom = d.height - d.scale_y(10)
    waveform_cy = (waveform_zone_top + waveform_zone_bottom) // 2
    waveform_max_h = (waveform_zone_bottom - waveform_zone_top) // 2

    snapshot = []
    if manager._waveform_observer is not None:
        manager._waveform_observer.set_voice_gated(True)
        snapshot = manager._waveform_observer.get_render_values()

    render_waveform_bars(d, snapshot, voice_gated=True, cy=waveform_cy, max_height=waveform_max_h)


def _render_clock_face(d, manager: "DisplayManager") -> None:
    now = datetime.now()
    hour_str = now.strftime("%I").lstrip("0")
    minute_str = now.strftime("%M")
    ampm = now.strftime("%p")
    seconds_str = now.strftime("%S")
    date_str = now.strftime("%A, %B %d")

    cx, cy = d.get_center()
    time_size = d.scale_font(100)

    hour_w, hour_h = d.get_text_size(hour_str, time_size)
    minute_w, minute_h = d.get_text_size(minute_str, time_size)
    colon_w, _ = d.get_text_size(":", time_size)

    total_time_w = hour_w + colon_w + minute_w
    time_y = cy - d.scale_y(80)
    time_start_x = cx - total_time_w // 2

    d.draw_text_sync(hour_str, time_start_x + 2, time_y + 2, Color(0, 0, 0), time_size)
    d.draw_text_sync(hour_str, time_start_x, time_y, Color(255, 255, 255), time_size)

    colon_x = time_start_x + hour_w
    d.draw_text_sync(":", colon_x + 2, time_y + 2, Color(0, 0, 0), time_size)
    d.draw_text_sync(":", colon_x, time_y, Color(255, 255, 255), time_size)

    minute_x = colon_x + colon_w
    d.draw_text_sync(minute_str, minute_x + 2, time_y + 2, Color(0, 0, 0), time_size)
    d.draw_text_sync(minute_str, minute_x, time_y, Color(255, 255, 255), time_size)

    ampm_size = d.scale_font(24)
    ampm_w, ampm_h = d.get_text_size(ampm, ampm_size)
    padding_x = d.scale_x(12)
    padding_y = d.scale_y(8)
    pill_w = int(ampm_w + padding_x * 2)
    pill_h = int(ampm_h + padding_y * 2)

    ampm_x = time_start_x + total_time_w + d.scale_x(15)
    ampm_y = time_y + d.scale_y(5)

    d.draw_rounded_rect_sync(
        ampm_x, ampm_y, pill_w, pill_h, d.scale_x(12), Color(45, 55, 72)
    )
    d.draw_text_sync(
        ampm, ampm_x + padding_x, ampm_y + padding_y, Color(99, 179, 237), ampm_size
    )

    sec_size = d.scale_font(18)
    sec_w, _ = d.get_text_size(f":{seconds_str}", sec_size)
    sec_x = ampm_x + (pill_w - sec_w) // 2
    sec_y = ampm_y + pill_h + d.scale_y(6)
    d.draw_text_sync(f":{seconds_str}", sec_x, sec_y, Color(113, 128, 150), sec_size)

    date_size = d.scale_font(24)
    date_w, date_h = d.get_text_size(date_str, date_size)
    date_x = cx - date_w // 2
    date_y = time_y + max(hour_h, minute_h) + d.scale_y(20)
    max_date_y = d.height - date_h - d.scale_y(20)
    date_y = min(date_y, max_date_y)
    d.draw_text_sync(date_str, date_x, date_y, Color(160, 174, 192), date_size)
