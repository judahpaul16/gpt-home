import asyncio
import json
import logging
import math
import os
import random
import subprocess
import sys
import threading
import time
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

logger = logging.getLogger("display.manager")

from .base import BaseDisplay, Color, DisplayMode
from .detection import detect_displays
from .factory import DisplayFactory
from .modes.clock import clock_loop
from .modes.gallery import gallery_loop
from .modes.screensaver import screensaver_loop
from .modes.waveform import waveform_loop
from .modes.weather import weather_loop
from .palette import (
    Palette,
    ScrollingText,
    ease_in_out_sine,
    ease_out_cubic,
    ease_out_quad,
    lerp,
)
from .renderers import (
    draw_gradient_bg,
    wrap_text,
)
from .renderers import (
    draw_host_ip_overlay as _draw_host_ip_overlay_fn,
)
from .spotify import spotify_now_playing_loop
from .weather import (
    draw_weather_gradient as _draw_weather_gradient_fn,
)
from .weather import (
    fetch_weather_data,
)

_src_dir = str(Path(__file__).parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

try:
    from src.audio_activity import get_audio_activity_detector
except ImportError:
    get_audio_activity_detector = None

try:
    from src.waveform import (
        FullDisplayWaveformObserver,
        get_waveform_mediator,
    )
except ImportError:
    FullDisplayWaveformObserver = None
    get_waveform_mediator = None

# Thread-safe activity flag - set by any thread, checked by render loops
_activity_pending = threading.Event()


def signal_activity() -> None:
    """Signal that user activity occurred. Thread-safe, called from any context."""
    _activity_pending.set()


def check_and_clear_activity() -> bool:
    """Check if activity was signaled and clear the flag. Called from async loops."""
    if _activity_pending.is_set():
        _activity_pending.clear()
        return True
    return False


SETTINGS_PATH = Path(__file__).parent.parent / "settings.json"
TARGET_FPS = 120
FRAME_TIME = 1.0 / TARGET_FPS


class AnimationState(Enum):
    IDLE = auto()
    USER_MESSAGE = auto()
    TOOL_ANIMATION = auto()
    RESPONSE = auto()
    STREAMING = auto()


class DisplayManager:
    _instance: Optional["DisplayManager"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._display: Optional[BaseDisplay] = None
        self._mode = DisplayMode.SMART
        self._render_task: Optional[asyncio.Task] = None
        self._gallery_images: List[str] = []
        self._gallery_index: int = 0
        self._weather_data: Dict[str, Any] = {}
        self._waveform_active: bool = False
        self._waveform_explicitly_started: bool = False
        self._init_waveform_thresholds()
        self._waveform_observer: Optional[FullDisplayWaveformObserver] = None
        self._init_waveform_observer()
        self._current_tool: Optional[str] = None
        self._tool_context: Dict[str, Any] = {}
        self._frame: int = 0
        self._streaming_text: str = ""
        self._state = AnimationState.IDLE
        self._render_lock = asyncio.Lock()
        self._has_tool_animation: bool = False
        self._stop_requested: bool = False
        self._tool_animation_start: float = 0.0
        self._tool_animation_timeout: float = 30.0
        self._spotify_active: bool = False
        self._spotify_track: str = ""
        self._spotify_artist: str = ""
        self._spotify_album: str = ""
        self._spotify_album_art: Optional[bytes] = None
        self._spotify_album_art_url: Optional[str] = None
        self._spotify_progress: float = 0.0
        self._spotify_progress_ms: int = 0
        self._spotify_duration_ms: int = 0
        self._spotify_task: Optional[asyncio.Task] = None
        # Scrolling text for Spotify
        self._track_scroller: Optional[ScrollingText] = None
        self._artist_scroller: Optional[ScrollingText] = None
        # Cache for smooth gradient background
        self._bg_cache: Optional[List[Color]] = None
        # Gallery settings
        self._gallery_interval: float = 10.0
        # Track initialization state for hotswap
        self._display_initialized: bool = False
        # Screensaver state
        self._screensaver_enabled: bool = True
        self._screensaver_timeout: float = 300.0  # seconds of inactivity
        self._screensaver_style: str = "starfield"  # starfield, matrix, bounce, fade
        self._last_activity_time: float = time.time()
        self._screensaver_task: Optional[asyncio.Task] = None
        self._screensaver_active: bool = False  # True when screensaver is showing
        self._screensaver_render_task: Optional[asyncio.Task] = None
        # Screensaver animation state
        self._stars: List[Dict[str, float]] = []
        self._matrix_drops: List[Dict[str, Any]] = []
        self._bounce_pos: List[float] = [0.0, 0.0]
        self._bounce_vel: List[float] = [2.0, 1.5]
        self._fade_hue: float = 0.0
        # Enhanced fade screensaver state
        self._fade_clock_pos: List[float] = [0.0, 0.0]
        self._fade_clock_vel: List[float] = [0.3, 0.2]
        self._fade_blobs: List[Dict[str, float]] = []
        self._fade_particles: List[Dict[str, float]] = []
        self._host_ip: str = ""
        self._initialized = True

    def _init_waveform_thresholds(self) -> None:
        self._waveform_show_threshold = 0.016
        self._waveform_hide_threshold = 0.004

    def _init_waveform_observer(self) -> None:
        if FullDisplayWaveformObserver is None or get_waveform_mediator is None:
            return
        try:
            self._waveform_observer = FullDisplayWaveformObserver(voice_gated=True)
            mediator = get_waveform_mediator()
            mediator.register_observer(self._waveform_observer)
        except Exception as e:
            logger.error("Failed to init waveform observer: %s", e)

    def _update_waveform_observer_mode(self, voice_gated: bool) -> None:
        """Update the waveform observer's voice-gated mode."""
        if self._waveform_observer:
            self._waveform_observer.set_voice_gated(voice_gated)

    @classmethod
    def get_instance(cls) -> "DisplayManager":
        return cls()

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance to allow reinitialization.

        Call this when displays are connected/disconnected to force
        re-detection on next initialize() call.
        """
        if cls._instance is not None:
            # Try to clean up existing display
            if cls._instance._display is not None:
                try:
                    import asyncio

                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(cls._instance.shutdown())
                    else:
                        loop.run_until_complete(cls._instance.shutdown())
                except Exception:
                    pass
            cls._instance._display = None
            cls._instance._display_initialized = False
            logger.debug("Instance reset for reinitialization")

    def _get_host_ip(self) -> str:
        """Get host LAN IP address."""
        if self._host_ip:
            return self._host_ip

        import subprocess

        # Use nsenter to get IP from host (requires pid:host in docker-compose)
        try:
            result = subprocess.run(
                ["nsenter", "-t", "1", "-n", "hostname", "-I"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                self._host_ip = result.stdout.strip().split()[0]
                return self._host_ip
        except Exception:
            pass

        try:
            with open("/run/gpt-home/host-ip", "r") as f:
                ip = f.read().strip()
                if ip:
                    self._host_ip = ip
                    return self._host_ip
        except Exception:
            pass

        return "gpt-home.local"

    async def initialize(
        self, preferred_type: Optional[str] = None, force_refresh: bool = False
    ) -> bool:
        if self._display_initialized and not force_refresh:
            return self._display is not None

        if self._display is not None:
            await self.shutdown()
            self._display = None

        from .detection import check_display_access

        check_display_access()

        # Try multi-display manager first for mirroring support
        full_display = None
        try:
            from .multi import get_multi_display_manager

            multi_mgr = get_multi_display_manager()
            await multi_mgr.detect_and_create_displays()
            full_display = multi_mgr.get_mirrored_display()
            if full_display:
                logger.debug(
                    "Using multi-display manager (mirror=%s)",
                    multi_mgr.get_config().mirror_enabled,
                )
        except Exception:
            pass

        # Fallback to single display detection
        if not full_display:
            full_display = DisplayFactory.auto_detect_full_display()

        if preferred_type and preferred_type not in ["i2c"] and not full_display:
            displays = detect_displays()
            for info in displays:
                if info.screen_type.value == preferred_type:
                    display = DisplayFactory.create(info)
                    if display and display.supports_modes:
                        full_display = display
                        break

        if full_display:
            self._display = full_display
            success = await self._display.initialize()
            if success:
                self._display_initialized = True
                self._build_gradient_cache()

                saved_mode = self._load_saved_mode()
                if saved_mode and saved_mode != self._mode:
                    self._mode = saved_mode

                self._stop_requested = False
                self._frame = 0

                self._load_screensaver_settings()
                self._last_activity_time = time.time()
                await self._start_mode_loop()

                # Always start screensaver activity monitor (it checks enabled flag internally)
                # This ensures the monitor is running and can activate when settings change
                self._screensaver_task = asyncio.create_task(
                    self._screensaver_monitor_loop()
                )
            return success

        self._display_initialized = True
        return False

    def _load_saved_mode(self) -> Optional[DisplayMode]:
        """Load the saved display mode from settings.json."""
        try:
            if SETTINGS_PATH.exists():
                with SETTINGS_PATH.open("r") as f:
                    settings = json.load(f)
                mode_name = settings.get("display_mode", "smart").lower()
                mode_map = {
                    "smart": DisplayMode.SMART,
                    "clock": DisplayMode.CLOCK,
                    "weather": DisplayMode.WEATHER,
                    "gallery": DisplayMode.GALLERY,
                    "waveform": DisplayMode.WAVEFORM,
                    "off": DisplayMode.OFF,
                }
                return mode_map.get(mode_name, DisplayMode.SMART)
        except Exception:
            pass
        return None

    def _load_screensaver_settings(self) -> None:
        """Load screensaver settings from settings.json."""
        try:
            if SETTINGS_PATH.exists():
                with SETTINGS_PATH.open("r") as f:
                    settings = json.load(f)
                self._screensaver_enabled = settings.get("screensaver_enabled", True)
                self._screensaver_timeout = float(
                    settings.get("screensaver_timeout", 300)
                )
                self._screensaver_style = settings.get("screensaver_style", "starfield")
        except Exception:
            pass

    def register_activity(self) -> None:
        """Register user activity to reset screensaver timer.

        Thread-safe. Sets a flag that render loops check to deactivate screensaver.
        """
        self._last_activity_time = time.time()
        if self._screensaver_active:
            signal_activity()

    async def register_activity_async(self) -> None:
        """Async version - register activity and wait for screensaver deactivation."""
        self._last_activity_time = time.time()
        was_active = self._screensaver_active
        if was_active:
            self._stop_requested = True
            await self._deactivate_screensaver()

    async def _activate_screensaver(self) -> None:
        if (
            self._screensaver_active
            or not self._display
            or self._mode == DisplayMode.OFF
        ):
            return

        logger.debug("Activating screensaver (style: %s)", self._screensaver_style)
        self._screensaver_active = True

        await self._stop_render()
        self._stop_requested = False
        self._load_screensaver_settings()

        def stop_check() -> bool:
            return self._stop_requested

        def activity_check() -> bool:
            return check_and_clear_activity()

        self._screensaver_render_task = asyncio.create_task(
            screensaver_loop(
                self,
                self._screensaver_style,
                stop_check,
                activity_check,
                self._deactivate_screensaver,
            )
        )

    async def _deactivate_screensaver(self) -> None:
        """Deactivate screensaver and resume the current mode's display."""
        if not self._screensaver_active and self._screensaver_render_task is None:
            return

        logger.debug("Deactivating screensaver, resuming mode: %s", self._mode.name)
        self._screensaver_active = False
        self._stop_requested = True

        # Check if we're being called from within the screensaver task itself
        current_task = asyncio.current_task()
        is_self_call = (
            self._screensaver_render_task is not None
            and current_task is self._screensaver_render_task
        )

        if self._screensaver_render_task and not self._screensaver_render_task.done():
            if not is_self_call:
                # Only cancel and wait if called from outside the task
                self._screensaver_render_task.cancel()
                try:
                    await asyncio.wait_for(self._screensaver_render_task, timeout=0.5)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
            # If called from within, just let it exit naturally after we return

        self._screensaver_render_task = None
        self._stop_requested = False

        # Start the mode loop - if called from screensaver task, schedule it
        if is_self_call:
            asyncio.create_task(self._start_mode_loop())
        else:
            await self._start_mode_loop()

    async def _check_screensaver_timeout(self) -> None:
        """Check if screensaver should activate due to inactivity."""
        if not self._screensaver_enabled:
            return
        if self._screensaver_active:
            return
        if not self._display:
            return
        if self._mode == DisplayMode.OFF:
            return
        if self._spotify_active:
            # Don't activate screensaver during Spotify playback
            return

        elapsed = time.time() - self._last_activity_time
        if elapsed >= self._screensaver_timeout:
            logger.debug("Activating screensaver after %.0fs of inactivity", elapsed)
            await self._activate_screensaver()

    async def _screensaver_monitor_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(10)
                await self._check_screensaver_timeout()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Screensaver monitor error: %s", e)

    async def reinitialize(self) -> bool:
        """Reinitialize the display manager to detect newly connected displays.

        This is the hotswap entry point - call this when displays are
        connected or disconnected to re-scan and reinitialize.

        Returns:
            True if a full display was found and initialized
        """
        logger.debug("Reinitializing display manager (hotswap)...")
        self._display_initialized = False
        return await self.initialize(force_refresh=True)

    @property
    def display(self) -> Optional[BaseDisplay]:
        """The full display (if available). None if only simple I2C display is connected."""
        return self._display

    @property
    def mode(self) -> DisplayMode:
        return self._mode

    @property
    def is_available(self) -> bool:
        """True if a full display (supporting modes) is available."""
        return self._display is not None

    @property
    def supports_modes(self) -> bool:
        """True if display modes are supported (i.e., a full display is connected).

        Simple displays like I2C don't support modes - they just show text.
        """
        return self._display is not None and self._display.supports_modes

    @property
    def has_tool_animation(self) -> bool:
        return self._has_tool_animation

    def _build_gradient_cache(self):
        """Pre-compute background color."""
        # Use solid dark background for clean look
        self._bg_color = Color(18, 20, 28)

    async def set_mode(self, mode: DisplayMode) -> None:
        if not self._display:
            return

        if self._screensaver_active:
            self._mode = mode
            return

        if self._mode == mode:
            return

        logger.debug("Changing mode from %s to %s", self._mode.name, mode.name)

        # Signal stop BEFORE acquiring lock to avoid deadlock
        # (render loop holds lock while checking stop flag)
        self._stop_requested = True

        # Cancel and wait for render task OUTSIDE the lock
        if self._render_task and not self._render_task.done():
            self._render_task.cancel()
            try:
                await asyncio.wait_for(self._render_task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            self._render_task = None

        # Now safe to change mode with lock held briefly
        async with self._render_lock:
            self._mode = mode
            self._display.current_mode = mode
            self._frame = 0
            self._state = AnimationState.IDLE

            # Clear display when switching modes to prevent artifacts
            self._display.clear_sync(Color(0, 0, 0))

            if mode == DisplayMode.OFF:
                self._display.show_sync()
                self._restore_tty()
                logger.debug("Display turned off, TTY restored")
                return

        # Clear stop flag and start new loop
        self._stop_requested = False
        await self._start_mode_loop()

    def _restore_tty(self) -> None:
        """Restore TTY to text mode."""
        if not self._display:
            return
        # Check if display has restore_tty method
        if hasattr(self._display, "restore_tty"):
            self._display.restore_tty()
        else:
            # Try to restore TTY using ioctl
            try:
                import fcntl
                import os

                KD_TEXT = 0x00
                KDSETMODE = 0x4B3A
                tty_path = "/dev/tty1"
                if os.path.exists(tty_path):
                    with open(tty_path, "w") as tty:
                        fcntl.ioctl(tty.fileno(), KDSETMODE, KD_TEXT)
            except Exception:
                pass

    async def _start_mode_loop(self) -> None:
        """Start the render loop for current mode."""
        current_mode = self._mode

        if self._screensaver_active:
            return

        if current_mode == DisplayMode.OFF:
            return

        if not self._display:
            return

        if self._render_task and not self._render_task.done():
            self._stop_requested = True
            self._render_task.cancel()
            try:
                await asyncio.wait_for(self._render_task, timeout=0.5)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            self._render_task = None

        # CRITICAL: Clear stop flag before starting new loop
        self._stop_requested = False
        self._frame = 0

        if self._screensaver_active:
            return

        # Helper callbacks for mode loops
        def stop_check() -> bool:
            return self._stop_requested

        def screensaver_check() -> bool:
            return self._screensaver_active

        # For SMART mode, start in idle (clock) but can be interrupted by tools
        # For other modes, they are STATIC and run their dedicated loop continuously
        if current_mode == DisplayMode.SMART:
            self._state = AnimationState.IDLE
            self._render_task = asyncio.create_task(
                clock_loop(self, stop_check, screensaver_check)
            )
        elif current_mode == DisplayMode.CLOCK:
            self._render_task = asyncio.create_task(
                clock_loop(self, stop_check, screensaver_check)
            )
        elif current_mode == DisplayMode.WEATHER:
            self._render_task = asyncio.create_task(
                weather_loop(self, stop_check, screensaver_check)
            )
        elif current_mode == DisplayMode.GALLERY:
            self._render_task = asyncio.create_task(
                gallery_loop(self, stop_check, screensaver_check)
            )
        elif current_mode == DisplayMode.WAVEFORM:
            self._render_task = asyncio.create_task(
                waveform_loop(self, stop_check, screensaver_check)
            )
        else:
            logger.warning("Unknown display mode: %s", current_mode)

    async def _stop_render(self) -> None:
        """Stop the current render task."""
        self._stop_requested = True

        if self._render_task and not self._render_task.done():
            self._render_task.cancel()
            try:
                await asyncio.wait_for(self._render_task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        self._render_task = None
        self._frame = 0

    async def show_user_message(self, message: str, duration: float = 3.0) -> None:
        """Show user message bubble - only in SMART mode."""
        await self.register_activity_async()

        if not self._display or self._mode != DisplayMode.SMART:
            return

        self._has_tool_animation = False
        prev_state = self._state
        self._state = AnimationState.USER_MESSAGE

        await self._stop_render()
        self._stop_requested = False
        await self._animate_user_bubble(message, duration)

        # Return to idle if no tool animation follows
        if self._state == AnimationState.USER_MESSAGE:
            self._state = AnimationState.IDLE
            if not self._screensaver_active:
                await self._start_mode_loop()

    async def show_tool_animation(
        self,
        tool_name: str,
        context: Dict[str, Any],
        user_message: Optional[str] = None,
    ) -> None:
        """Show tool-specific animation - only in SMART mode."""
        await self.register_activity_async()

        if not self._display:
            return
        if self._mode != DisplayMode.SMART:
            return

        await self._stop_render()
        self._stop_requested = False
        self._tool_context = context
        self._current_tool = tool_name.lower()
        self._state = AnimationState.TOOL_ANIMATION
        self._has_tool_animation = True
        self._tool_animation_start = time.time()

        await self._start_tool_animation(tool_name, context)

    async def _start_tool_animation(
        self, tool_name: str, context: Dict[str, Any]
    ) -> None:
        """Start the appropriate animation for a tool."""
        tool = tool_name.lower()
        self._stop_requested = False

        if "weather" in tool:
            if "temperature" in context:
                self._weather_data["temperature"] = context.get("temperature")
            if "condition" in context:
                self._weather_data["condition"] = context.get("condition")
            if "location" in context:
                self._weather_data["location"] = context.get("location")
            requested_location = context.get("requested_location")

            def stop_check() -> bool:
                return self._stop_requested

            def screensaver_check() -> bool:
                return self._screensaver_active

            self._render_task = asyncio.create_task(
                weather_loop(
                    self,
                    stop_check,
                    screensaver_check,
                    fetch_forecast=True,
                    location=requested_location,
                )
            )
        elif "timer" in tool or "alarm" in tool:
            self._render_task = asyncio.create_task(self._timer_animation(context))
        elif "spotify" in tool or "music" in tool:
            self._render_task = asyncio.create_task(self._music_animation(context))
        elif "light" in tool or "hue" in tool:
            self._render_task = asyncio.create_task(self._light_animation(context))
        else:
            # Generic tool animation
            self._render_task = asyncio.create_task(
                self._generic_tool_animation(tool_name, context)
            )

    async def _timer_animation(self, context: Dict[str, Any]) -> None:
        try:
            duration = context.get("duration", 0)
            name = context.get("name", "Timer")
            start_time = time.perf_counter()
            last_frame = start_time
            is_alarm = "alarm" in name.lower()
            rotation = 0.0

            while not self._stop_requested and not self._screensaver_active:
                if (
                    self._mode == DisplayMode.SMART
                    and self._tool_animation_start > 0
                    and time.time() - self._tool_animation_start
                    > self._tool_animation_timeout
                ):
                    asyncio.create_task(self.resume_idle())
                    break

                now = time.perf_counter()
                dt = now - last_frame
                last_frame = now
                elapsed = now - start_time

                async with self._render_lock:
                    d = self._display
                    if not d:
                        break

                    draw_gradient_bg(d)
                    cx, cy = d.get_center()

                    if duration <= 0:
                        rotation += dt * 120
                        pulse = ease_in_out_sine((math.sin(elapsed * 2) + 1) / 2)

                        d.draw_circle_sync(
                            cx, cy, d.scale_x(90), Color(40, 45, 65), filled=False
                        )
                        radius = d.scale_x(70)
                        d.draw_circle_sync(
                            cx, cy, radius, Color(55, 60, 85), filled=False
                        )

                        if hasattr(d, "draw_arc_sync"):
                            arc_len = 80 + 40 * pulse
                            d.draw_arc_sync(
                                cx,
                                cy,
                                radius,
                                int(rotation % 360),
                                int((rotation + arc_len) % 360),
                                Palette.ACCENT_CYAN,
                                4,
                            )

                        icon_r = d.scale_x(28)
                        d.draw_circle_sync(
                            cx,
                            cy,
                            icon_r,
                            Color(
                                50 + int(15 * pulse),
                                55 + int(15 * pulse),
                                80 + int(15 * pulse),
                            ),
                            filled=True,
                        )

                        if is_alarm:
                            d.draw_circle_sync(
                                cx,
                                cy - d.scale_y(3),
                                d.scale_x(10),
                                Palette.ACCENT_ORANGE,
                                filled=True,
                            )
                            d.draw_circle_sync(
                                cx,
                                cy - d.scale_y(14),
                                d.scale_x(4),
                                Palette.ACCENT_ORANGE,
                                filled=True,
                            )
                        else:
                            angle = math.radians(rotation * 0.3)
                            hx, hy = (
                                int(cx + math.cos(angle - 1) * d.scale_x(8)),
                                int(cy + math.sin(angle - 1) * d.scale_y(8)),
                            )
                            mx, my = (
                                int(cx + math.cos(angle) * d.scale_x(14)),
                                int(cy + math.sin(angle) * d.scale_y(14)),
                            )
                            d.draw_line_sync(cx, cy, hx, hy, Palette.ACCENT_CYAN, 3)
                            d.draw_line_sync(cx, cy, mx, my, Palette.ACCENT_CYAN, 2)

                        label = f"Setting {name}"
                        label_size = d.scale_font(20)
                        d.draw_text_sync(
                            label,
                            int(cx - len(label) * label_size * 0.25),
                            cy + d.scale_y(55),
                            Palette.TEXT_PRIMARY,
                            label_size,
                        )
                    else:
                        remaining = max(0, duration - elapsed)
                        progress = min(1.0, elapsed / duration)

                        d.draw_circle_sync(
                            cx, cy, d.scale_x(90), Color(40, 45, 65), filled=False
                        )
                        radius = d.scale_x(75)
                        d.draw_circle_sync(
                            cx, cy, radius, Color(50, 55, 80), filled=False
                        )

                        if hasattr(d, "draw_arc_sync"):
                            r = int(lerp(80, Palette.ACCENT_GREEN.r, progress))
                            g = int(lerp(200, Palette.ACCENT_GREEN.g, progress))
                            b = int(lerp(255, Palette.ACCENT_GREEN.b, progress))
                            d.draw_arc_sync(
                                cx,
                                cy,
                                radius,
                                -90,
                                int(-90 + progress * 360),
                                Color(r, g, b),
                                6,
                            )

                        mins, secs = int(remaining // 60), int(remaining % 60)
                        time_str = f"{mins}:{secs:02d}" if mins > 0 else str(secs)
                        time_size = d.scale_font(52)
                        d.draw_text_sync(
                            time_str,
                            int(cx - len(time_str) * time_size * 0.27),
                            cy - d.scale_y(15),
                            Palette.TEXT_PRIMARY,
                            time_size,
                        )

                        unit = "remaining" if mins > 0 else "seconds"
                        unit_size = d.scale_font(14)
                        d.draw_text_sync(
                            unit,
                            int(cx - len(unit) * unit_size * 0.25),
                            cy + d.scale_y(25),
                            Palette.TEXT_MUTED,
                            unit_size,
                        )

                        name_size = d.scale_font(18)
                        d.draw_text_sync(
                            name,
                            int(cx - len(name) * name_size * 0.25),
                            cy + d.scale_y(55),
                            Palette.TEXT_SECONDARY,
                            name_size,
                        )

                        if remaining <= 0:
                            break

                    d.show_sync()

                await asyncio.sleep(
                    max(0.001, FRAME_TIME - (time.perf_counter() - now))
                )
        except asyncio.CancelledError:
            pass

    async def _fetch_spotify_data(self) -> Dict[str, Any]:
        """Fetch current Spotify playback data from the backend."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "http://localhost:8000/api/spotify/playback",
                    timeout=aiohttp.ClientTimeout(total=3),
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception:
            pass
        return {}

    async def _load_album_art(self, url: str) -> Optional[Any]:
        """Load album art from URL."""
        if not url:
            return None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status == 200:
                        import io

                        from PIL import Image

                        data = await resp.read()
                        img = Image.open(io.BytesIO(data))
                        return img.convert("RGB")
        except Exception:
            pass
        return None

    async def _music_animation(self, context: Dict[str, Any]) -> None:
        """Spotify music animation with modern, appealing design and scrolling text."""
        try:
            # Try to get real Spotify data first
            spotify_data = await self._fetch_spotify_data()

            track = spotify_data.get("track") or context.get("track", "")
            artist = spotify_data.get("artist") or context.get("artist", "")
            album_art_url = (
                spotify_data.get("album_art_url") or context.get("album_art_url") or ""
            )

            # Load album art
            album_art_img = (
                await self._load_album_art(album_art_url) if album_art_url else None
            )

            last_frame = time.perf_counter()
            phase = 0.0
            bar_heights = [0.0] * 12  # For animated equalizer bars
            last_data_fetch = time.perf_counter()

            # Initialize scrolling text (will be set up in render loop with proper dimensions)
            track_scroller: Optional[ScrollingText] = None
            artist_scroller: Optional[ScrollingText] = None
            last_track = ""
            last_artist = ""

            while not self._stop_requested and not self._screensaver_active:
                if (
                    self._mode == DisplayMode.SMART
                    and self._tool_animation_start > 0
                    and time.time() - self._tool_animation_start
                    > self._tool_animation_timeout
                ):
                    asyncio.create_task(self.resume_idle())
                    break

                now = time.perf_counter()
                dt = now - last_frame
                last_frame = now
                phase += dt * 2.5

                # Refresh Spotify data periodically (every 5 seconds)
                if now - last_data_fetch > 5.0:
                    spotify_data = await self._fetch_spotify_data()
                    if spotify_data:
                        new_track = spotify_data.get("track", "")
                        new_art_url = spotify_data.get("album_art_url")
                        # Reload album art if track changed
                        if new_track and new_track != track:
                            track = new_track
                            artist = spotify_data.get("artist", "")
                            # Reset scrollers on track change
                            track_scroller = None
                            artist_scroller = None
                            if new_art_url and new_art_url != album_art_url:
                                album_art_url = new_art_url
                                album_art_img = await self._load_album_art(
                                    album_art_url
                                )
                    last_data_fetch = now

                async with self._render_lock:
                    d = self._display
                    if not d or self._stop_requested:
                        break

                    w, h = d.width, d.height

                    # Dark gradient background
                    d.clear_sync(Color(12, 12, 18))

                    # Layout: Left side = album art, Right side = track info + visualizer
                    margin = d.scale_x(60)
                    art_size = min(d.scale_x(280), d.scale_y(280), h - d.scale_y(100))
                    art_x = margin
                    art_y = (h - art_size) // 2

                    # Draw album art with rounded corners effect (border)
                    if album_art_img:
                        try:
                            resized = album_art_img.resize((art_size, art_size))
                            # Draw shadow/glow behind
                            shadow_offset = d.scale_x(8)
                            d.fill_rect_sync(
                                art_x + shadow_offset,
                                art_y + shadow_offset,
                                art_size,
                                art_size,
                                Color(0, 0, 0),
                            )
                            if hasattr(d, "draw_pil_image_sync"):
                                d.draw_pil_image_sync(resized, art_x, art_y)
                            else:
                                d.fill_rect_sync(
                                    art_x, art_y, art_size, art_size, Color(40, 40, 50)
                                )
                        except Exception:
                            d.fill_rect_sync(
                                art_x, art_y, art_size, art_size, Color(30, 30, 40)
                            )
                    else:
                        # Modern loading placeholder with spinner
                        d.fill_rect_sync(
                            art_x, art_y, art_size, art_size, Color(20, 20, 28)
                        )

                        # Draw modern spinning loader
                        spinner_cx = art_x + art_size // 2
                        spinner_cy = art_y + art_size // 2
                        spinner_radius = art_size // 5
                        spinner_thickness = d.scale_x(6)

                        # Draw spinner arc segments
                        num_segments = 12
                        for i in range(num_segments):
                            angle = (i / num_segments) * 2 * math.pi + phase * 2
                            # Fade segments for trailing effect
                            segment_alpha = (
                                (i + int(phase * 8)) % num_segments
                            ) / num_segments

                            seg_x = spinner_cx + int(math.cos(angle) * spinner_radius)
                            seg_y = spinner_cy + int(math.sin(angle) * spinner_radius)

                            # Spotify green with varying intensity
                            intensity = segment_alpha
                            seg_color = Color(
                                int(30 * intensity),
                                int(215 * intensity),
                                int(96 * intensity),
                            )

                            # Draw dot for each segment
                            dot_size = spinner_thickness
                            d.fill_rect_sync(
                                seg_x - dot_size // 2,
                                seg_y - dot_size // 2,
                                dot_size,
                                dot_size,
                                seg_color,
                            )

                    # Right side content - calculate available width carefully
                    left_margin = d.scale_x(40)
                    content_x = art_x + art_size + left_margin
                    right_margin = left_margin  # Balance left/right margins
                    content_width = w - content_x - right_margin

                    # Spotify logo indicator (green dot) - positioned safely in corner
                    indicator_size = d.scale_x(10)
                    d.fill_rect_sync(
                        w - right_margin - indicator_size,
                        d.scale_y(20),
                        indicator_size,
                        d.scale_y(10),
                        Palette.SPOTIFY_GREEN,
                    )

                    # Track name with scrolling
                    track_y = art_y + d.scale_y(20)
                    track_size = d.scale_font(28)
                    track_display = track if track else "Playing on Spotify"

                    # Initialize or update track scroller
                    if track_display != last_track or track_scroller is None:
                        track_scroller = ScrollingText(
                            track_display,
                            content_width,
                            track_size,
                            char_width_ratio=0.55,
                        )
                        last_track = track_display

                    # Update scroller animation
                    track_scroller.update(dt)

                    # Draw track name with clipping
                    if track_scroller.needs_scroll:
                        scroll_offset = track_scroller.get_offset()
                        d.set_clip(
                            content_x,
                            0,
                            content_width,
                            d.height,
                        )
                        d.draw_text_sync(
                            track_display,
                            content_x - scroll_offset,
                            track_y,
                            Palette.TEXT_PRIMARY,
                            track_size,
                        )
                        d.clear_clip()
                        # Fade gradient on right edge
                        fade_width = d.scale_x(30)
                        for i in range(fade_width):
                            alpha = i / fade_width
                            fade_color = Color(
                                int(12 * alpha), int(12 * alpha), int(18 * alpha)
                            )
                            d.fill_rect_sync(
                                w - right_margin - fade_width + i,
                                track_y - d.scale_y(5),
                                1,
                                track_size + d.scale_y(10),
                                fade_color,
                            )
                    else:
                        d.draw_text_sync(
                            track_display,
                            content_x,
                            track_y,
                            Palette.TEXT_PRIMARY,
                            track_size,
                        )

                    # Artist name with scrolling
                    artist_y = track_y + d.scale_y(45)
                    artist_size = d.scale_font(20)
                    artist_display = artist if artist else "GPT Home"

                    # Initialize or update artist scroller
                    if artist_display != last_artist or artist_scroller is None:
                        artist_scroller = ScrollingText(
                            artist_display,
                            content_width,
                            artist_size,
                            char_width_ratio=0.55,
                        )
                        last_artist = artist_display

                    # Update scroller animation
                    artist_scroller.update(dt)

                    # Draw artist name with clipping
                    if artist_scroller.needs_scroll:
                        scroll_offset = artist_scroller.get_offset()
                        d.set_clip(
                            content_x,
                            0,
                            content_width,
                            d.height,
                        )
                        d.draw_text_sync(
                            artist_display,
                            content_x - scroll_offset,
                            artist_y,
                            Palette.TEXT_SECONDARY,
                            artist_size,
                        )
                        d.clear_clip()
                        # Fade gradient on right edge
                        fade_width = d.scale_x(25)
                        for i in range(fade_width):
                            alpha = i / fade_width
                            fade_color = Color(
                                int(12 * alpha), int(12 * alpha), int(18 * alpha)
                            )
                            d.fill_rect_sync(
                                w - right_margin - fade_width + i,
                                artist_y - d.scale_y(3),
                                1,
                                artist_size + d.scale_y(6),
                                fade_color,
                            )
                    else:
                        d.draw_text_sync(
                            artist_display,
                            content_x,
                            artist_y,
                            Palette.TEXT_SECONDARY,
                            artist_size,
                        )

                    # Animated equalizer visualization at bottom right
                    eq_bar_count = 12
                    eq_bar_w = d.scale_x(8)
                    eq_spacing = d.scale_x(6)
                    eq_height = d.scale_y(60)
                    eq_y = art_y + art_size - eq_height
                    eq_x = content_x

                    for i in range(eq_bar_count):
                        # Create varied animation for each bar
                        target = 0.2 + 0.6 * abs(math.sin(phase * 2 + i * 0.5))
                        target *= 0.5 + 0.5 * abs(math.sin(phase * 0.7 + i * 0.3))
                        if i >= len(bar_heights):
                            bar_heights.append(0.0)
                        bar_heights[i] = lerp(bar_heights[i], target, dt * 10)

                        h_px = max(d.scale_y(4), int(eq_height * bar_heights[i]))
                        bx = eq_x + i * (eq_bar_w + eq_spacing)
                        by = eq_y + eq_height - h_px

                        # Color gradient from green to cyan
                        ratio = i / eq_bar_count
                        bar_color = Color(
                            int(30 + 40 * ratio),
                            int(200 - 30 * ratio),
                            int(100 + 80 * ratio),
                        )
                        d.fill_rect_sync(bx, by, eq_bar_w, h_px, bar_color)

                    # Progress bar at the very bottom with time stamps
                    progress_y = h - d.scale_y(35)
                    progress_h = d.scale_y(4)
                    progress_margin = margin + d.scale_x(50)  # Space for time
                    progress_w = w - progress_margin * 2

                    # Time labels
                    time_size = d.scale_font(14)
                    progress_pct = spotify_data.get("progress_pct", 0)
                    duration_ms = spotify_data.get("duration_ms", 0)
                    progress_ms = spotify_data.get("progress_ms", 0)

                    # Format times
                    if duration_ms > 0:
                        prog_min = int(progress_ms / 60000)
                        prog_sec = int((progress_ms % 60000) / 1000)
                        dur_min = int(duration_ms / 60000)
                        dur_sec = int((duration_ms % 60000) / 1000)
                        start_time = f"{prog_min}:{prog_sec:02d}"
                        end_time = f"{dur_min}:{dur_sec:02d}"
                    else:
                        # Loading state - show blank times
                        start_time = "0:00"
                        end_time = "-:--"
                        progress_pct = 0  # No progress when loading

                    # Draw start time
                    d.draw_text_sync(
                        start_time,
                        margin,
                        progress_y - d.scale_y(2),
                        Palette.TEXT_SECONDARY,
                        time_size,
                    )

                    # Draw end time
                    d.draw_text_sync(
                        end_time,
                        w - margin - len(end_time) * time_size // 2,
                        progress_y - d.scale_y(2),
                        Palette.TEXT_SECONDARY,
                        time_size,
                    )

                    # Background track (always visible)
                    d.fill_rect_sync(
                        progress_margin,
                        progress_y,
                        progress_w,
                        progress_h,
                        Color(50, 50, 60),
                    )

                    # Progress fill (only if we have actual progress)
                    if progress_pct > 0:
                        filled_w = int(progress_w * min(1.0, progress_pct))
                        if filled_w > 0:
                            d.fill_rect_sync(
                                progress_margin,
                                progress_y,
                                filled_w,
                                progress_h,
                                Palette.SPOTIFY_GREEN,
                            )

                        # Playhead dot
                        dot_radius = d.scale_y(6)
                        dot_x = progress_margin + filled_w
                        d.fill_rect_sync(
                            dot_x - dot_radius // 2,
                            progress_y - dot_radius // 2 + progress_h // 2,
                            dot_radius,
                            dot_radius,
                            Palette.SPOTIFY_GREEN,
                        )

                    _draw_host_ip_overlay_fn(d, self._get_host_ip())
                    d.show_sync()

                await asyncio.sleep(
                    max(0.001, FRAME_TIME - (time.perf_counter() - now))
                )

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Music animation error: %s", e)

    async def _light_animation(self, context: Dict[str, Any]) -> None:
        try:
            action = context.get("action", "toggle")
            is_on = "on" in action.lower() or "toggle" in action.lower()
            last_frame = time.perf_counter()
            frame = 0

            while not self._stop_requested and not self._screensaver_active:
                if (
                    self._mode == DisplayMode.SMART
                    and self._tool_animation_start > 0
                    and time.time() - self._tool_animation_start
                    > self._tool_animation_timeout
                ):
                    asyncio.create_task(self.resume_idle())
                    break

                now = time.perf_counter()
                last_frame = now
                pulse = ease_in_out_sine((math.sin(now * 3) + 1) / 2)

                async with self._render_lock:
                    d = self._display
                    if not d:
                        break

                    d.clear_sync(Color(18, 20, 28))
                    cx, cy = d.get_center()

                    if is_on:
                        # Pulsing light bulb glow
                        glow_radius = int(d.scale_x(60 + 40 * pulse))
                        for r in range(5, 0, -1):
                            alpha = 0.15 * r * pulse
                            glow_color = Color(
                                int(255 * alpha), int(220 * alpha), int(100 * alpha)
                            )
                            d.draw_circle_sync(
                                cx,
                                cy - d.scale_y(20),
                                glow_radius + r * 15,
                                glow_color,
                                filled=True,
                            )

                        # Bright bulb
                        bulb_color = Color(
                            int(255 * pulse), int(240 * pulse), int(180 * pulse)
                        )
                    else:
                        # Dim/off bulb
                        bulb_color = Color(80, 85, 100)

                    d.draw_circle_sync(
                        cx, cy - d.scale_y(20), d.scale_x(40), bulb_color, filled=True
                    )

                    # Status text
                    status = f"Lights {action.title()}"
                    status_size = d.scale_font(24)
                    status_w = len(status) * (status_size * 0.5)
                    d.draw_text_sync(
                        status,
                        int(cx - status_w // 2),
                        cy + d.scale_y(50),
                        Palette.TEXT_PRIMARY,
                        status_size,
                    )

                    dots = "." * ((frame // 15) % 4)
                    proc_text = f"Controlling{dots}"
                    proc_size = d.scale_font(14)
                    d.draw_text_sync(
                        proc_text,
                        int(cx - len(proc_text) * proc_size * 0.25),
                        cy + d.scale_y(80),
                        Palette.TEXT_MUTED,
                        proc_size,
                    )

                    d.show_sync()

                frame += 1
                await asyncio.sleep(
                    max(0.001, FRAME_TIME - (time.perf_counter() - now))
                )

        except asyncio.CancelledError:
            pass

    async def _generic_tool_animation(
        self, tool_name: str, context: Dict[str, Any]
    ) -> None:
        """Show generic tool animation - loops continuously until stopped."""
        try:
            frame = 0
            while not self._stop_requested and not self._screensaver_active:
                if (
                    self._mode == DisplayMode.SMART
                    and self._tool_animation_start > 0
                    and time.time() - self._tool_animation_start
                    > self._tool_animation_timeout
                ):
                    asyncio.create_task(self.resume_idle())
                    break

                t = (frame % 60) / 60.0  # Cycle every 60 frames
                phase = t * math.pi * 2

                async with self._render_lock:
                    d = self._display
                    if not d:
                        break

                    d.clear_sync(Color(18, 20, 28))
                    cx, cy = d.get_center()

                    # Spinning dots with pulsing effect
                    for j in range(8):
                        angle = (j / 8) * math.pi * 2 + phase
                        radius = d.scale_x(50) + int(10 * math.sin(phase * 2))
                        x = cx + int(math.cos(angle) * radius)
                        y = cy + int(math.sin(angle) * radius)
                        dot_size = 4 + int(4 * (1 + math.sin(phase + j)))
                        # Cycle through colors
                        colors = [
                            Palette.ACCENT_CYAN,
                            Palette.ACCENT_BLUE,
                            Palette.ACCENT_PURPLE,
                            Palette.ACCENT_PINK,
                        ]
                        color = colors[(j + frame // 15) % len(colors)]
                        d.draw_circle_sync(x, y, dot_size, color, filled=True)

                    # Tool name with subtle pulse
                    name = tool_name.replace("_", " ").title()
                    name_size = d.scale_font(20)
                    name_w = len(name) * (name_size * 0.5)
                    d.draw_text_sync(
                        name,
                        int(cx - name_w // 2),
                        cy + d.scale_y(80),
                        Palette.TEXT_SECONDARY,
                        name_size,
                    )

                    # "Processing..." text
                    dots = "." * ((frame // 20) % 4)
                    status = f"Processing{dots}"
                    status_size = d.scale_font(14)
                    status_w = len(status) * (status_size * 0.5)
                    d.draw_text_sync(
                        status,
                        int(cx - status_w // 2),
                        cy + d.scale_y(110),
                        Palette.TEXT_MUTED,
                        status_size,
                    )

                    d.show_sync()

                frame += 1
                await asyncio.sleep(0.016)
        except asyncio.CancelledError:
            pass

    async def show_response_animation(self, response: str) -> None:
        """Show response bubble - only in SMART mode and if no tool animation."""
        if not self._display or self._mode != DisplayMode.SMART:
            return

        if self._screensaver_active:
            return

        if self._has_tool_animation:
            return

        await self._stop_render()
        # Clear stop flag so animation can run
        self._stop_requested = False
        self._state = AnimationState.RESPONSE
        await self._animate_response_bubble(response)

    async def stream_response_word(self, word: str) -> None:
        """Stream response word by word - only in SMART mode."""
        if not self._display or self._mode != DisplayMode.SMART:
            return

        if self._screensaver_active:
            return

        if self._state != AnimationState.STREAMING:
            await self._stop_render()
            self._state = AnimationState.STREAMING
            self._streaming_text = ""

        self._streaming_text += (" " if self._streaming_text else "") + word
        await self._render_streaming_text()

    async def clear_streaming(self) -> None:
        self._streaming_text = ""

    def _render_waveform_inline(self, d, dt: float, voice_gated: bool = True) -> None:
        """Render waveform bars inline within any mode loop.

        Args:
            d: Display instance
            dt: Delta time since last frame
            voice_gated: If True, only show bars when voice is detected (SMART mode).
                        If False, show bars for any audio (WAVEFORM mode).
        """
        if self._waveform_observer is None:
            return

        self._waveform_observer.set_voice_gated(voice_gated)
        waveform_snapshot = self._waveform_observer.get_render_values()

        cx, cy = d.get_center()
        bar_count = 32
        total_bar_area = d.width - d.scale_x(80)
        bar_width = max(8, total_bar_area // (bar_count + bar_count // 2))
        spacing = max(3, bar_width // 3)
        total_width = bar_count * (bar_width + spacing) - spacing
        start_x = cx - total_width // 2

        for i in range(bar_count):
            x = start_x + i * (bar_width + spacing)
            pos_factor = i / (bar_count - 1)
            val = waveform_snapshot[i] if i < len(waveform_snapshot) else 0.0

            max_height = d.scale_y(120)
            half_height = max(1, int(val * max_height))
            y = cy - half_height
            height = half_height * 2

            if val > 0.005:
                intensity = min(1.0, val * 1.5)
                r = int(50 + 180 * intensity * (0.3 + 0.7 * pos_factor))
                g = int(120 + 100 * intensity * (1.0 - 0.3 * pos_factor))
                b = int(200 + 55 * intensity)
                bar_color = Color(min(255, r), min(255, g), min(255, b))

                if val > 0.3:
                    glow_alpha = min(0.4, (val - 0.3) * 0.8)
                    glow_r = int(r * glow_alpha)
                    glow_g = int(g * glow_alpha)
                    glow_b = int(b * glow_alpha)
                    d.fill_rect_sync(
                        x - 1,
                        y - 2,
                        bar_width + 2,
                        height + 4,
                        Color(glow_r // 3, glow_g // 3, glow_b // 2),
                    )

                d.fill_rect_sync(x, y, bar_width, height, bar_color)

                if height > 6:
                    highlight_h = max(2, height // 6)
                    d.fill_rect_sync(
                        x + 1,
                        y + 1,
                        max(1, bar_width - 2),
                        highlight_h,
                        Color(min(255, r + 40), min(255, g + 30), min(255, b + 20)),
                    )
            else:
                d.fill_rect_sync(x, cy - 1, bar_width, 2, Color(40, 50, 60))

    def start_waveform_sync(self) -> None:
        """Synchronously activate waveform display (called from audio thread)."""
        if (
            not self._display
            or self._mode == DisplayMode.OFF
            or self._has_tool_animation
        ):
            return
        self._waveform_active = True
        self._waveform_explicitly_started = True
        self._last_activity_time = time.time()
        # Signal activity to wake screensaver immediately
        if self._screensaver_active:
            signal_activity()

    def stop_waveform_sync(self) -> None:
        """Synchronously deactivate waveform display."""
        self._waveform_active = False
        self._waveform_explicitly_started = False

    async def start_waveform(self, source: str = "microphone") -> None:
        if source == "output":
            return
        self.start_waveform_sync()

    async def stop_waveform(self) -> None:
        self.stop_waveform_sync()

    async def show_spotify_now_playing(
        self,
        track: str,
        artist: str,
        album: str = "",
        album_art_url: Optional[str] = None,
        progress_pct: float = 0.0,
        progress_ms: int = 0,
        duration_ms: int = 0,
    ) -> None:
        """Show Spotify now playing display - always takes priority when Spotify is playing."""
        if not self._display:
            return

        # Wake up from screensaver if Spotify starts playing
        if self._screensaver_active:
            logger.debug("Waking from screensaver for Spotify playback")
            await self._deactivate_screensaver()

        # Check if track changed (forces album art reload)
        track_changed = track != self._spotify_track

        # Update state
        self._spotify_track = track
        self._spotify_artist = artist
        self._spotify_album = album
        self._spotify_progress = progress_pct
        self._spotify_progress_ms = progress_ms
        self._spotify_duration_ms = duration_ms

        # Fetch album art if URL changed OR track changed
        if album_art_url and (
            album_art_url != self._spotify_album_art_url or track_changed
        ):
            self._spotify_album_art_url = album_art_url
            self._spotify_album_art = None  # Reset to trigger re-decode in loop
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        album_art_url, timeout=aiohttp.ClientTimeout(total=5)
                    ) as resp:
                        if resp.status == 200:
                            self._spotify_album_art = await resp.read()
            except Exception:
                self._spotify_album_art = None
        elif not album_art_url and track_changed:
            # New track has no art - clear the old art
            self._spotify_album_art_url = None
            self._spotify_album_art = None

        # If not already showing Spotify, start the loop
        if not self._spotify_active:
            logger.debug("Starting Spotify display: %s - %s", track, artist)
            self._spotify_active = True
            await self._stop_render()
            self._stop_requested = False
            self._spotify_task = asyncio.create_task(spotify_now_playing_loop(self))

    async def stop_spotify_now_playing(self) -> None:
        if not self._spotify_active:
            return

        self._spotify_active = False
        self._spotify_album_art = None
        self._spotify_album_art_url = None

        if self._spotify_task:
            self._spotify_task.cancel()
            try:
                await self._spotify_task
            except asyncio.CancelledError:
                pass
            self._spotify_task = None

        # Resume normal mode
        if not self._screensaver_active:
            await self._start_mode_loop()

    async def resume_idle(self) -> None:
        """Resume idle state and restart mode loop."""
        if self._screensaver_active:
            return

        if self._state == AnimationState.IDLE and self._render_task:
            return

        logger.debug("Resuming idle")
        self._streaming_text = ""
        self._has_tool_animation = False
        self._tool_animation_start = 0.0
        self._state = AnimationState.IDLE
        self._waveform_active = False
        self._waveform_explicitly_started = False

        await self._stop_render()
        await self._start_mode_loop()

    def set_gallery_images(self, images: List[str]) -> None:
        self._gallery_images = images
        self._gallery_index = 0

    def set_gallery_interval(self, interval: float) -> None:
        self._gallery_interval = max(3.0, min(60.0, interval))

    def set_weather_data(self, data: Dict[str, Any]) -> None:
        old_temp = self._weather_data.get("temperature") if self._weather_data else None
        new_temp = data.get("temperature")
        if old_temp != new_temp:
            logger.debug(
                "Weather updated: %s° %s in %s",
                new_temp,
                data.get("condition", ""),
                data.get("location", ""),
            )
        self._weather_data = data

    async def _fetch_weather_data(self, location: Optional[str] = None) -> None:
        """Fetch weather data and update the manager's weather state."""
        await fetch_weather_data(location=location, on_data=self.set_weather_data)

    async def shutdown(self) -> None:
        await self._stop_render()
        if self._display:
            # Clear and restore TTY
            self._display.clear_sync(Color(0, 0, 0))
            self._display.show_sync()
            self._restore_tty()
            await self._display.shutdown()

    # -------------------------------------------------------------------------
    # Drawing Helpers
    # -------------------------------------------------------------------------

    def _draw_glow(self, d, phase: float) -> None:
        """Draw subtle accent glow."""
        cx = d.width // 2 + int(math.sin(phase * 0.5) * d.scale_x(40))
        cy = d.height // 3
        for i in range(5, 0, -1):
            alpha = 0.025 * i
            radius = d.scale_x(50 + i * 30)
            r = int(100 * alpha)
            g = int(102 * alpha)
            b = int(241 * alpha)
            d.draw_circle_sync(cx, cy, radius, Color(r, g, b), filled=True)

    # -------------------------------------------------------------------------
    # User Message Animation
    # -------------------------------------------------------------------------

    async def _animate_user_bubble(
        self, message: str, display_duration: float = 3.0
    ) -> None:
        d = self._display
        if not d:
            return

        padding = d.scale_x(35)
        inner_padding = d.scale_x(20)

        if len(message) > 100:
            font_size = d.scale_font(16)
            max_lines = 5
        elif len(message) > 60:
            font_size = d.scale_font(18)
            max_lines = 4
        else:
            font_size = d.scale_font(22)
            max_lines = 3

        max_bubble_w = d.width - padding * 2
        text_area_w = max_bubble_w - inner_padding * 2

        test_char_w, _ = d.get_text_size("M", font_size)
        chars_per_line = max(10, int(text_area_w / test_char_w))

        lines = wrap_text(message, chars_per_line)
        line_height = font_size + d.scale_y(6)
        visible_lines = lines[:max_lines]

        if len(lines) > max_lines and len(visible_lines[-1]) > 3:
            visible_lines[-1] = visible_lines[-1][:-3] + "..."

        max_line_w = 0
        for line in visible_lines:
            line_w, _ = d.get_text_size(line, font_size)
            max_line_w = max(max_line_w, line_w)

        bubble_w = min(max_bubble_w, max_line_w + inner_padding * 2)
        bubble_h = len(visible_lines) * line_height + d.scale_y(20)

        fade_in_duration = 0.4
        hold_duration = max(1.5, display_duration - 0.8)
        fade_out_duration = 0.4

        start_time = time.perf_counter()
        total_duration = fade_in_duration + hold_duration + fade_out_duration

        start_x = d.width + d.scale_x(20)
        end_x = d.width - padding - bubble_w
        bubble_y = d.scale_y(45)

        while True:
            if self._stop_requested:
                return

            elapsed = time.perf_counter() - start_time

            # Determine animation phase and calculate progress
            if elapsed < fade_in_duration:
                # Fade in phase - slide in from right with opacity
                phase_t = elapsed / fade_in_duration
                ease_t = ease_out_cubic(phase_t)
                bubble_x = int(lerp(start_x, end_x, ease_t))
                opacity = ease_t
            elif elapsed < fade_in_duration + hold_duration:
                # Hold phase - fully visible
                bubble_x = end_x
                opacity = 1.0
            elif elapsed < total_duration:
                # Fade out phase - slide out to right with fade
                phase_t = (
                    elapsed - fade_in_duration - hold_duration
                ) / fade_out_duration
                ease_t = ease_out_quad(phase_t)
                bubble_x = int(lerp(end_x, start_x, ease_t))
                opacity = 1.0 - ease_t
            else:
                break

            async with self._render_lock:
                draw_gradient_bg(d)

                # Only draw if visible
                if opacity > 0.05:
                    # Shadow with opacity
                    if opacity > 0.3:
                        shadow_alpha = opacity * 0.4
                        d.draw_rounded_rect_sync(
                            bubble_x + 4,
                            bubble_y + 4,
                            bubble_w,
                            bubble_h,
                            d.scale_x(12),
                            Color(
                                int(10 * shadow_alpha),
                                int(10 * shadow_alpha),
                                int(15 * shadow_alpha),
                            ),
                        )

                    # Bubble color with opacity
                    base_color = (100, 102, 241)  # Purple-ish
                    color = Color(
                        int(base_color[0] * opacity),
                        int(base_color[1] * opacity),
                        int(base_color[2] * opacity),
                    )
                    d.draw_rounded_rect_sync(
                        bubble_x, bubble_y, bubble_w, bubble_h, d.scale_x(12), color
                    )

                    if opacity > 0.2:
                        text_alpha = min(1.0, opacity * 1.2)
                        text_color = Color(
                            int(255 * text_alpha),
                            int(255 * text_alpha),
                            int(255 * text_alpha),
                        )
                        text_y = bubble_y + d.scale_y(10)
                        for line in visible_lines:
                            line_w, _ = d.get_text_size(line, font_size)
                            if line_w > bubble_w - inner_padding * 2:
                                available = bubble_w - inner_padding * 2 - d.scale_x(20)
                                ratio = available / line_w if line_w > 0 else 1
                                cut_idx = max(1, int(len(line) * ratio))
                                line = line[:cut_idx] + "..."
                            d.draw_text_sync(
                                line,
                                bubble_x + inner_padding,
                                text_y,
                                text_color,
                                font_size,
                            )
                            text_y += line_height

                d.show_sync()

            await asyncio.sleep(FRAME_TIME)

    # -------------------------------------------------------------------------
    # Response Animation
    # -------------------------------------------------------------------------

    async def _animate_response_bubble(self, response: str) -> None:
        d = self._display
        if not d:
            return

        padding = d.scale_x(35)
        max_width = d.width - padding * 2
        font_size = d.scale_font(19)
        lines = wrap_text(response, (max_width - d.scale_x(40)) // (font_size // 2))
        line_height = font_size + d.scale_y(6)
        bubble_h = min(
            len(lines[:6]) * line_height + d.scale_y(30),
            d.height - d.scale_y(80),
        )
        bubble_w = max_width
        bubble_x = padding
        bubble_y = d.scale_y(70)

        start_time = time.perf_counter()
        duration = 0.12

        while True:
            if self._stop_requested:
                return

            elapsed = time.perf_counter() - start_time
            t = min(1.0, elapsed / duration)
            ease_t = ease_out_cubic(t)

            async with self._render_lock:
                draw_gradient_bg(d)

                scale = 0.92 + 0.08 * ease_t
                sw = int(bubble_w * scale)
                sh = int(bubble_h * scale)
                ox = (bubble_w - sw) // 2
                oy = (bubble_h - sh) // 2

                d.draw_rounded_rect_sync(
                    bubble_x + ox + 3,
                    bubble_y + oy + 3,
                    sw,
                    sh,
                    d.scale_x(12),
                    Color(0, 0, 0),
                )
                d.draw_rounded_rect_sync(
                    bubble_x + ox, bubble_y + oy, sw, sh, d.scale_x(12), Palette.BG_CARD
                )

                if t > 0.1:
                    text_y = bubble_y + oy + d.scale_y(15)
                    for line in lines[:6]:
                        d.draw_text_sync(
                            line,
                            bubble_x + ox + d.scale_x(18),
                            text_y,
                            Palette.TEXT_PRIMARY,
                            font_size,
                        )
                        text_y += line_height

                d.show_sync()

            if t >= 1.0:
                break
            await asyncio.sleep(FRAME_TIME)

    # -------------------------------------------------------------------------
    # Streaming Text
    # -------------------------------------------------------------------------

    async def _render_streaming_text(self) -> None:
        d = self._display
        if not d:
            return

        async with self._render_lock:
            draw_gradient_bg(d)

            padding = d.scale_x(25)
            bubble_w = d.width - padding * 2
            bubble_y = d.scale_y(70)
            font_size = d.scale_font(18)
            lines = wrap_text(
                self._streaming_text, (bubble_w - d.scale_x(35)) // (font_size // 2)
            )
            visible = lines[-5:] if len(lines) > 5 else lines
            bubble_h = len(visible) * (font_size + d.scale_y(6)) + d.scale_y(35)

            d.draw_rounded_rect_sync(
                padding + 3,
                bubble_y + 3,
                bubble_w,
                bubble_h,
                d.scale_x(14),
                Color(0, 0, 0),
            )
            d.draw_rounded_rect_sync(
                padding, bubble_y, bubble_w, bubble_h, d.scale_x(14), Palette.BG_CARD
            )

            text_y = bubble_y + d.scale_y(18)
            for line in visible:
                d.draw_text_sync(
                    line,
                    padding + d.scale_x(18),
                    text_y,
                    Palette.TEXT_PRIMARY,
                    font_size,
                )
                text_y += font_size + d.scale_y(6)

            d.show_sync()
