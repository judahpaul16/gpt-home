"""State management for non-mode displays (supports_modes=False).

Each AuxiliaryDisplay wraps a BaseDisplay and owns its lifecycle:
screensaver, Spotify now-playing, waveform, word-by-word text,
and state animations (Connecting/Listening).

Both SSD1306 (I2C) and ST7789 (SPI LCD) displays are managed here.
"""

import asyncio
import logging
import random
import subprocess
import time
from datetime import datetime
from typing import Dict, List, Optional

from .base import BaseDisplay, Color, Colors, ScreenType
from .detection import detect_displays
from .factory import DisplayFactory
from .palette import Palette, ScrollingText
from .renderers import get_cpu_temp, render_waveform_bars, wrap_text

logger = logging.getLogger("display.auxiliary")

_displays: Dict[str, "AuxiliaryDisplay"] = {}


def _get_host_ip() -> str:
    try:
        result = subprocess.run(
            ["nsenter", "-t", "1", "-n", "hostname", "-I"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().split()[0]
    except Exception:
        pass
    try:
        with open("/run/gpt-home/host-ip", "r") as f:
            ip = f.read().strip()
            if ip:
                return ip
    except Exception:
        pass
    return ""


class AuxiliaryDisplay:
    def __init__(self, display: BaseDisplay):
        self.display = display
        self._lock = asyncio.Lock()

        self._last_activity_time = time.time()
        self._screensaver_active = False
        self._screensaver_task: Optional[asyncio.Task] = None
        self._screensaver_render_task: Optional[asyncio.Task] = None
        self._monitor_task: Optional[asyncio.Task] = None

        self._spotify_active = False
        self._spotify_track = ""
        self._spotify_artist = ""
        self._spotify_progress_ms = 0
        self._spotify_duration_ms = 0
        self._spotify_album_art_url = ""
        self._spotify_album_art_img = None
        self._spotify_album_art_loading = ""
        self._spotify_render_task: Optional[asyncio.Task] = None
        self._spotify_title_scroller: Optional[ScrollingText] = None
        self._spotify_artist_scroller: Optional[ScrollingText] = None

        self._waveform_observer = None
        self._dashboard_task: Optional[asyncio.Task] = None
        self._weather_task: Optional[asyncio.Task] = None

    @property
    def is_color(self) -> bool:
        return self.display.info.screen_type != ScreenType.SSD1306

    @property
    def content_y(self) -> int:
        if self.is_color:
            return 28
        return 10

    @property
    def header_height(self) -> int:
        if self.is_color:
            return 24
        return 9

    def _chars_per_line(self) -> int:
        if self.is_color:
            return (self.display.width - 20) // 9
        return self.display.width // 6

    def _max_text_lines(self) -> int:
        content_height = self.display.height - self.content_y
        line_height = 20 if self.is_color else 10
        return content_height // line_height

    def _text_line_height(self) -> int:
        return 20 if self.is_color else 10

    def _text_font_size(self) -> int:
        return 16 if self.is_color else 10

    # ── Header ──

    def draw_header(self) -> None:
        if self.is_color:
            self.display.fill_rect_sync(
                0, 0, self.display.width, self.header_height, Colors.BLACK
            )
            font_size = max(10, self.display.width // 20)
            pad = max(6, self.display.width // 30)
            ip = _get_host_ip()
            if ip:
                self.display.draw_text_sync(
                    ip, pad, 3, Color(100, 110, 130), font_size
                )
            cpu_temp = get_cpu_temp()
            if cpu_temp is not None:
                temp_str = f"{cpu_temp}\u00b0C"
                tw, _ = self.display.get_text_size(temp_str, font_size)
                self.display.draw_text_sync(
                    temp_str, self.display.width - tw - pad, 3,
                    Color(100, 110, 130), font_size,
                )
        else:
            self.display.fill_rect_sync(
                0, 0, self.display.width, self.header_height, Colors.BLACK
            )
            ip = _get_host_ip()
            if ip:
                self.display.draw_text_sync(ip, 0, 0, Colors.WHITE, 10)
            cpu_temp = get_cpu_temp()
            if cpu_temp is not None:
                temp_str = f"{cpu_temp}C"
                temp_x = self.display.width - len(temp_str) * 6 - 2
                self.display.draw_text_sync(temp_str, temp_x, 0, Colors.WHITE, 10)

    def _draw_idle_bars(self) -> None:
        bar_count = 16
        bar_width = 6
        bar_spacing = 2
        total_width = bar_count * (bar_width + bar_spacing) - bar_spacing
        start_x = (self.display.width - total_width) // 2
        base_y = self.display.height - 1
        min_bar_height = 2
        for i in range(bar_count):
            x = start_x + i * (bar_width + bar_spacing)
            self.display.fill_rect_sync(x, base_y - min_bar_height, bar_width, min_bar_height, Colors.WHITE)

    async def restore_header(self) -> None:
        self._stop_weather()
        async with self._lock:
            self.display.clear_sync()
            if self.is_color:
                self._render_dashboard_frame()
            else:
                self.draw_header()
                self._draw_idle_bars()
            await asyncio.get_event_loop().run_in_executor(
                None, self.display.show_sync
            )
        if self.is_color:
            self._start_dashboard()

    # ── Dashboard (ST7789 idle view) ──

    def _render_dashboard_frame(self) -> None:
        w, h = self.display.width, self.display.height
        clock_bottom = self._draw_clock_block(80)
        date_str = datetime.now().strftime("%a %b %-d")
        dw, _ = self.display.get_text_size(date_str, 14)
        self.display.draw_text_sync(
            date_str, (w - dw) // 2, clock_bottom + 10, Palette.TEXT_MUTED, 14,
        )
        self.display.fill_rect_sync(20, h - 48, w - 40, 1, Color(40, 40, 50))
        self._draw_info_row(h - 34)

    def _start_dashboard(self) -> None:
        if not self.is_color:
            return
        self._stop_dashboard()
        self._dashboard_task = asyncio.create_task(self._dashboard_loop())

    def _stop_dashboard(self) -> None:
        if self._dashboard_task and not self._dashboard_task.done():
            self._dashboard_task.cancel()
        self._dashboard_task = None

    async def _dashboard_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(10)
                if self._screensaver_active or self._spotify_active:
                    continue
                async with self._lock:
                    self.display.clear_sync()
                    self._render_dashboard_frame()
                    await asyncio.get_event_loop().run_in_executor(
                        None, self.display.show_sync
                    )
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Dashboard render error: %s", e)

    # ── Activity / Screensaver ──

    def register_activity(self) -> None:
        self._last_activity_time = time.time()
        if self._screensaver_active:
            logger.debug("Waking auxiliary screensaver due to activity")
            self._screensaver_active = False
            if self._screensaver_render_task and not self._screensaver_render_task.done():
                self._screensaver_render_task.cancel()
            self._screensaver_render_task = None
            self.display.clear_sync()
            if self.is_color:
                self._render_dashboard_frame()
            else:
                self.draw_header()
            self.display.show_sync()
            if self.is_color:
                self._start_dashboard()

    async def check_screensaver(self, settings: dict) -> None:
        if not settings.get("screensaver_enabled", True):
            return
        if self._screensaver_active or self._spotify_active:
            return

        timeout = float(settings.get("screensaver_timeout", 300))
        elapsed = time.time() - self._last_activity_time

        if elapsed >= timeout:
            self._screensaver_active = True
            self._stop_dashboard()
            self._stop_weather()
            logger.debug(
                "Auxiliary screensaver activated after %.0fs of inactivity", elapsed
            )
            self._screensaver_render_task = asyncio.create_task(
                self._screensaver_animation()
            )

    async def stop_screensaver(self) -> None:
        if not self._screensaver_active:
            return
        self._screensaver_active = False
        if self._screensaver_render_task and not self._screensaver_render_task.done():
            self._screensaver_render_task.cancel()
        self._screensaver_render_task = None
        self._last_activity_time = time.time()
        await self.restore_header()

    async def _screensaver_animation(self) -> None:
        try:
            from src.common import load_settings
            style = load_settings().get("screensaver_style", "starfield").lower()
            await self._run_screensaver_style(style)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Auxiliary screensaver error: %s", e)
            self._screensaver_active = False
        finally:
            if not self._screensaver_active:
                await self.restore_header()

    async def _run_screensaver_style(self, style: str) -> None:
        from .modes.screensaver import init_style, render_style
        from src.common import load_settings

        d = self.display
        settings = load_settings()

        if style not in ("starfield", "matrix", "bounce", "fade"):
            style = "starfield"

        state = init_style(d, style, settings)

        if not self.is_color and style == "fade":
            state["fade"]["blobs"] = state["fade"]["blobs"][:3]
            state["fade"]["particles"] = state["fade"]["particles"][:15]

        last_frame = time.perf_counter()
        fps = 20 if not self.is_color else 30
        frame_time = 1.0 / fps

        while self._screensaver_active:
            now = time.perf_counter()
            dt = now - last_frame
            last_frame = now

            async with self._lock:
                await render_style(d, style, dt, state)

                if not self.is_color:
                    self._dither_to_mono()

                await asyncio.get_event_loop().run_in_executor(
                    None, d.show_sync
                )

            elapsed = time.perf_counter() - now
            await asyncio.sleep(max(0.001, frame_time - elapsed))

    def _dither_to_mono(self) -> None:
        img = getattr(self.display, "_image", None)
        if img is None:
            return
        mono = img.convert("1")
        img.paste(mono.convert(img.mode))

    def start_screensaver_monitor(self) -> None:
        if self._monitor_task is None or self._monitor_task.done():
            self._monitor_task = asyncio.create_task(self._screensaver_monitor_loop())
            logger.debug("Auxiliary screensaver monitor started for %s", self.display.info.screen_type.value)

    async def _screensaver_monitor_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(10)
                from src.common import load_settings
                settings = load_settings()
                await self.check_screensaver(settings)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Auxiliary screensaver monitor error: %s", e)

    # ── State display (Connecting / Listening / etc.) ──

    async def display_state(self, state: str, stop_event: asyncio.Event) -> None:
        self._stop_dashboard()
        self._stop_weather()
        self.register_activity()

        if state == "Listening":
            await self._display_waveform(stop_event)
            return

        font_size = self._text_font_size()
        cy = self.content_y + (self.display.height - self.content_y) // 2

        while not stop_event.is_set():
            for i in range(4):
                if stop_event.is_set():
                    return
                async with self._lock:
                    self.display.fill_rect_sync(
                        0, self.content_y,
                        self.display.width, self.display.height - self.content_y,
                        Colors.BLACK,
                    )
                    text = state + "." * i
                    if self.is_color:
                        tw, _ = self.display.get_text_size(text, font_size)
                        tx = (self.display.width - tw) // 2
                        self.display.draw_text_sync(
                            text, tx, cy, Colors.WHITE, font_size
                        )
                    else:
                        self.display.draw_text_sync(text, 0, 20, Colors.WHITE, 10)
                    await asyncio.get_event_loop().run_in_executor(
                        None, self.display.show_sync
                    )
                await asyncio.sleep(0.5)

    # ── Waveform ──

    def _get_waveform_observer(self):
        if self._waveform_observer is None:
            try:
                from src.waveform import I2CDisplayWaveformObserver, get_waveform_mediator
                self._waveform_observer = I2CDisplayWaveformObserver()
                mediator = get_waveform_mediator()
                mediator.register_observer(self._waveform_observer)
            except Exception as e:
                logger.error("Failed to init waveform observer: %s", e)
        return self._waveform_observer

    async def _display_waveform(self, stop_event: asyncio.Event) -> None:
        if self._spotify_active:
            while not stop_event.is_set():
                await asyncio.sleep(0.1)
            return

        if self._screensaver_active:
            await self.stop_screensaver()
        self._stop_weather()

        observer = self._get_waveform_observer()
        if observer is None:
            return

        async with self._lock:
            self.display.clear_sync()
            if self.is_color:
                self._render_dashboard_frame()
            else:
                self.draw_header()
            await asyncio.get_event_loop().run_in_executor(
                None, self.display.show_sync
            )

        if self.is_color:
            await self._color_waveform(observer, stop_event)
        else:
            await self._mono_waveform(observer, stop_event)

    def _draw_clock_block(self, y_top: int) -> int:
        w = self.display.width
        now = datetime.now()
        time_str = now.strftime("%-I:%M")
        ampm_str = now.strftime("%p")
        tw, th = self.display.get_text_size(time_str, 40)
        aw, ah = self.display.get_text_size(ampm_str, 14)
        total_tw = tw + 4 + aw
        time_x = (w - total_tw) // 2
        self.display.draw_text_sync(
            time_str, time_x, y_top, Palette.TEXT_PRIMARY, 40,
        )
        self.display.draw_text_sync(
            ampm_str, time_x + tw + 4, y_top + th - ah - 6, Palette.TEXT_MUTED, 14,
        )
        return y_top + th

    def _draw_info_row(self, y: int) -> None:
        w = self.display.width
        ip = _get_host_ip()
        if ip:
            self.display.draw_text_sync(ip, 10, y, Palette.TEXT_MUTED, 14)
        cpu_temp = get_cpu_temp()
        if cpu_temp is not None:
            temp_str = f"{cpu_temp}\u00b0C"
            ttw, _ = self.display.get_text_size(temp_str, 14)
            self.display.draw_text_sync(
                temp_str, w - ttw - 10, y, Palette.TEXT_MUTED, 14,
            )

    def _stop_weather(self) -> None:
        if self._weather_task and not self._weather_task.done():
            self._weather_task.cancel()
        self._weather_task = None

    async def show_weather(self, location: str = None) -> None:
        if not self.is_color:
            return
        self._stop_dashboard()
        self._stop_weather()
        self._weather_task = asyncio.create_task(self._weather_animation(location))

    async def _weather_animation(self, location: str = None) -> None:
        from .weather import (
            draw_weather_gradient,
            draw_weather_icon_fancy,
            fetch_weather_data,
            get_weather_colors,
        )

        w, h = self.display.width, self.display.height

        async with self._lock:
            self.display.clear_sync()
            lw, _ = self.display.get_text_size("Loading...", 16)
            self.display.draw_text_sync(
                "Loading...", (w - lw) // 2, h // 2, Palette.TEXT_MUTED, 16,
            )
            await asyncio.get_event_loop().run_in_executor(None, self.display.show_sync)

        try:
            data = await fetch_weather_data(location=location)
        except Exception:
            data = {}

        condition = data.get("condition", "Clear")
        temp = data.get("temperature")
        loc = data.get("location", "")
        high = data.get("high")
        low = data.get("low")

        phase = 0.0
        start_time = time.time()

        try:
            while time.time() - start_time < 20:
                phase += 0.05
                hour = datetime.now().hour
                top_color, bottom_color, _, _ = get_weather_colors(condition, hour)

                async with self._lock:
                    draw_weather_gradient(self.display, top_color, bottom_color)

                    icon_size = 80
                    icon_x = (w - icon_size) // 2
                    icon_y = 30
                    draw_weather_icon_fancy(
                        self.display, condition, icon_x, icon_y, icon_size, phase,
                    )

                    shadow = Color(0, 0, 0)

                    temp_str = f"{temp}\u00b0" if temp is not None else "--\u00b0"
                    tw, _ = self.display.get_text_size(temp_str, 36)
                    tx = (w - tw) // 2
                    ty = icon_y + icon_size + 10
                    self.display.draw_text_sync(temp_str, tx + 1, ty + 1, shadow, 36)
                    self.display.draw_text_sync(temp_str, tx, ty, Colors.WHITE, 36)

                    info_y = icon_y + icon_size + 52
                    cond_display = condition.title()
                    cw, _ = self.display.get_text_size(cond_display, 16)
                    cx = (w - cw) // 2
                    self.display.draw_text_sync(cond_display, cx + 1, info_y + 1, shadow, 16)
                    self.display.draw_text_sync(cond_display, cx, info_y, Color(100, 220, 255), 16)

                    if high is not None and low is not None:
                        hl_str = f"\u2191{high}\u00b0 \u2193{low}\u00b0"
                        hw, _ = self.display.get_text_size(hl_str, 13)
                        hx = (w - hw) // 2
                        self.display.draw_text_sync(hl_str, hx + 1, info_y + 23, shadow, 13)
                        self.display.draw_text_sync(hl_str, hx, info_y + 22, Color(210, 220, 240), 13)

                    if loc:
                        locw, _ = self.display.get_text_size(loc, 16)
                        lx = (w - locw) // 2
                        self.display.draw_text_sync(loc, lx + 1, h - 21, shadow, 16)
                        self.display.draw_text_sync(loc, lx, h - 22, Color(180, 190, 210), 16)

                    await asyncio.get_event_loop().run_in_executor(
                        None, self.display.show_sync,
                    )
                await asyncio.sleep(0.033)
        except asyncio.CancelledError:
            return
        finally:
            self._weather_task = None

        async with self._lock:
            self.display.clear_sync()
            self._render_dashboard_frame()
            await asyncio.get_event_loop().run_in_executor(
                None, self.display.show_sync,
            )
        self._start_dashboard()

    def _render_waveform_bars(self, snapshot, w: int, h: int, cy_override: int = 0) -> None:
        bar_count = 24
        bar_width = 5
        spacing = 3
        total_bw = bar_count * (bar_width + spacing) - spacing
        start_x = (w - total_bw) // 2
        waveform_cy = cy_override if cy_override else (h * 2 // 3)
        max_bar_h = 40
        n_vals = len(snapshot) if snapshot else 0

        for i in range(bar_count):
            idx = int(i * n_vals / bar_count) if n_vals > bar_count else i
            val = snapshot[min(idx, n_vals - 1)] if idx < n_vals and n_vals > 0 else 0.0
            half_h = max(1, int(val * max_bar_h))
            x = start_x + i * (bar_width + spacing)
            y = waveform_cy - half_h
            bar_h = half_h * 2

            if val > 0.005:
                intensity = min(1.0, val * 1.5)
                pos = i / max(1, bar_count - 1)
                r = int(50 + 180 * intensity * (0.3 + 0.7 * pos))
                g = int(120 + 100 * intensity * (1.0 - 0.3 * pos))
                b = int(200 + 55 * intensity)
                self.display.fill_rect_sync(
                    x, y, bar_width, bar_h,
                    Color(min(255, r), min(255, g), min(255, b)),
                )

    async def _color_waveform(self, observer, stop_event: asyncio.Event) -> None:
        w, h = self.display.width, self.display.height

        while not stop_event.is_set():
            snapshot = observer.get_render_values()
            current_max = max(snapshot) if snapshot else 0.0
            if current_max > 0.02:
                self.register_activity()

            async with self._lock:
                self.display.clear_sync()
                clock_bottom = self._draw_clock_block(30)

                lw, lh = self.display.get_text_size("Listening", 16)
                label_y = clock_bottom + 8
                self.display.draw_text_sync(
                    "Listening", (w - lw) // 2, label_y,
                    Palette.ACCENT_CYAN, 16,
                )

                waveform_top = label_y + lh + 8
                waveform_bottom = h - 48
                waveform_cy = (waveform_top + waveform_bottom) // 2
                self._render_waveform_bars(snapshot, w, h, waveform_cy)

                self.display.fill_rect_sync(20, h - 48, w - 40, 1, Color(40, 40, 50))
                self._draw_info_row(h - 34)

                await asyncio.get_event_loop().run_in_executor(
                    None, self.display.show_sync
                )
            await asyncio.sleep(0.033)

    async def _mono_waveform(self, observer, stop_event: asyncio.Event) -> None:
        bar_count = 16
        bar_width = 6
        bar_spacing = 2
        total_width = bar_count * (bar_width + bar_spacing) - bar_spacing
        start_x = (self.display.width - total_width) // 2
        base_y = self.display.height - 1
        max_bar_height = 18
        min_bar_height = 2

        while not stop_event.is_set():
            snapshot = observer.get_render_values()
            current_max = max(snapshot) if snapshot else 0.0
            if current_max > 0.02:
                self.register_activity()

            async with self._lock:
                self.display.fill_rect_sync(
                    0, self.content_y,
                    self.display.width, self.display.height - self.content_y,
                    Colors.BLACK,
                )
                self.display.draw_text_sync("Listening", 34, 10, Colors.WHITE, 10)

                for i in range(bar_count):
                    idx1 = i * 2
                    idx2 = i * 2 + 1
                    val = (snapshot[idx1] + snapshot[idx2]) / 2.0
                    bar_height = max(min_bar_height, int(val * max_bar_height))
                    x = start_x + i * (bar_width + bar_spacing)
                    y = base_y - bar_height
                    self.display.fill_rect_sync(x, y, bar_width, bar_height, Colors.WHITE)

                await asyncio.get_event_loop().run_in_executor(
                    None, self.display.show_sync
                )
            await asyncio.sleep(0.033)

    # ── Word-by-word response text ──

    async def show_word(self, word: str, current_words: list) -> None:
        if self.is_color and (self._spotify_active or self._weather_task):
            return
        self._stop_dashboard()
        current_words.append(word)
        text = " ".join(current_words)
        lines = wrap_text(text, self._chars_per_line())
        max_lines = self._max_text_lines()
        visible = lines[-max_lines:]
        line_height = self._text_line_height()
        font_size = self._text_font_size()

        async with self._lock:
            if self.is_color:
                self.display.clear_sync()
                total_h = len(visible) * line_height
                start_y = max(10, (self.display.height - total_h) // 2)
                for i, line in enumerate(visible):
                    y = start_y + i * line_height
                    lw, _ = self.display.get_text_size(line, font_size)
                    x = max(0, (self.display.width - lw) // 2)
                    self.display.draw_text_sync(line, x, y, Colors.WHITE, font_size)
            else:
                self.display.fill_rect_sync(
                    0, self.content_y,
                    self.display.width, self.display.height - self.content_y,
                    Colors.BLACK,
                )
                for i, line in enumerate(visible):
                    y = self.content_y + i * line_height
                    self.display.draw_text_sync(line, 0, y, Colors.WHITE, font_size)
            await asyncio.get_event_loop().run_in_executor(
                None, self.display.show_sync
            )

    async def show_message(self, lines: List[str]) -> None:
        if self.is_color and (self._spotify_active or self._weather_task):
            return
        self._stop_dashboard()
        font_size = self._text_font_size()
        line_height = self._text_line_height()
        max_lines = self._max_text_lines()
        visible = lines[-max_lines:]

        async with self._lock:
            self.display.clear_sync()
            if self.is_color:
                total_h = len(visible) * line_height
                start_y = max(10, (self.display.height - total_h) // 2)
                for i, line in enumerate(visible):
                    y = start_y + i * line_height
                    lw, _ = self.display.get_text_size(line, font_size)
                    x = max(0, (self.display.width - lw) // 2)
                    self.display.draw_text_sync(line, x, y, Colors.WHITE, font_size)
            else:
                self.draw_header()
                for i, line in enumerate(visible):
                    y = self.content_y + i * line_height
                    self.display.draw_text_sync(line, 0, y, Colors.WHITE, font_size)
            await asyncio.get_event_loop().run_in_executor(
                None, self.display.show_sync
            )

    # ── Spotify now-playing ──

    async def show_spotify(
        self, track: str, artist: str, progress_ms: int = 0, duration_ms: int = 0,
        album_art_url: str = "",
    ) -> None:
        track_changed = track != self._spotify_track or artist != self._spotify_artist

        self._spotify_track = track
        self._spotify_artist = artist
        self._spotify_progress_ms = progress_ms
        self._spotify_duration_ms = duration_ms

        if album_art_url and album_art_url != self._spotify_album_art_url:
            self._spotify_album_art_url = album_art_url
            if self.is_color:
                asyncio.create_task(self._fetch_album_art(album_art_url))

        if track_changed and self.is_color:
            max_width = self.display.width - 20
            self._spotify_title_scroller = ScrollingText(track, max_width, 14)
            self._spotify_artist_scroller = ScrollingText(artist, max_width, 12)

        self._last_activity_time = time.time()
        self._stop_dashboard()
        self._stop_weather()

        if not self._spotify_active:
            self._spotify_active = True
            if self._screensaver_active:
                self.register_activity()
            if self._spotify_render_task is None or self._spotify_render_task.done():
                self._spotify_render_task = asyncio.create_task(
                    self._spotify_render_loop()
                )

    async def stop_spotify(self) -> None:
        self._spotify_active = False
        self._spotify_track = ""
        self._spotify_artist = ""
        if self._spotify_render_task and not self._spotify_render_task.done():
            self._spotify_render_task.cancel()
            try:
                await self._spotify_render_task
            except asyncio.CancelledError:
                pass
        self._spotify_render_task = None
        self._spotify_album_art_img = None
        self._spotify_album_art_url = ""
        self._spotify_album_art_loading = ""
        await self.restore_header()

    async def _fetch_album_art(self, url: str) -> None:
        if url == self._spotify_album_art_loading:
            return
        self._spotify_album_art_loading = url
        try:
            import io
            import aiohttp
            from PIL import Image
            art_size = min(self.display.width, self.display.height - 80)
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        img = Image.open(io.BytesIO(data))
                        self._spotify_album_art_img = img.resize(
                            (art_size, art_size)
                        ).convert("RGB")
        except Exception as e:
            logger.debug("Album art fetch failed: %s", e)

    async def _spotify_render_loop(self) -> None:
        last_frame = time.time()
        try:
            if self.is_color:
                await self._color_spotify_render(last_frame)
            else:
                await self._mono_spotify_render(last_frame)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Spotify render error: %s", e)
        finally:
            self._spotify_active = False

    async def _color_spotify_render(self, last_frame: float) -> None:
        w, h = self.display.width, self.display.height
        title_font = 14
        artist_font = 12
        time_font = 10
        bar_height = 4
        margin = 18
        art_size = min(w, h - 74)
        art_x = (w - art_size) // 2

        while self._spotify_active:
            now = time.time()
            dt = now - last_frame
            last_frame = now

            if self._spotify_title_scroller:
                self._spotify_title_scroller.update(dt)
            if self._spotify_artist_scroller:
                self._spotify_artist_scroller.update(dt)

            async with self._lock:
                self.display.clear_sync()

                if self._spotify_album_art_img and hasattr(self.display, "draw_pil_image_sync"):
                    self.display.draw_pil_image_sync(self._spotify_album_art_img, art_x, 0)
                else:
                    self.display.fill_rect_sync(art_x, 0, art_size, art_size, Color(35, 35, 45))

                text_y = art_size + 6

                title_offset = self._spotify_title_scroller.get_offset() if self._spotify_title_scroller else 0
                self.display.draw_text_sync(
                    self._spotify_track,
                    margin - title_offset, text_y,
                    Palette.TEXT_PRIMARY, title_font,
                )

                artist_offset = self._spotify_artist_scroller.get_offset() if self._spotify_artist_scroller else 0
                self.display.draw_text_sync(
                    self._spotify_artist,
                    margin - artist_offset, text_y + 20,
                    Palette.TEXT_MUTED, artist_font,
                )

                bar_y = h - 24

                if self._spotify_duration_ms > 0:
                    bar_width = w - margin * 2
                    progress_pct = min(1.0, self._spotify_progress_ms / self._spotify_duration_ms)
                    filled = int(bar_width * progress_pct)

                    self.display.fill_rect_sync(
                        margin, bar_y, bar_width, bar_height, Color(50, 50, 50)
                    )
                    if filled > 0:
                        self.display.fill_rect_sync(
                            margin, bar_y, filled, bar_height, Palette.SPOTIFY_GREEN
                        )

                    prog_min = self._spotify_progress_ms // 60000
                    prog_sec = (self._spotify_progress_ms % 60000) // 1000
                    dur_min = self._spotify_duration_ms // 60000
                    dur_sec = (self._spotify_duration_ms % 60000) // 1000
                    time_left = f"{prog_min}:{prog_sec:02d}"
                    time_right = f"{dur_min}:{dur_sec:02d}"
                    time_y = bar_y + bar_height + 2

                    self.display.draw_text_sync(
                        time_left, margin, time_y, Palette.TEXT_MUTED, time_font
                    )
                    tw, _ = self.display.get_text_size(time_right, time_font)
                    self.display.draw_text_sync(
                        time_right, w - margin - tw, time_y,
                        Palette.TEXT_MUTED, time_font,
                    )

                await asyncio.get_event_loop().run_in_executor(
                    None, self.display.show_sync
                )
            await asyncio.sleep(0.1)

    async def _mono_spotify_render(self, last_frame: float) -> None:
        scroll_speed = 30
        char_width = 6
        scroll_offset = 0.0
        scroll_pause = 2.0

        while self._spotify_active:
            now = time.time()
            dt = now - last_frame
            last_frame = now

            display_text = f"{self._spotify_track} - {self._spotify_artist}"
            text_width = len(display_text) * char_width
            needs_scroll = text_width > self.display.width

            if needs_scroll:
                if scroll_pause > 0:
                    scroll_pause -= dt
                else:
                    scroll_offset += scroll_speed * dt
                    max_scroll = text_width - self.display.width + char_width * 3
                    if scroll_offset >= max_scroll:
                        scroll_offset = 0
                        scroll_pause = 2.0

            async with self._lock:
                self.display.clear_sync()
                self.draw_header()

                scroll_x = -int(scroll_offset) if needs_scroll else 0
                self.display.draw_text_sync(display_text, scroll_x, 12, Colors.WHITE, 10)

                if self._spotify_duration_ms > 0:
                    prog_min = self._spotify_progress_ms // 60000
                    prog_sec = (self._spotify_progress_ms % 60000) // 1000
                    dur_min = self._spotify_duration_ms // 60000
                    dur_sec = (self._spotify_duration_ms % 60000) // 1000
                    elapsed_str = f"{prog_min}:{prog_sec:02d}"
                    total_str = f"{dur_min}:{dur_sec:02d}"

                    time_y = 25
                    time_font = 8
                    char_w = 5
                    elapsed_w = len(elapsed_str) * char_w
                    total_w = len(total_str) * char_w
                    gap = 3
                    bar_x = elapsed_w + gap
                    bar_w = self.display.width - bar_x - gap - total_w
                    bar_h = 5
                    bar_y = time_y + 1

                    self.display.draw_text_sync(elapsed_str, 0, time_y, Colors.WHITE, time_font)
                    self.display.draw_text_sync(total_str, self.display.width - total_w, time_y, Colors.WHITE, time_font)

                    self.display.fill_rect_sync(bar_x, bar_y, bar_w, bar_h, Colors.WHITE)
                    self.display.fill_rect_sync(bar_x + 1, bar_y + 1, bar_w - 2, bar_h - 2, Colors.BLACK)

                    progress_pct = min(1.0, self._spotify_progress_ms / self._spotify_duration_ms)
                    filled = int((bar_w - 2) * progress_pct)
                    if filled > 0:
                        self.display.fill_rect_sync(bar_x + 1, bar_y + 1, filled, bar_h - 2, Colors.WHITE)

                await asyncio.get_event_loop().run_in_executor(
                    None, self.display.show_sync
                )
            await asyncio.sleep(0.1)

    # ── Shutdown ──

    async def shutdown(self) -> None:
        self._spotify_active = False
        self._screensaver_active = False
        self._stop_dashboard()
        self._stop_weather()
        for task in [
            self._spotify_render_task,
            self._screensaver_render_task,
            self._monitor_task,
            self._weather_task,
        ]:
            if task and not task.done():
                task.cancel()
        try:
            await self.display.shutdown()
        except Exception as e:
            logger.error("Error shutting down auxiliary display: %s", e)


# ── Module-level API ──

async def init_auxiliary_displays() -> Dict[str, AuxiliaryDisplay]:
    for existing in list(_displays.values()):
        await existing.shutdown()
    _displays.clear()

    detected = detect_displays()
    aux_candidates = [d for d in detected if d.screen_type in (ScreenType.SSD1306, ScreenType.ST7789)]
    logger.debug("Auxiliary display detection: %d total, %d auxiliary candidates", len(detected), len(aux_candidates))

    for info in aux_candidates:
        display = DisplayFactory.create(info)
        if display is None:
            continue
        if not await display.initialize():
            continue

        display_id = f"{info.screen_type.value}_{info.width}x{info.height}"
        aux = AuxiliaryDisplay(display)
        aux.display.clear_sync()
        if aux.is_color:
            aux._render_dashboard_frame()
        else:
            aux.draw_header()
        aux.display.show_sync()
        if aux.is_color:
            aux._start_dashboard()
        _displays[display_id] = aux
        logger.info("Auxiliary display initialized: %s", display_id)

    return _displays


async def reinit_auxiliary_displays() -> Dict[str, AuxiliaryDisplay]:
    displays = await init_auxiliary_displays()
    start_all_screensaver_monitors()
    return displays


def get_auxiliary_displays() -> Dict[str, AuxiliaryDisplay]:
    return _displays


def get_all_auxiliary() -> List[AuxiliaryDisplay]:
    return list(_displays.values())


def register_all_auxiliary_activity() -> None:
    for aux in _displays.values():
        aux.register_activity()


async def restore_all_headers() -> None:
    for aux in _displays.values():
        await aux.restore_header()


async def show_message_all(lines: List[str]) -> None:
    for aux in _displays.values():
        await aux.show_message(lines)


async def show_word_all(word: str, word_lists: Dict[str, list]) -> None:
    for display_id, aux in _displays.items():
        if display_id not in word_lists:
            word_lists[display_id] = []
        await aux.show_word(word, word_lists[display_id])


async def display_state_all(state: str, stop_event: asyncio.Event) -> List[asyncio.Task]:
    tasks = []
    for aux in _displays.values():
        tasks.append(asyncio.create_task(aux.display_state(state, stop_event)))
    return tasks


async def show_spotify_all(
    track: str, artist: str, progress_ms: int = 0, duration_ms: int = 0,
    album_art_url: str = "",
) -> None:
    for aux in _displays.values():
        await aux.show_spotify(track, artist, progress_ms, duration_ms, album_art_url)


async def stop_spotify_all() -> None:
    for aux in _displays.values():
        await aux.stop_spotify()


async def show_weather_all(location: str = None) -> None:
    for aux in _displays.values():
        await aux.show_weather(location)


async def check_screensaver_all(settings: dict) -> None:
    for aux in _displays.values():
        await aux.check_screensaver(settings)


def start_all_screensaver_monitors() -> None:
    for aux in _displays.values():
        aux.start_screensaver_monitor()


def set_ssd1306_rotation(rotation: int) -> None:
    for aux in _displays.values():
        if aux.display.info.screen_type == ScreenType.SSD1306:
            aux.display.set_rotation(rotation)


async def shutdown_all() -> None:
    for aux in _displays.values():
        await aux.shutdown()
    _displays.clear()
