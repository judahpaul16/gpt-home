"""Spotify now playing display rendering."""

import asyncio
import logging
import math
import time
from typing import TYPE_CHECKING, Any, Optional

from .base import BaseDisplay, Color
from .palette import Palette, ScrollingText, lerp
from .renderers import draw_host_ip_overlay

if TYPE_CHECKING:
    from .manager import DisplayManager

# Target frame time for 60fps
FRAME_TIME = 1.0 / 60.0


async def spotify_now_playing_loop(manager: "DisplayManager") -> None:
    """Main Spotify now playing display loop."""
    try:
        smoothed_progress = manager._spotify_progress
        album_art_img = None
        last_art_id = None
        last_frame = time.perf_counter()

        track_scroller: Optional[ScrollingText] = None
        artist_scroller: Optional[ScrollingText] = None
        last_track = ""
        last_artist = ""

        while (
            manager._spotify_active
            and not manager._stop_requested
            and not manager._screensaver_active
        ):
            now = time.perf_counter()
            dt = now - last_frame
            last_frame = now

            async with manager._render_lock:
                d = manager._display
                if not d or manager._stop_requested or manager._screensaver_active:
                    break

                d.clear_sync(Color(18, 18, 24))
                cx, cy = d.get_center()
                w = d.width
                h = d.height

                # Layout constants
                margin = d.scale_x(40)
                bottom_margin = d.scale_y(25)

                # Progress bar area (at the very bottom)
                time_size = d.scale_font(14)
                bar_height = d.scale_y(4)
                bar_y = h - bottom_margin - bar_height

                # Time labels above progress bar
                time_label_y = bar_y - d.scale_y(18)

                # Waveform above time labels
                waveform_height = d.scale_y(20)
                waveform_y = time_label_y - d.scale_y(8) - waveform_height

                # Artist text above waveform
                artist_size = d.scale_font(18)
                artist_y = waveform_y - d.scale_y(30)

                # Track text above artist
                track_size = d.scale_font(24)
                track_y = artist_y - d.scale_y(35)

                # Album art fills remaining space at top
                art_top_margin = d.scale_y(35)
                art_bottom_margin = d.scale_y(15)
                available_art_height = track_y - art_top_margin - art_bottom_margin
                art_size = min(d.scale_x(200), d.scale_y(200), available_art_height)
                art_x = cx - art_size // 2
                art_y = art_top_margin

                # Load album art if changed
                album_art_img, last_art_id = _load_album_art(
                    manager, album_art_img, last_art_id, art_size
                )

                # Draw album art
                _draw_album_art(d, album_art_img, art_x, art_y, art_size)

                # Track name with scrolling
                text_area_width = w - margin * 2
                track_text = (
                    manager._spotify_track
                    if manager._spotify_track
                    else "Unknown Track"
                )

                track_scroller, last_track = _update_scroller(
                    track_scroller, track_text, last_track, text_area_width, track_size
                )
                track_scroller.update(dt)
                _draw_scrolling_text(
                    d,
                    track_text,
                    track_scroller,
                    margin,
                    track_y,
                    text_area_width,
                    track_size,
                    Palette.TEXT_PRIMARY,
                    cx,
                )

                # Artist name with scrolling
                artist_text = (
                    manager._spotify_artist
                    if manager._spotify_artist
                    else "Unknown Artist"
                )

                artist_scroller, last_artist = _update_scroller(
                    artist_scroller,
                    artist_text,
                    last_artist,
                    text_area_width,
                    artist_size,
                )
                artist_scroller.update(dt)
                _draw_scrolling_text(
                    d,
                    artist_text,
                    artist_scroller,
                    margin,
                    artist_y,
                    text_area_width,
                    artist_size,
                    Palette.TEXT_SECONDARY,
                    cx,
                )

                # Animated waveform visualization
                _draw_waveform(d, cx, waveform_y, waveform_height, now)

                # Time labels and progress bar
                smoothed_progress = _draw_progress_section(
                    d,
                    manager,
                    margin,
                    w,
                    time_label_y,
                    bar_y,
                    bar_height,
                    time_size,
                    smoothed_progress,
                    dt,
                )

                draw_host_ip_overlay(d, manager._get_host_ip())
                d.show_sync()

            await asyncio.sleep(max(0.001, FRAME_TIME - (time.perf_counter() - now)))

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logging.getLogger("display.spotify").error(
            "Spotify now playing loop error: %s", e
        )


def _load_album_art(
    manager: "DisplayManager",
    current_img: Any,
    last_art_id: Optional[int],
    art_size: int,
) -> tuple:
    """Load album art if it has changed."""
    if manager._spotify_album_art and id(manager._spotify_album_art) != last_art_id:
        last_art_id = id(manager._spotify_album_art)
        try:
            import io

            from PIL import Image

            img = Image.open(io.BytesIO(manager._spotify_album_art))
            current_img = img.resize((art_size, art_size)).convert("RGB")
        except Exception:
            current_img = None
    return current_img, last_art_id


def _draw_album_art(
    d: BaseDisplay, album_art_img: Any, art_x: int, art_y: int, art_size: int
) -> None:
    """Draw album art or placeholder."""
    if album_art_img:
        if hasattr(d, "draw_pil_image_sync"):
            d.draw_pil_image_sync(album_art_img, art_x, art_y)
        else:
            d.fill_rect_sync(art_x, art_y, art_size, art_size, Color(40, 40, 50))
    else:
        d.fill_rect_sync(art_x, art_y, art_size, art_size, Color(35, 35, 45))


def _update_scroller(
    scroller: Optional[ScrollingText],
    text: str,
    last_text: str,
    max_width: int,
    font_size: int,
) -> tuple:
    """Update scrolling text state if text changed."""
    if text != last_text or scroller is None:
        scroller = ScrollingText(text, max_width, font_size, char_width_ratio=0.5)
        last_text = text
    return scroller, last_text


def _draw_scrolling_text(
    d: BaseDisplay,
    text: str,
    scroller: ScrollingText,
    margin: int,
    y: int,
    text_area_width: int,
    font_size: int,
    color: Color,
    center_x: int,
) -> None:
    """Draw text with scrolling if needed."""
    if scroller.needs_scroll:
        scroll_offset = scroller.get_offset()
        d.set_clip(margin, 0, text_area_width, d.height)
        d.draw_text_sync(text, margin - scroll_offset, y, color, font_size)
        d.clear_clip()
    else:
        text_w = len(text) * int(font_size * 0.5)
        d.draw_text_sync(text, center_x - text_w // 2, y, color, font_size)


def _draw_waveform(
    d: BaseDisplay, cx: int, waveform_y: int, waveform_height: int, now: float
) -> None:
    """Draw animated waveform visualization."""
    num_bars = 12
    bar_spacing = d.scale_x(6)
    bar_w = d.scale_x(4)
    total_waveform_width = num_bars * bar_w + (num_bars - 1) * bar_spacing
    waveform_x = cx - total_waveform_width // 2

    t = now * 3.0
    for i in range(num_bars):
        phase = i * 0.4
        wave1 = math.sin(t + phase) * 0.3
        wave2 = math.sin(t * 1.7 + phase * 1.3) * 0.25
        wave3 = math.sin(t * 2.3 + phase * 0.7) * 0.2
        bar_height_pct = 0.25 + abs(wave1 + wave2 + wave3)
        bar_height_pct = min(1.0, max(0.1, bar_height_pct))

        bar_h = int(waveform_height * bar_height_pct)
        bx = waveform_x + i * (bar_w + bar_spacing)
        by = waveform_y + waveform_height - bar_h

        d.fill_rect_sync(bx, by, bar_w, bar_h, Palette.SPOTIFY_GREEN)


def _draw_progress_section(
    d: BaseDisplay,
    manager: "DisplayManager",
    margin: int,
    width: int,
    time_label_y: int,
    bar_y: int,
    bar_height: int,
    time_size: int,
    smoothed_progress: float,
    dt: float,
) -> float:
    """Draw time labels and progress bar, return updated smoothed progress."""
    progress_ms = manager._spotify_progress_ms
    duration_ms = manager._spotify_duration_ms

    if duration_ms > 0:
        prog_min = progress_ms // 60000
        prog_sec = (progress_ms % 60000) // 1000
        dur_min = duration_ms // 60000
        dur_sec = (duration_ms % 60000) // 1000
        start_time = f"{prog_min}:{prog_sec:02d}"
        end_time = f"{dur_min}:{dur_sec:02d}"
    else:
        start_time = "0:00"
        end_time = "-:--"

    # Draw elapsed time (left)
    d.draw_text_sync(start_time, margin, time_label_y, Palette.TEXT_MUTED, time_size)

    # Draw total time (right)
    end_time_w, _ = d.get_text_size(end_time, time_size)
    d.draw_text_sync(
        end_time,
        width - margin - end_time_w,
        time_label_y,
        Palette.TEXT_MUTED,
        time_size,
    )

    # Progress bar
    bar_x = margin
    bar_width = width - margin * 2

    smoothed_progress = lerp(
        smoothed_progress, manager._spotify_progress / 100.0, dt * 8
    )
    d.fill_rect_sync(bar_x, bar_y, bar_width, bar_height, Color(50, 50, 60))
    progress_w = int(bar_width * smoothed_progress)
    if progress_w > 0:
        d.fill_rect_sync(bar_x, bar_y, progress_w, bar_height, Palette.SPOTIFY_GREEN)

    return smoothed_progress
