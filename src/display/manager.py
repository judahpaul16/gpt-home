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

from .base import BaseDisplay, Color, DisplayMode
from .detection import detect_displays
from .factory import DisplayFactory

_src_dir = str(Path(__file__).parent.parent)
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

try:
    from src.audio_activity import get_audio_activity_detector
except ImportError:
    get_audio_activity_detector = None

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

logger = logging.getLogger(__name__)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * min(1.0, max(0.0, t))


def ease_out_cubic(t: float) -> float:
    return 1.0 - pow(1.0 - min(1.0, max(0.0, t)), 3)


def ease_out_quad(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return 1.0 - (1.0 - t) * (1.0 - t)


def ease_in_out_sine(t: float) -> float:
    return -(math.cos(math.pi * t) - 1) / 2


class AnimationState(Enum):
    IDLE = auto()
    USER_MESSAGE = auto()
    TOOL_ANIMATION = auto()
    RESPONSE = auto()
    STREAMING = auto()


class Palette:
    BG_DARK = Color(30, 35, 55)
    BG_MID = Color(40, 48, 75)
    BG_CARD = Color(55, 65, 100)
    BG_ELEVATED = Color(70, 82, 120)
    ACCENT_BLUE = Color(100, 140, 255)
    ACCENT_PURPLE = Color(180, 130, 255)
    ACCENT_CYAN = Color(80, 230, 255)
    ACCENT_GREEN = Color(70, 230, 170)
    ACCENT_ORANGE = Color(255, 170, 90)
    ACCENT_PINK = Color(255, 140, 200)
    SPOTIFY_GREEN = Color(30, 215, 96)
    TEXT_PRIMARY = Color(255, 255, 255)
    TEXT_SECONDARY = Color(200, 210, 230)
    TEXT_MUTED = Color(150, 165, 195)


class ScrollingText:
    """Handles Spotify-style scrolling text animation.

    Behavior matches Spotify:
    - Text starts visible, pauses for a moment
    - Scrolls left to show full text
    - Pauses at the end
    - Scrolls back (or jumps back) to start
    - Repeats
    """

    def __init__(
        self, text: str, max_width: int, font_size: int, char_width_ratio: float = 0.55
    ):
        self.text = text
        self.max_width = max_width
        self.font_size = font_size
        self.char_width = int(font_size * char_width_ratio)

        # Calculate if scrolling is needed
        self.text_width = len(text) * self.char_width
        self.needs_scroll = self.text_width > max_width

        # Scrolling state
        self.scroll_offset = 0.0
        self.scroll_speed = 50.0  # pixels per second
        self.pause_time = 2.0  # seconds to pause at each end
        self.pause_timer = self.pause_time  # Start with a pause
        self.scroll_direction = 1  # 1 = left, -1 = right (back)
        self.state = "pause_start"  # pause_start, scrolling, pause_end, scrolling_back

    def update(self, dt: float) -> None:
        """Update scroll position. Call every frame."""
        if not self.needs_scroll:
            return

        max_scroll = (
            self.text_width - self.max_width + self.char_width * 2
        )  # Extra padding

        if self.state == "pause_start":
            self.pause_timer -= dt
            if self.pause_timer <= 0:
                self.state = "scrolling"
                self.scroll_direction = 1

        elif self.state == "scrolling":
            self.scroll_offset += self.scroll_speed * dt
            if self.scroll_offset >= max_scroll:
                self.scroll_offset = max_scroll
                self.state = "pause_end"
                self.pause_timer = self.pause_time

        elif self.state == "pause_end":
            self.pause_timer -= dt
            if self.pause_timer <= 0:
                self.state = "scrolling_back"

        elif self.state == "scrolling_back":
            self.scroll_offset -= self.scroll_speed * 1.5 * dt  # Scroll back faster
            if self.scroll_offset <= 0:
                self.scroll_offset = 0
                self.state = "pause_start"
                self.pause_timer = self.pause_time

    def get_offset(self) -> int:
        """Get current scroll offset in pixels."""
        return int(self.scroll_offset)

    def reset(self, new_text: str = None) -> None:
        """Reset scrolling state, optionally with new text."""
        if new_text is not None:
            self.text = new_text
            self.text_width = len(new_text) * self.char_width
            self.needs_scroll = self.text_width > self.max_width
        self.scroll_offset = 0.0
        self.pause_timer = self.pause_time
        self.state = "pause_start"


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
        self._waveform_values: List[float] = [0.0] * 32
        self._waveform_lock = threading.Lock()
        self._waveform_active: bool = False
        self._waveform_explicitly_started: bool = False
        self._waveform_smoothed: List[float] = [0.0] * 32
        self._init_waveform_thresholds()
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
        # Spotify now playing state
        self._spotify_active: bool = False
        self._spotify_track: str = ""
        self._spotify_artist: str = ""
        self._spotify_album: str = ""
        self._spotify_album_art: Optional[bytes] = None
        self._spotify_album_art_url: Optional[str] = None
        self._spotify_progress: float = 0.0
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
                except Exception as e:
                    logger.debug(f"Error during display cleanup: {e}")
            cls._instance._display = None
            cls._instance._display_initialized = False
            logger.info("DisplayManager instance reset for reinitialization")

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

        full_display = DisplayFactory.auto_detect_full_display()

        if preferred_type and preferred_type not in ["i2c"]:
            displays = detect_displays()
            for info in displays:
                if info.screen_type.value == preferred_type:
                    display = DisplayFactory.create(info)
                    if display and display.supports_modes:
                        full_display = display
                        logger.debug(f"Using preferred display type: {preferred_type}")
                        break

        if full_display:
            self._display = full_display
            success = await self._display.initialize()
            if success:
                self._display_initialized = True
                self._build_gradient_cache()

                # Load saved display mode from settings
                saved_mode = self._load_saved_mode()
                if saved_mode and saved_mode != self._mode:
                    logger.debug(f"Restoring saved display mode: {saved_mode.name}")
                    self._mode = saved_mode

                # Ensure stop flag is clear before starting
                self._stop_requested = False
                self._frame = 0

                # Load screensaver settings
                self._load_screensaver_settings()
                self._last_activity_time = time.time()

                # Start the render loop
                logger.debug(
                    f"Starting initial render loop for mode: {self._mode.name}"
                )
                await self._start_mode_loop()

                # Always start screensaver activity monitor (it checks enabled flag internally)
                # This ensures the monitor is running and can activate when settings change
                self._screensaver_task = asyncio.create_task(
                    self._screensaver_monitor_loop()
                )
            return success

        logger.debug(
            "No full display found - display modes disabled (I2C is text-only)"
        )
        self._display_initialized = True  # Mark as initialized even if no display
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
        except Exception as e:
            logger.debug(f"Could not load saved display mode: {e}")
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
                logger.debug(
                    f"Screensaver settings: enabled={self._screensaver_enabled}, "
                    f"timeout={self._screensaver_timeout}s, style={self._screensaver_style}"
                )
        except Exception as e:
            logger.debug(f"Could not load screensaver settings: {e}")

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
        """Activate screensaver - pauses current mode and shows screensaver animation."""
        if self._screensaver_active:
            logger.debug("_activate_screensaver called but already active")
            return
        if not self._display:
            logger.debug("_activate_screensaver called but no display available")
            return
        if self._mode == DisplayMode.OFF:
            logger.debug("_activate_screensaver called but display is OFF")
            return

        logger.info(
            f"Activating screensaver (current mode: {self._mode.name}, style: {self._screensaver_style})"
        )
        self._screensaver_active = True

        # Stop current render task
        logger.debug("Stopping current render task for screensaver...")
        await self._stop_render()

        # Start screensaver render task
        self._stop_requested = False
        logger.debug("Starting screensaver render task...")
        self._screensaver_render_task = asyncio.create_task(self._screensaver_loop())
        logger.info("Screensaver render task started")

    async def _deactivate_screensaver(self) -> None:
        """Deactivate screensaver and resume the current mode's display."""
        if not self._screensaver_active and self._screensaver_render_task is None:
            return

        logger.info(f"Deactivating screensaver, resuming mode: {self._mode.name}")
        self._screensaver_active = False
        self._stop_requested = True

        if self._screensaver_render_task and not self._screensaver_render_task.done():
            self._screensaver_render_task.cancel()
            try:
                await asyncio.wait_for(self._screensaver_render_task, timeout=0.3)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        self._screensaver_render_task = None

        self._stop_requested = False
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

        elapsed = time.time() - self._last_activity_time
        if elapsed >= self._screensaver_timeout:
            logger.info(f"Activating screensaver after {elapsed:.0f}s of inactivity")
            await self._activate_screensaver()

    async def _screensaver_monitor_loop(self) -> None:
        """Background task to monitor inactivity and activate screensaver."""
        logger.info("Screensaver monitor loop started")
        try:
            while True:
                await asyncio.sleep(10)
                await self._check_screensaver_timeout()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Screensaver monitor error: {e}")

    async def reinitialize(self) -> bool:
        """Reinitialize the display manager to detect newly connected displays.

        This is the hotswap entry point - call this when displays are
        connected or disconnected to re-scan and reinitialize.

        Returns:
            True if a full display was found and initialized
        """
        logger.info("Reinitializing display manager (hotswap)...")
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
            logger.warning("set_mode called but no display available")
            return

        if self._screensaver_active:
            self._mode = mode
            logger.debug(
                f"set_mode: screensaver active, mode stored as {mode.name} but not starting loop"
            )
            return

        if self._mode == mode:
            logger.debug(f"set_mode: already in mode {mode.name}")
            return

        logger.info(f"Changing display mode from {self._mode.name} to {mode.name}")

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
                logger.info("Display turned off, TTY restored")
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
                    logger.info("TTY restored to text mode")
            except Exception as e:
                logger.debug(f"Could not restore TTY: {e}")

    async def _start_mode_loop(self) -> None:
        """Start the render loop for current mode."""
        current_mode = self._mode

        if self._screensaver_active:
            logger.debug("_start_mode_loop: screensaver active, not starting loop")
            return

        if current_mode == DisplayMode.OFF:
            logger.debug("_start_mode_loop: mode is OFF, not starting loop")
            return

        if not self._display:
            logger.warning("_start_mode_loop: no display available")
            return

        # Ensure no existing task is running
        if self._render_task and not self._render_task.done():
            logger.warning("Render task still running, stopping it first")
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

        # For SMART mode, start in idle (clock) but can be interrupted by tools
        # For other modes, they are STATIC and run their dedicated loop continuously
        if current_mode == DisplayMode.SMART:
            self._state = AnimationState.IDLE
            self._render_task = asyncio.create_task(self._clock_loop())
        elif current_mode == DisplayMode.CLOCK:
            self._render_task = asyncio.create_task(self._clock_loop())
        elif current_mode == DisplayMode.WEATHER:
            self._render_task = asyncio.create_task(self._weather_loop())
        elif current_mode == DisplayMode.GALLERY:
            self._render_task = asyncio.create_task(self._gallery_loop())
        elif current_mode == DisplayMode.WAVEFORM:
            self._render_task = asyncio.create_task(self._waveform_loop())
        else:
            logger.warning(f"Unknown display mode: {current_mode}")

    async def _stop_render(self) -> None:
        """Stop the current render task."""
        self._stop_requested = True

        if self._render_task and not self._render_task.done():
            logger.debug("Cancelling existing render task")
            self._render_task.cancel()
            try:
                await asyncio.wait_for(self._render_task, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            logger.debug("Render task stopped")

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
            self._render_task = asyncio.create_task(
                self._weather_loop(fetch_forecast=True, location=requested_location)
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

                    self._draw_gradient_bg(d)
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
        except Exception as e:
            logger.debug(f"Could not fetch Spotify data: {e}")
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
        except Exception as e:
            logger.debug(f"Could not load album art: {e}")
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

                    self._draw_host_ip_overlay(d)
                    d.show_sync()

                await asyncio.sleep(
                    max(0.001, FRAME_TIME - (time.perf_counter() - now))
                )

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Music animation error: {e}")

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

    def set_waveform_values(self, values: list, has_voice: bool = False) -> None:
        """Set waveform values directly (called from common.py during listening).

        Args:
            values: List of 32 amplitude values
            has_voice: Whether audio amplitude exceeds threshold
        """
        if len(values) != 32:
            return

        float_values = [float(v) for v in values]

        with self._waveform_lock:
            self._waveform_values = float_values

        if has_voice and self._screensaver_active:
            signal_activity()

    def _render_waveform_inline(self, d, dt: float) -> None:
        """Render waveform bars inline within any mode loop."""
        with self._waveform_lock:
            waveform_snapshot = list(self._waveform_values)

        current_max = max(waveform_snapshot) if waveform_snapshot else 0.0
        has_audio = current_max > self._waveform_hide_threshold

        cx, cy = d.get_center()
        bar_count = 32
        total_bar_area = d.width - d.scale_x(80)
        bar_width = max(8, total_bar_area // (bar_count + bar_count // 2))
        spacing = max(3, bar_width // 3)
        total_width = bar_count * (bar_width + spacing) - spacing
        start_x = cx - total_width // 2

        max_val = max(0.08, current_max)

        for i in range(bar_count):
            x = start_x + i * (bar_width + spacing)
            pos_factor = i / (bar_count - 1)

            if has_audio and i < len(waveform_snapshot):
                raw_val = waveform_snapshot[i] / max_val
                target = min(1.0, raw_val * 1.2)
            else:
                target = 0.0

            current = self._waveform_smoothed[i]
            if target > current:
                self._waveform_smoothed[i] = lerp(current, target, min(1.0, dt * 28))
            else:
                self._waveform_smoothed[i] = lerp(current, target, min(1.0, dt * 12))

            val = self._waveform_smoothed[i]
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

    async def start_waveform(self, source: str = "microphone") -> None:
        if source == "output":
            return
        if not self._display:
            print("[WAVEFORM] start_waveform: no display", flush=True)
            return
        if self._mode == DisplayMode.OFF:
            print("[WAVEFORM] start_waveform: mode is OFF", flush=True)
            return
        if self._has_tool_animation:
            print("[WAVEFORM] start_waveform: blocked by tool animation", flush=True)
            return

        print(
            f"[WAVEFORM] start_waveform: activating (mode={self._mode.name})",
            flush=True,
        )
        self._waveform_active = True
        self._waveform_explicitly_started = True

        if self._screensaver_active:
            await self.register_activity_async()
        else:
            self._last_activity_time = time.time()

    async def update_waveform(self, amplitude: float) -> None:
        """Update waveform with a single amplitude value (fallback method)."""
        if self._waveform_active:
            amp = min(1.0, amplitude)
            with self._waveform_lock:
                self._waveform_values.pop(0)
                self._waveform_values.append(amp)

    async def stop_waveform(self) -> None:
        """Stop waveform visualization."""
        print("[WAVEFORM] stop_waveform called", flush=True)
        self._waveform_active = False
        self._waveform_explicitly_started = False
        with self._waveform_lock:
            self._waveform_values = [0.0] * 32

    async def show_spotify_now_playing(
        self,
        track: str,
        artist: str,
        album: str = "",
        album_art_url: Optional[str] = None,
        progress_pct: float = 0.0,
    ) -> None:
        """Show Spotify now playing display - always takes priority when Spotify is playing."""
        if not self._display:
            return

        if self._screensaver_active:
            return

        # Update state
        self._spotify_track = track
        self._spotify_artist = artist
        self._spotify_album = album
        self._spotify_progress = progress_pct

        # Fetch album art only if URL changed (new track)
        if album_art_url and album_art_url != self._spotify_album_art_url:
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

        # If not already showing Spotify, start the loop
        if not self._spotify_active:
            print(
                f"[show_spotify_now_playing] Starting Spotify display: {track} - {artist}",
                flush=True,
            )
            self._spotify_active = True
            await self._stop_render()
            self._stop_requested = False
            self._spotify_task = asyncio.create_task(self._spotify_now_playing_loop())

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

    async def _spotify_now_playing_loop(self) -> None:
        try:
            smoothed_progress = self._spotify_progress
            album_art_img = None
            last_art_id = None
            last_frame = time.perf_counter()

            # Scrolling text state for this loop
            track_scroller: Optional[ScrollingText] = None
            artist_scroller: Optional[ScrollingText] = None
            last_track = ""
            last_artist = ""

            while (
                self._spotify_active
                and not self._stop_requested
                and not self._screensaver_active
            ):
                now = time.perf_counter()
                dt = now - last_frame
                last_frame = now

                async with self._render_lock:
                    d = self._display
                    if not d or self._stop_requested or self._screensaver_active:
                        break

                    d.clear_sync(Color(18, 18, 24))
                    cx, cy = d.get_center()
                    w = d.width
                    h = d.height

                    if (
                        self._spotify_album_art
                        and id(self._spotify_album_art) != last_art_id
                    ):
                        last_art_id = id(self._spotify_album_art)
                        try:
                            import io

                            from PIL import Image

                            img = Image.open(io.BytesIO(self._spotify_album_art))
                            art_size = min(d.scale_x(200), d.scale_y(200))
                            album_art_img = img.resize((art_size, art_size)).convert(
                                "RGB"
                            )
                        except Exception:
                            album_art_img = None

                    art_size = min(d.scale_x(200), d.scale_y(200))
                    art_x = cx - art_size // 2
                    art_y = d.scale_y(30)

                    if album_art_img:
                        if hasattr(d, "draw_pil_image_sync"):
                            d.draw_pil_image_sync(album_art_img, art_x, art_y)
                        else:
                            d.fill_rect_sync(
                                art_x, art_y, art_size, art_size, Color(40, 40, 50)
                            )
                    else:
                        d.fill_rect_sync(
                            art_x, art_y, art_size, art_size, Color(35, 35, 45)
                        )

                    # Text area with scrolling
                    text_y = art_y + art_size + d.scale_y(25)
                    margin = d.scale_x(40)
                    text_area_width = w - margin * 2

                    # Track name with scrolling
                    track_size = d.scale_font(24)
                    track_text = (
                        self._spotify_track if self._spotify_track else "Unknown Track"
                    )

                    # Reset scroller if track changed
                    if track_text != last_track or track_scroller is None:
                        track_scroller = ScrollingText(
                            track_text,
                            text_area_width,
                            track_size,
                            char_width_ratio=0.5,
                        )
                        last_track = track_text

                    track_scroller.update(dt)

                    # Center the text initially, scroll if needed
                    if track_scroller.needs_scroll:
                        scroll_offset = track_scroller.get_offset()
                        d.set_clip(
                            margin,
                            0,
                            text_area_width,
                            d.height,
                        )
                        d.draw_text_sync(
                            track_text,
                            margin - scroll_offset,
                            text_y,
                            Palette.TEXT_PRIMARY,
                            track_size,
                        )
                        d.clear_clip()
                    else:
                        # Center short text
                        text_w = len(track_text) * int(track_size * 0.5)
                        d.draw_text_sync(
                            track_text,
                            cx - text_w // 2,
                            text_y,
                            Palette.TEXT_PRIMARY,
                            track_size,
                        )

                    # Artist name with scrolling
                    artist_y = text_y + d.scale_y(32)
                    artist_size = d.scale_font(18)
                    artist_text = (
                        self._spotify_artist
                        if self._spotify_artist
                        else "Unknown Artist"
                    )

                    # Reset scroller if artist changed
                    if artist_text != last_artist or artist_scroller is None:
                        artist_scroller = ScrollingText(
                            artist_text,
                            text_area_width,
                            artist_size,
                            char_width_ratio=0.5,
                        )
                        last_artist = artist_text

                    artist_scroller.update(dt)

                    if artist_scroller.needs_scroll:
                        scroll_offset = artist_scroller.get_offset()
                        d.set_clip(
                            margin,
                            0,
                            text_area_width,
                            d.height,
                        )
                        d.draw_text_sync(
                            artist_text,
                            margin - scroll_offset,
                            artist_y,
                            Palette.TEXT_SECONDARY,
                            artist_size,
                        )
                        d.clear_clip()
                    else:
                        # Center short text
                        text_w = len(artist_text) * int(artist_size * 0.5)
                        d.draw_text_sync(
                            artist_text,
                            cx - text_w // 2,
                            artist_y,
                            Palette.TEXT_SECONDARY,
                            artist_size,
                        )

                    bar_y = h - d.scale_y(40)
                    bar_margin = d.scale_x(40)
                    bar_width = w - bar_margin * 2
                    bar_height = d.scale_y(4)

                    smoothed_progress = lerp(
                        smoothed_progress, self._spotify_progress, dt * 8
                    )
                    d.fill_rect_sync(
                        bar_margin, bar_y, bar_width, bar_height, Color(50, 50, 60)
                    )
                    progress_w = int(bar_width * smoothed_progress)
                    if progress_w > 0:
                        d.fill_rect_sync(
                            bar_margin,
                            bar_y,
                            progress_w,
                            bar_height,
                            Palette.SPOTIFY_GREEN,
                        )

                    d.fill_rect_sync(
                        w - d.scale_x(18),
                        d.scale_y(12),
                        d.scale_x(6),
                        d.scale_y(6),
                        Palette.SPOTIFY_GREEN,
                    )
                    self._draw_host_ip_overlay(d)
                    d.show_sync()

                await asyncio.sleep(
                    max(0.001, FRAME_TIME - (time.perf_counter() - now))
                )

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Spotify now playing loop error: {e}")

    async def resume_idle(self) -> None:
        """Resume idle state and restart mode loop."""
        if self._screensaver_active:
            print("[DISPLAY] resume_idle: screensaver active, skipping", flush=True)
            return

        if self._state == AnimationState.IDLE and self._render_task:
            print("[DISPLAY] resume_idle: already idle with render task", flush=True)
            return

        print(f"[DISPLAY] resume_idle: clearing tool animation", flush=True)
        self._streaming_text = ""
        self._has_tool_animation = False
        self._tool_animation_start = 0.0
        self._state = AnimationState.IDLE

        await self._stop_render()
        print(f"[DISPLAY] resume_idle: starting mode loop", flush=True)
        await self._start_mode_loop()
        print(f"[DISPLAY] resume_idle: done", flush=True)

    def set_gallery_images(self, images: List[str]) -> None:
        self._gallery_images = images
        self._gallery_index = 0

    def set_gallery_interval(self, interval: float) -> None:
        self._gallery_interval = max(3.0, min(60.0, interval))

    def set_weather_data(self, data: Dict[str, Any]) -> None:
        old_temp = self._weather_data.get("temperature") if self._weather_data else None
        new_temp = data.get("temperature")
        if old_temp != new_temp:
            logger.info(
                f"Weather data updated: {new_temp}° {data.get('condition', '')} in {data.get('location', '')}"
            )
        self._weather_data = data

    async def _fetch_weather_data(self, location: Optional[str] = None) -> None:
        try:
            try:
                from src.common import load_settings
            except ImportError:
                from common import load_settings

            settings = load_settings()
            lat = None
            lon = None
            city = ""

            if location:
                city = location
                try:
                    async with aiohttp.ClientSession() as session:
                        geo_response = await session.get(
                            f"https://nominatim.openstreetmap.org/search?q={location}&format=json",
                            headers={"User-Agent": "GPT-Home/1.0"},
                            timeout=5,
                        )
                        if geo_response.status == 200:
                            geo_data = await geo_response.json()
                            if geo_data:
                                lat = float(geo_data[0]["lat"])
                                lon = float(geo_data[0]["lon"])
                except Exception as geo_err:
                    logger.debug(f"Weather: Geocoding failed for {location}: {geo_err}")

            if not lat or not lon:
                lat = settings.get("lat")
                lon = settings.get("lon")
                city = settings.get("city", "") or city

            if not lat or not lon:
                try:
                    async with aiohttp.ClientSession() as session:
                        geo_response = await session.get(
                            "http://ip-api.com/json/?fields=lat,lon,city", timeout=5
                        )
                        if geo_response.status == 200:
                            geo_data = await geo_response.json()
                            lat = geo_data.get("lat")
                            lon = geo_data.get("lon")
                            if not city:
                                city = geo_data.get("city", "")
                except Exception as geo_err:
                    logger.debug(f"Weather: IP geolocation failed: {geo_err}")

            if not lat or not lon:
                logger.warning("Weather: Could not determine location")
                self.set_weather_data(
                    {
                        "temperature": 70,
                        "condition": "Clear",
                        "location": "Unknown",
                        "high": 75,
                        "low": 65,
                        "forecast": [],
                    }
                )
                return

            api_key = os.getenv("OPEN_WEATHER_API_KEY")
            async with aiohttp.ClientSession() as session:
                # Try OpenWeatherMap first if API key is set
                if api_key:
                    try:
                        response = await session.get(
                            f"https://api.openweathermap.org/data/3.0/onecall?"
                            f"lat={lat}&lon={lon}&appid={api_key}&units=imperial"
                            f"&exclude=minutely,hourly,alerts",
                            timeout=10,
                        )
                        if response.status == 200:
                            data = await response.json()
                            current = data.get("current", {})
                            weather_info = current.get("weather", [{}])[0]
                            daily = data.get("daily", [])

                            # Build forecast from daily data
                            forecast = []
                            day_names = [
                                "Sun",
                                "Mon",
                                "Tue",
                                "Wed",
                                "Thu",
                                "Fri",
                                "Sat",
                            ]
                            for i, day_data in enumerate(daily[:7]):
                                dt = datetime.fromtimestamp(day_data.get("dt", 0))
                                day_weather = day_data.get("weather", [{}])[0]
                                forecast.append(
                                    {
                                        "day": day_names[dt.weekday()]
                                        if i > 0
                                        else "Today",
                                        "high": round(
                                            day_data.get("temp", {}).get("max", 0)
                                        ),
                                        "low": round(
                                            day_data.get("temp", {}).get("min", 0)
                                        ),
                                        "condition": day_weather.get("main", "Clear"),
                                    }
                                )

                            today = daily[0] if daily else {}
                            self.set_weather_data(
                                {
                                    "temperature": round(current.get("temp", 0)),
                                    "condition": weather_info.get("main", "Clear"),
                                    "location": city,
                                    "high": round(today.get("temp", {}).get("max", 0))
                                    if today
                                    else None,
                                    "low": round(today.get("temp", {}).get("min", 0))
                                    if today
                                    else None,
                                    "forecast": forecast,
                                }
                            )
                            return
                    except Exception as owm_err:
                        logger.debug(f"Weather: OpenWeatherMap failed: {owm_err}")

                # Fallback to Open-Meteo (free, no API key) with daily forecast
                response = await session.get(
                    f"https://api.open-meteo.com/v1/forecast?"
                    f"latitude={lat}&longitude={lon}"
                    f"&current=temperature_2m,weather_code"
                    f"&daily=temperature_2m_max,temperature_2m_min,weather_code"
                    f"&temperature_unit=fahrenheit"
                    f"&timezone=auto",
                    timeout=10,
                )
                if response.status == 200:
                    data = await response.json()
                    current = data.get("current", {})
                    temp = current.get("temperature_2m")
                    weather_code = current.get("weather_code", 0)
                    condition = self._wmo_code_to_condition(weather_code)

                    # Parse daily forecast
                    daily = data.get("daily", {})
                    dates = daily.get("time", [])
                    highs = daily.get("temperature_2m_max", [])
                    lows = daily.get("temperature_2m_min", [])
                    codes = daily.get("weather_code", [])

                    forecast = []
                    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
                    for i in range(min(7, len(dates))):
                        try:
                            dt = datetime.strptime(dates[i], "%Y-%m-%d")
                            day_name = "Today" if i == 0 else day_names[dt.weekday()]
                            forecast.append(
                                {
                                    "day": day_name,
                                    "high": round(highs[i]) if i < len(highs) else None,
                                    "low": round(lows[i]) if i < len(lows) else None,
                                    "condition": self._wmo_code_to_condition(
                                        codes[i] if i < len(codes) else 0
                                    ),
                                }
                            )
                        except (ValueError, IndexError):
                            continue

                    today_high = round(highs[0]) if highs else None
                    today_low = round(lows[0]) if lows else None

                    self.set_weather_data(
                        {
                            "temperature": round(temp) if temp is not None else None,
                            "condition": condition,
                            "location": city,
                            "high": today_high,
                            "low": today_low,
                            "forecast": forecast,
                        }
                    )
                    return
        except Exception as e:
            logger.warning(f"Weather: Failed to fetch data: {e}")
            self.set_weather_data(
                {
                    "temperature": 70,
                    "condition": "Clear",
                    "location": "Unknown",
                    "high": 75,
                    "low": 65,
                    "forecast": [],
                }
            )

    def _wmo_code_to_condition(self, code: int) -> str:
        """Convert WMO weather code to simple condition string."""
        if code == 0:
            return "Clear"
        elif code in (1, 2, 3):
            return "Cloudy"
        elif code in (45, 48):
            return "Fog"
        elif code in (51, 53, 55, 56, 57):
            return "Drizzle"
        elif code in (61, 63, 65, 66, 67, 80, 81, 82):
            return "Rain"
        elif code in (71, 73, 75, 77, 85, 86):
            return "Snow"
        elif code in (95, 96, 99):
            return "Thunderstorm"
        else:
            return "Clear"

    async def shutdown(self) -> None:
        await self._stop_render()
        if self._display:
            # Clear and restore TTY
            self._display.clear_sync(Color(0, 0, 0))
            self._display.show_sync()
            self._restore_tty()
            await self._display.shutdown()

    # -------------------------------------------------------------------------
    # Text Utilities
    # -------------------------------------------------------------------------

    def _wrap_text(self, text: str, max_chars: int) -> List[str]:
        """Wrap text to fit within max characters per line."""
        if not text:
            return []

        words = text.split()
        lines = []
        current_line = ""

        for word in words:
            if not current_line:
                current_line = word
            elif len(current_line) + 1 + len(word) <= max_chars:
                current_line += " " + word
            else:
                lines.append(current_line)
                current_line = word

        if current_line:
            lines.append(current_line)

        return lines

    # -------------------------------------------------------------------------
    # Background Drawing
    # -------------------------------------------------------------------------

    def _draw_gradient_bg(self, d) -> None:
        """Draw clean solid dark background."""
        bg = getattr(self, "_bg_color", Color(18, 20, 28))
        d.clear_sync(bg)

    def _draw_weather_bg(self, d, top: tuple, bottom: tuple) -> None:
        """Draw weather-themed gradient."""
        for y in range(d.height):
            t = y / d.height
            # Subtle dithering for smooth gradients
            noise = ((y * 23) % 9 - 4) / 512.0
            t = max(0.0, min(1.0, t + noise))
            r = int(top[0] + (bottom[0] - top[0]) * t)
            g = int(top[1] + (bottom[1] - top[1]) * t)
            b = int(top[2] + (bottom[2] - top[2]) * t)
            d.fill_rect_sync(0, y, d.width, 1, Color(r, g, b))

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

    def _get_cpu_temp(self) -> Optional[int]:
        """Get CPU temperature in Celsius."""
        try:
            output = subprocess.check_output(["vcgencmd", "measure_temp"]).decode()
            return int(float(output.split("=")[1].split("'")[0]))
        except Exception:
            return None

    def _draw_host_ip_overlay(self, d) -> None:
        """Draw host IP address in top-left and CPU temp in top-right."""
        font_size = d.scale_font(12)
        padding = d.scale_x(5)

        host_ip = self._get_host_ip()
        if host_ip:
            d.draw_text_sync(
                host_ip,
                padding,
                padding,
                Color(100, 110, 130),
                font_size,
            )

        cpu_temp = self._get_cpu_temp()
        if cpu_temp is not None:
            temp_str = f"CPU: {cpu_temp}°C"
            text_width, _ = d.get_text_size(temp_str, font_size)
            d.draw_text_sync(
                temp_str,
                d.width - text_width - padding,
                padding,
                Color(100, 110, 130),
                font_size,
            )

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

        lines = self._wrap_text(message, chars_per_line)
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
                self._draw_gradient_bg(d)

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
        lines = self._wrap_text(
            response, (max_width - d.scale_x(40)) // (font_size // 2)
        )
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
                self._draw_gradient_bg(d)

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
            self._draw_gradient_bg(d)

            padding = d.scale_x(25)
            bubble_w = d.width - padding * 2
            bubble_y = d.scale_y(70)
            font_size = d.scale_font(18)
            lines = self._wrap_text(
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

    # -------------------------------------------------------------------------
    # Clock Loop
    # -------------------------------------------------------------------------

    async def _clock_loop(self) -> None:
        try:
            last_frame = time.perf_counter()
            while not self._stop_requested and not self._screensaver_active:
                if self._mode not in (DisplayMode.CLOCK, DisplayMode.SMART):
                    print(
                        f"[_clock_loop] Mode changed to {self._mode.name}, exiting",
                        flush=True,
                    )
                    logger.info(
                        f"Clock loop exiting: mode changed to {self._mode.name}"
                    )
                    break

                self._frame += 1
                now_time = time.perf_counter()
                dt = min(0.05, now_time - last_frame)
                last_frame = now_time

                if self._stop_requested or self._screensaver_active:
                    break

                async with self._render_lock:
                    d = self._display
                    if not d:
                        logger.warning("Clock loop: display is None")
                        break
                    if self._stop_requested or self._screensaver_active:
                        break

                    if (
                        self._waveform_active or self._waveform_explicitly_started
                    ) and self._mode == DisplayMode.SMART:
                        d.clear_sync(Color(10, 12, 18))
                        self._render_waveform_inline(d, dt)
                        self._draw_host_ip_overlay(d)
                        d.show_sync()
                        await asyncio.sleep(0.016)
                        continue

                    d.clear_sync(Color(12, 14, 18))

                    now = datetime.now()
                    # Split hour and minute for separate rendering (avoid colon issues)
                    hour_str = now.strftime("%I").lstrip("0")
                    minute_str = now.strftime("%M")
                    ampm = now.strftime("%p")
                    seconds_str = now.strftime("%S")
                    date_str = now.strftime("%A, %B %d")

                    cx, cy = d.get_center()

                    # Large centered time - render hour, colon, minute separately
                    time_size = d.scale_font(100)

                    # Get actual text dimensions for precise positioning
                    hour_w, hour_h = d.get_text_size(hour_str, time_size)
                    minute_w, minute_h = d.get_text_size(minute_str, time_size)
                    colon_w, colon_h = d.get_text_size(":", time_size)

                    # Total width of time display (without AM/PM for centering)
                    total_time_w = hour_w + colon_w + minute_w

                    # Position time in upper portion of screen
                    time_y = cy - d.scale_y(80)

                    # Start position for hour (centered horizontally)
                    time_start_x = cx - total_time_w // 2

                    # Draw hour with shadow
                    d.draw_text_sync(
                        hour_str,
                        time_start_x + 2,
                        time_y + 2,
                        Color(0, 0, 0),
                        time_size,
                    )
                    d.draw_text_sync(
                        hour_str, time_start_x, time_y, Color(255, 255, 255), time_size
                    )

                    # Draw colon with shadow
                    colon_x = time_start_x + hour_w
                    d.draw_text_sync(
                        ":", colon_x + 2, time_y + 2, Color(0, 0, 0), time_size
                    )
                    d.draw_text_sync(
                        ":", colon_x, time_y, Color(255, 255, 255), time_size
                    )

                    # Draw minute with shadow
                    minute_x = colon_x + colon_w
                    d.draw_text_sync(
                        minute_str, minute_x + 2, time_y + 2, Color(0, 0, 0), time_size
                    )
                    d.draw_text_sync(
                        minute_str, minute_x, time_y, Color(255, 255, 255), time_size
                    )

                    # AM/PM badge - positioned to the right of the time
                    ampm_size = d.scale_font(24)
                    ampm_w, ampm_h = d.get_text_size(ampm, ampm_size)
                    padding_x = d.scale_x(12)
                    padding_y = d.scale_y(8)
                    pill_w = int(ampm_w + padding_x * 2)
                    pill_h = int(ampm_h + padding_y * 2)

                    ampm_x = time_start_x + total_time_w + d.scale_x(15)
                    ampm_y = time_y + d.scale_y(5)

                    # Draw rounded pill background for AM/PM
                    d.draw_rounded_rect_sync(
                        ampm_x, ampm_y, pill_w, pill_h, d.scale_x(12), Color(45, 55, 72)
                    )
                    d.draw_text_sync(
                        ampm,
                        ampm_x + padding_x,
                        ampm_y + padding_y,
                        Color(99, 179, 237),
                        ampm_size,
                    )

                    # Seconds below AM/PM
                    sec_size = d.scale_font(18)
                    sec_w, sec_h = d.get_text_size(f":{seconds_str}", sec_size)
                    sec_x = ampm_x + (pill_w - sec_w) // 2
                    sec_y = ampm_y + pill_h + d.scale_y(6)
                    d.draw_text_sync(
                        f":{seconds_str}",
                        sec_x,
                        sec_y,
                        Color(113, 128, 150),
                        sec_size,
                    )

                    # Date below time - positioned safely within screen
                    date_size = d.scale_font(24)
                    date_w, date_h = d.get_text_size(date_str, date_size)
                    date_x = cx - date_w // 2
                    # Position date with fixed offset from time, ensuring it stays on screen
                    date_y = time_y + max(hour_h, minute_h) + d.scale_y(20)
                    # Clamp to ensure date doesn't go off screen (leave 20px margin)
                    max_date_y = d.height - date_h - d.scale_y(20)
                    date_y = min(date_y, max_date_y)
                    d.draw_text_sync(
                        date_str,
                        date_x,
                        date_y,
                        Color(160, 174, 192),
                        date_size,
                    )

                    self._draw_host_ip_overlay(d)

                    d.show_sync()

                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pass

    # -------------------------------------------------------------------------
    # Weather Loop
    # -------------------------------------------------------------------------

    async def _weather_loop(
        self, fetch_forecast: bool = False, location: Optional[str] = None
    ) -> None:
        try:
            last_frame = time.perf_counter()
            rain_drops: List[Dict] = []
            snow_flakes: List[Dict] = []

            random.seed()
            clouds = [
                {
                    "x": float(random.randint(-100, 800)),
                    "y": random.randint(20, 120),
                    "w": random.randint(60, 140),
                    "speed": random.uniform(0.15, 0.35),
                    "opacity": random.uniform(0.4, 0.9),
                    "bob_offset": random.uniform(0, 6.28),
                    "bob_speed": random.uniform(0.008, 0.02),
                }
                for _ in range(6)
            ]

            stars: List[Dict] = [
                {
                    "x": random.randint(0, 800),
                    "y": random.randint(0, 200),
                    "size": random.uniform(1, 3),
                    "twinkle_phase": random.uniform(0, 6.28),
                    "twinkle_speed": random.uniform(0.02, 0.06),
                }
                for _ in range(60)
            ]

            if (
                fetch_forecast
                or not self._weather_data
                or self._weather_data.get("temperature") is None
            ):
                await self._fetch_weather_data(location=location)

            last_weather_fetch = asyncio.get_event_loop().time()
            weather_refresh_interval = 600

            phase = 0.0
            glow_phase = 0.0
            last_frame_time = time.time()
            target_fps = 60
            frame_duration = 1.0 / target_fps

            while not self._stop_requested and not self._screensaver_active:
                if self._mode not in (DisplayMode.WEATHER, DisplayMode.SMART):
                    break
                if (
                    self._mode == DisplayMode.SMART
                    and self._state != AnimationState.TOOL_ANIMATION
                ):
                    break
                if (
                    self._mode == DisplayMode.SMART
                    and self._tool_animation_start > 0
                    and time.time() - self._tool_animation_start
                    > self._tool_animation_timeout
                ):
                    asyncio.create_task(self.resume_idle())
                    break

                current_frame_time = time.time()
                delta_time = current_frame_time - last_frame_time
                last_frame_time = current_frame_time

                self._frame += 1
                phase += delta_time * 0.8
                glow_phase += delta_time * 1.2

                # Periodically refresh weather data
                current_time = asyncio.get_event_loop().time()
                if current_time - last_weather_fetch > weather_refresh_interval:
                    await self._fetch_weather_data()
                    last_weather_fetch = current_time

                if self._stop_requested or self._screensaver_active:
                    break

                now_time = time.perf_counter()
                dt = min(0.05, now_time - last_frame)
                last_frame = now_time

                async with self._render_lock:
                    d = self._display
                    if not d or self._stop_requested:
                        break

                    if not self._weather_data:
                        self._weather_data = {}

                    cond = self._weather_data.get("condition", "clear").lower()
                    temp = self._weather_data.get("temperature")
                    loc = self._weather_data.get("location", "")
                    forecast = self._weather_data.get("forecast", [])
                    high_temp = self._weather_data.get("high")
                    low_temp = self._weather_data.get("low")

                    now = datetime.now()
                    hour = now.hour

                    is_night = hour < 6 or hour >= 20
                    is_dawn = 6 <= hour < 8
                    is_dusk = 18 <= hour < 20
                    is_golden_hour = is_dawn or is_dusk

                    if "clear" in cond or "sun" in cond:
                        if is_night:
                            top_color = Color(8, 12, 35)
                            bottom_color = Color(25, 35, 70)
                            accent_color = Color(100, 120, 200)
                        elif is_golden_hour:
                            top_color = Color(255, 140, 80)
                            bottom_color = Color(255, 200, 140)
                            accent_color = Color(255, 220, 180)
                        else:
                            top_color = Color(45, 130, 220)
                            bottom_color = Color(135, 200, 255)
                            accent_color = Color(255, 255, 255)
                    elif "rain" in cond or "drizzle" in cond:
                        top_color = Color(35, 45, 60)
                        bottom_color = Color(55, 70, 90)
                        accent_color = Color(100, 150, 200)
                    elif "cloud" in cond:
                        if is_night:
                            top_color = Color(25, 30, 50)
                            bottom_color = Color(45, 55, 80)
                            accent_color = Color(140, 160, 200)
                        else:
                            top_color = Color(90, 110, 140)
                            bottom_color = Color(140, 165, 200)
                            accent_color = Color(200, 215, 240)
                    elif "snow" in cond:
                        top_color = Color(180, 195, 220)
                        bottom_color = Color(220, 235, 255)
                        accent_color = Color(255, 255, 255)
                    elif "thunder" in cond:
                        top_color = Color(20, 20, 35)
                        bottom_color = Color(40, 40, 60)
                        accent_color = Color(255, 255, 150)
                    else:
                        top_color = Color(30, 50, 80)
                        bottom_color = Color(60, 90, 130)
                        accent_color = Color(150, 180, 220)

                    self._draw_weather_gradient(d, top_color, bottom_color)

                    if is_night:
                        for star in stars:
                            star["twinkle_phase"] += (
                                star["twinkle_speed"] * delta_time * 60
                            )
                            brightness = max(
                                0.0, 0.5 + 0.5 * math.sin(star["twinkle_phase"])
                            )
                            star_color = Color(
                                min(255, int(180 * brightness)),
                                min(255, int(195 * brightness)),
                                min(255, int(255 * brightness)),
                            )
                            sx = int(star["x"] * d.width / 800)
                            sy = int(star["y"] * d.height / 480)
                            if star["size"] > 2:
                                d.draw_circle_sync(sx, sy, 2, star_color, True)
                            else:
                                d.draw_circle_sync(sx, sy, 1, star_color, True)

                    if "clear" in cond or "sun" in cond:
                        if is_night:
                            moon_x = d.width - d.scale_x(100)
                            moon_y = d.scale_y(80)
                            moon_r = d.scale_x(35)
                            glow_intensity = 0.5 + 0.08 * math.sin(glow_phase)
                            for i in range(4, 0, -1):
                                glow_r = moon_r + i * 8
                                alpha = int(30 * glow_intensity / i)
                                d.draw_circle_sync(
                                    moon_x, moon_y, glow_r, Color(200, 220, 255), True
                                )
                            d.draw_circle_sync(
                                moon_x, moon_y, moon_r, Color(240, 245, 255), True
                            )
                            d.draw_circle_sync(
                                moon_x - 8, moon_y - 5, 6, Color(220, 225, 240), True
                            )
                            d.draw_circle_sync(
                                moon_x + 10, moon_y + 8, 4, Color(225, 230, 245), True
                            )
                        else:
                            self._draw_sun(
                                d, d.width - d.scale_x(100), d.scale_y(90), phase
                            )

                    for cloud in clouds:
                        cloud["x"] += cloud["speed"] * delta_time * 20
                        if cloud["x"] > 800 + cloud["w"]:
                            cloud["x"] = float(-cloud["w"] - random.randint(20, 100))
                            cloud["y"] = random.randint(20, 120)
                            cloud["w"] = random.randint(60, 140)
                            cloud["speed"] = random.uniform(0.15, 0.35)
                            cloud["opacity"] = random.uniform(0.4, 0.9)
                        cloud["bob_offset"] += cloud["bob_speed"] * delta_time * 20
                        bob_y = int(cloud["y"] + math.sin(cloud["bob_offset"]) * 2)
                        scaled_x = int(cloud["x"] * d.width / 800)
                        scaled_y = int(bob_y * d.height / 480)
                        scaled_w = int(cloud["w"] * d.width / 800)
                        self._draw_cloud_fancy(
                            d, scaled_x, scaled_y, scaled_w, cloud["opacity"]
                        )

                    if "rain" in cond or "drizzle" in cond:
                        spawn_rate = max(1, int(3 - delta_time * 60))
                        if len(rain_drops) < 100 and self._frame % spawn_rate == 0:
                            for _ in range(2):
                                rain_drops.append(
                                    {
                                        "x": float(random.randint(0, d.width)),
                                        "y": float(random.randint(-50, -10)),
                                        "speed": random.uniform(18, 28),
                                        "len": random.randint(15, 25),
                                        "wind": random.uniform(2.0, 4.0),
                                        "opacity": random.uniform(0.5, 1.0),
                                    }
                                )
                        new_drops = []
                        for drop in rain_drops:
                            drop["y"] += drop["speed"] * delta_time * 60
                            drop["x"] += drop["wind"] * delta_time * 60
                            if drop["y"] < d.height + 30:
                                rain_color = Color(
                                    int(140 * drop["opacity"]),
                                    int(180 * drop["opacity"]),
                                    int(230 * drop["opacity"]),
                                )
                                d.draw_line_sync(
                                    int(drop["x"]),
                                    int(drop["y"]),
                                    int(drop["x"] + drop["wind"] * 0.5),
                                    int(drop["y"] + drop["len"]),
                                    rain_color,
                                    1,
                                )
                                new_drops.append(drop)
                        rain_drops = new_drops

                    if "snow" in cond:
                        if len(snow_flakes) < 80 and self._frame % 2 == 0:
                            snow_flakes.append(
                                {
                                    "x": float(random.randint(0, d.width)),
                                    "y": float(random.randint(-30, -5)),
                                    "speed": random.uniform(1.5, 4.0),
                                    "wobble": random.uniform(0, 6.28),
                                    "wobble_speed": random.uniform(0.06, 0.12),
                                    "wobble_amount": random.uniform(1.0, 2.5),
                                    "size": random.randint(2, 5),
                                    "opacity": random.uniform(0.7, 1.0),
                                }
                            )
                        new_flakes = []
                        for flake in snow_flakes:
                            flake["y"] += flake["speed"] * delta_time * 60
                            flake["wobble"] += flake["wobble_speed"]
                            flake["x"] += (
                                math.sin(flake["wobble"])
                                * flake["wobble_amount"]
                                * delta_time
                                * 60
                            )
                            if flake["y"] < d.height + 10:
                                snow_brightness = int(255 * flake["opacity"])
                                d.draw_circle_sync(
                                    int(flake["x"]),
                                    int(flake["y"]),
                                    flake["size"],
                                    Color(
                                        snow_brightness,
                                        snow_brightness,
                                        snow_brightness,
                                    ),
                                    filled=True,
                                )
                                new_flakes.append(flake)
                        snow_flakes = new_flakes

                    if "thunder" in cond and random.random() < 0.02:
                        d.draw_rounded_rect_sync(
                            0, 0, d.width, d.height, 0, Color(255, 255, 255)
                        )

                    total_width = d.width
                    total_height = d.height

                    card_w = min(d.scale_x(280), int(total_width * 0.38))
                    card_h = min(d.scale_y(220), int(total_height * 0.55))
                    card_x = d.scale_x(30)
                    card_y = (total_height - card_h) // 2

                    d.draw_rounded_rect_sync(
                        card_x,
                        card_y,
                        card_w,
                        card_h,
                        d.scale_x(24),
                        Color(15, 20, 35),
                    )

                    icon_size = d.scale_x(70)
                    icon_x = card_x + d.scale_x(20)
                    icon_y = card_y + d.scale_y(20)
                    self._draw_weather_icon_fancy(
                        d, cond, icon_x, icon_y, icon_size, phase
                    )

                    if temp is not None:
                        temp_str = f"{temp}°"
                        if temp <= 32:
                            temp_color = Color(100, 180, 255)
                        elif temp <= 50:
                            temp_color = Color(150, 200, 255)
                        elif temp <= 70:
                            temp_color = Color(255, 255, 255)
                        elif temp <= 85:
                            temp_color = Color(255, 200, 100)
                        else:
                            temp_color = Color(255, 120, 80)
                    else:
                        temp_str = "--°"
                        temp_color = Color(180, 190, 210)

                    temp_size = d.scale_font(72)
                    temp_w, temp_h = d.get_text_size(temp_str, temp_size)
                    temp_x = card_x + card_w - temp_w - d.scale_x(15)
                    temp_y = card_y + d.scale_y(15)

                    d.draw_text_sync(
                        temp_str,
                        temp_x + 2,
                        temp_y + 2,
                        Color(0, 0, 0),
                        temp_size,
                    )
                    d.draw_text_sync(temp_str, temp_x, temp_y, temp_color, temp_size)

                    if high_temp is not None and low_temp is not None:
                        hl_y = card_y + d.scale_y(90)
                        hl_size = d.scale_font(18)

                        high_str = f"↑{high_temp}°"
                        d.draw_text_sync(
                            high_str,
                            card_x + card_w - d.scale_x(110),
                            hl_y,
                            Color(255, 150, 130),
                            hl_size,
                        )

                        low_str = f"↓{low_temp}°"
                        d.draw_text_sync(
                            low_str,
                            card_x + card_w - d.scale_x(55),
                            hl_y,
                            Color(130, 180, 255),
                            hl_size,
                        )

                    cond_display = cond.title() if cond else "Unknown"
                    cond_size = d.scale_font(22)
                    cond_w, cond_h = d.get_text_size(cond_display, cond_size)
                    d.draw_text_sync(
                        cond_display[:18],
                        card_x + (card_w - cond_w) // 2,
                        card_y + d.scale_y(120),
                        Color(80, 200, 255),
                        cond_size,
                    )

                    now = datetime.now()
                    date_str = now.strftime("%a, %b %d")
                    time_str = now.strftime("%I:%M %p").lstrip("0")

                    info_size = d.scale_font(13)
                    loc_display = loc[:16] if loc else ""

                    bottom_y = card_y + card_h - d.scale_y(20)

                    if loc_display:
                        loc_w, _ = d.get_text_size(loc_display, info_size)
                        d.draw_text_sync(
                            loc_display,
                            card_x + d.scale_x(12),
                            bottom_y,
                            Color(140, 155, 185),
                            info_size,
                        )

                    time_w, _ = d.get_text_size(time_str, info_size)
                    d.draw_text_sync(
                        time_str,
                        card_x + card_w - time_w - d.scale_x(12),
                        bottom_y,
                        Color(140, 155, 185),
                        info_size,
                    )

                    forecast_x = card_x + card_w + d.scale_x(20)
                    forecast_y = card_y
                    forecast_w = total_width - forecast_x - d.scale_x(25)
                    forecast_h = card_h

                    if forecast_w >= d.scale_x(200):
                        d.draw_rounded_rect_sync(
                            forecast_x,
                            forecast_y,
                            forecast_w,
                            forecast_h,
                            d.scale_x(20),
                            Color(18, 24, 42),
                        )

                        title_size = d.scale_font(15)
                        title_str = "5-Day Forecast"
                        title_w, _ = d.get_text_size(title_str, title_size)
                        d.draw_text_sync(
                            title_str,
                            forecast_x + (forecast_w - title_w) // 2,
                            forecast_y + d.scale_y(8),
                            Color(160, 175, 200),
                            title_size,
                        )

                        days_to_show = min(len(forecast), 5) if forecast else 0

                        if days_to_show > 0:
                            day_width = forecast_w // days_to_show
                            content_start_y = forecast_y + d.scale_y(38)

                            for i, day in enumerate(forecast[:days_to_show]):
                                day_center_x = (
                                    forecast_x + i * day_width + day_width // 2
                                )

                                if i == 0:
                                    highlight_x = (
                                        forecast_x + i * day_width + d.scale_x(4)
                                    )
                                    highlight_w = day_width - d.scale_x(8)
                                    d.draw_rounded_rect_sync(
                                        highlight_x,
                                        content_start_y - d.scale_y(5),
                                        highlight_w,
                                        d.scale_y(125),
                                        d.scale_x(12),
                                        Color(40, 60, 100),
                                    )

                                raw_day = day.get("day", "")
                                if raw_day.lower() == "today":
                                    day_name = datetime.now().strftime("%a").upper()
                                else:
                                    day_name = raw_day[:3].upper()
                                day_name_size = d.scale_font(14)
                                day_w, _ = d.get_text_size(day_name, day_name_size)
                                day_color = (
                                    Color(255, 220, 100)
                                    if i == 0
                                    else Color(180, 195, 220)
                                )
                                d.draw_text_sync(
                                    day_name,
                                    day_center_x - day_w // 2,
                                    content_start_y,
                                    day_color,
                                    day_name_size,
                                )

                                day_cond = day.get("condition", "clear").lower()
                                icon_y = content_start_y + d.scale_y(25)
                                self._draw_weather_icon_mini(
                                    d,
                                    day_cond,
                                    day_center_x,
                                    icon_y,
                                    d.scale_x(28),
                                    phase + i * 0.5,
                                )

                                cond_abbrev = day.get("condition", "")[:6]
                                cond_size = d.scale_font(10)
                                cond_w, _ = d.get_text_size(cond_abbrev, cond_size)
                                d.draw_text_sync(
                                    cond_abbrev,
                                    day_center_x - cond_w // 2,
                                    icon_y + d.scale_y(18),
                                    Color(140, 155, 180),
                                    cond_size,
                                )

                                high = day.get("high")
                                high_str = f"{high}°" if high is not None else "--"
                                high_size = d.scale_font(18)
                                high_w, _ = d.get_text_size(high_str, high_size)

                                if high is not None:
                                    if high <= 32:
                                        high_color = Color(100, 180, 255)
                                    elif high <= 60:
                                        high_color = Color(200, 220, 255)
                                    elif high <= 80:
                                        high_color = Color(255, 255, 255)
                                    else:
                                        high_color = Color(255, 180, 120)
                                else:
                                    high_color = Color(180, 190, 210)

                                d.draw_text_sync(
                                    high_str,
                                    day_center_x - high_w // 2,
                                    content_start_y + d.scale_y(78),
                                    high_color,
                                    high_size,
                                )

                                low = day.get("low")
                                low_str = f"{low}°" if low is not None else "--"
                                low_size = d.scale_font(14)
                                low_w, _ = d.get_text_size(low_str, low_size)
                                d.draw_text_sync(
                                    low_str,
                                    day_center_x - low_w // 2,
                                    content_start_y + d.scale_y(100),
                                    Color(120, 140, 170),
                                    low_size,
                                )

                                if i < days_to_show - 1:
                                    sep_x = forecast_x + (i + 1) * day_width
                                    d.draw_line_sync(
                                        sep_x,
                                        content_start_y + d.scale_y(10),
                                        sep_x,
                                        forecast_y + forecast_h - d.scale_y(20),
                                        Color(50, 60, 85),
                                        1,
                                    )
                        else:
                            no_data_size = d.scale_font(16)
                            no_data_str = "Loading forecast..."
                            no_data_w, _ = d.get_text_size(no_data_str, no_data_size)
                            d.draw_text_sync(
                                no_data_str,
                                forecast_x + (forecast_w - no_data_w) // 2,
                                forecast_y + forecast_h // 2,
                                Color(140, 150, 175),
                                no_data_size,
                            )

                    self._draw_host_ip_overlay(d)

                    d.show_sync()

                elapsed = time.time() - current_frame_time
                sleep_time = max(0.001, frame_duration - elapsed)
                await asyncio.sleep(sleep_time)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Weather loop error: {e}", exc_info=True)

    def _draw_weather_gradient(
        self, d, top_color: Color, bottom_color: Color, steps: int = 32
    ) -> None:
        step_h = d.height // steps
        for i in range(steps):
            t = i / (steps - 1)
            r = int(top_color.r + (bottom_color.r - top_color.r) * t)
            g = int(top_color.g + (bottom_color.g - top_color.g) * t)
            b = int(top_color.b + (bottom_color.b - top_color.b) * t)
            y = i * step_h
            # Last step extends to full height to avoid gaps
            h = step_h + 1 if i < steps - 1 else d.height - y
            d.fill_rect_sync(0, y, d.width, h, Color(r, g, b))

    def _draw_stars(self, d, phase: float) -> None:
        random.seed(42)
        for _ in range(30):
            x = random.randint(0, d.width)
            y = random.randint(0, d.height // 2)
            twinkle = 0.5 + 0.5 * math.sin(phase * 2 + x * 0.1)
            brightness = int(100 + 155 * twinkle)
            size = 1 if random.random() > 0.3 else 2
            d.fill_rect_sync(
                x, y, size, size, Color(brightness, brightness, brightness)
            )
        random.seed()

    def _draw_weather_icon(
        self, d, condition: str, x: int, y: int, size: int, phase: float
    ) -> None:
        cond = condition.lower()
        if "clear" in cond or "sun" in cond:
            pulse = 1.0 + math.sin(phase * 2) * 0.1
            r = int(size * 0.4 * pulse)
            d.draw_circle_sync(
                x + size // 2, y + size // 2, r, Color(255, 200, 50), True
            )
            for i in range(8):
                angle = (i / 8) * math.pi * 2 + phase * 0.5
                cx, cy = x + size // 2, y + size // 2
                start_r = r + 4
                end_r = r + 10
                x1 = int(cx + math.cos(angle) * start_r)
                y1 = int(cy + math.sin(angle) * start_r)
                x2 = int(cx + math.cos(angle) * end_r)
                y2 = int(cy + math.sin(angle) * end_r)
                d.draw_line_sync(x1, y1, x2, y2, Color(255, 200, 50), 2)
        elif "cloud" in cond:
            self._draw_cloud(d, x, y + size // 4, size)
        elif "rain" in cond or "drizzle" in cond:
            self._draw_cloud(d, x, y + size // 6, int(size * 0.8))
            for i in range(3):
                drop_x = x + size // 4 + i * (size // 4)
                drop_y = y + size // 2 + int(math.sin(phase * 3 + i) * 5)
                d.draw_line_sync(
                    drop_x, drop_y, drop_x, drop_y + size // 5, Color(100, 160, 220), 2
                )
        elif "snow" in cond:
            self._draw_cloud(d, x, y + size // 6, int(size * 0.8))
            for i in range(3):
                flake_x = x + size // 4 + i * (size // 4)
                flake_y = y + size // 2 + int(math.sin(phase * 2 + i) * 4)
                d.draw_circle_sync(flake_x, flake_y, 3, Color(220, 230, 255), True)
        elif "thunder" in cond:
            self._draw_cloud(d, x, y + size // 6, int(size * 0.8))
            bolt_x = x + size // 2
            bolt_y = y + size // 2
            if int(phase * 10) % 20 < 3:
                d.draw_line_sync(
                    bolt_x, bolt_y, bolt_x - 5, bolt_y + 10, Color(255, 255, 100), 2
                )
                d.draw_line_sync(
                    bolt_x - 5,
                    bolt_y + 10,
                    bolt_x + 3,
                    bolt_y + 12,
                    Color(255, 255, 100),
                    2,
                )
                d.draw_line_sync(
                    bolt_x + 3,
                    bolt_y + 12,
                    bolt_x - 2,
                    bolt_y + 22,
                    Color(255, 255, 100),
                    2,
                )
        else:
            self._draw_cloud(d, x, y + size // 4, size)

    def _draw_weather_icon_small(
        self, d, condition: str, x: int, y: int, size: int
    ) -> None:
        cond = condition.lower()
        if "clear" in cond or "sun" in cond:
            d.draw_circle_sync(x, y, size // 3, Color(255, 200, 50), True)
        elif "cloud" in cond:
            r = size // 4
            d.draw_circle_sync(x - r // 2, y, r, Color(200, 210, 225), True)
            d.draw_circle_sync(x + r // 2, y - r // 3, r, Color(200, 210, 225), True)
            d.draw_circle_sync(x + r, y, r, Color(200, 210, 225), True)
        elif "rain" in cond or "drizzle" in cond:
            r = size // 5
            d.draw_circle_sync(x, y - r, r, Color(180, 190, 210), True)
            d.draw_circle_sync(x + r, y - r, r, Color(180, 190, 210), True)
            d.draw_line_sync(x - r, y + 2, x - r, y + 6, Color(100, 160, 220), 1)
            d.draw_line_sync(x + r, y + 2, x + r, y + 6, Color(100, 160, 220), 1)
        elif "snow" in cond:
            r = size // 5
            d.draw_circle_sync(x, y - r, r, Color(200, 210, 225), True)
            d.draw_circle_sync(x + r, y - r, r, Color(200, 210, 225), True)
            d.draw_circle_sync(x - r // 2, y + 4, 2, Color(220, 230, 255), True)
            d.draw_circle_sync(x + r // 2, y + 4, 2, Color(220, 230, 255), True)
        elif "thunder" in cond:
            r = size // 5
            d.draw_circle_sync(x, y - r, r, Color(100, 105, 120), True)
            d.draw_line_sync(x, y + 2, x - 3, y + 8, Color(255, 255, 100), 1)
        else:
            d.draw_circle_sync(x, y, size // 4, Color(180, 190, 210), True)

    def _draw_cloud(self, d, x: int, y: int, w: int) -> None:
        color = Color(235, 240, 248)
        shadow = Color(200, 210, 220)
        h = w // 2
        d.draw_circle_sync(x + w // 4, y + 4, w // 4, shadow, filled=True)
        d.draw_circle_sync(x + w // 2, y - h // 3 + 4, w // 3, shadow, filled=True)
        d.draw_circle_sync(x + w * 3 // 4, y + 4, w // 4, shadow, filled=True)
        d.draw_circle_sync(x + w // 4, y, w // 4, color, filled=True)
        d.draw_circle_sync(x + w // 2, y - h // 3, w // 3, color, filled=True)
        d.draw_circle_sync(x + w * 3 // 4, y, w // 4, color, filled=True)
        d.fill_rect_sync(x + w // 4, y, w // 2, h // 2, color)

    def _draw_sun(self, d, x: int, y: int, phase: float) -> None:
        radius = d.scale_x(38)
        pulse = 1.0 + math.sin(phase * 0.5) * 0.01

        # Draw rays first (behind sun body)
        for i in range(12):
            angle = (i / 12) * math.pi * 2 + phase * 0.05
            ray_len = d.scale_x(22) + math.sin(phase * 0.4 + i * 0.5) * d.scale_x(2)
            start_r = radius + d.scale_x(10)
            end_r = start_r + ray_len
            x1 = x + int(math.cos(angle) * start_r)
            y1 = y + int(math.sin(angle) * start_r)
            x2 = x + int(math.cos(angle) * end_r)
            y2 = y + int(math.sin(angle) * end_r)
            d.draw_line_sync(x1, y1, x2, y2, Color(255, 205, 65), 3)

        # Draw sun body (solid colors, no alpha glow)
        d.draw_circle_sync(x, y, int(radius * pulse), Color(255, 195, 55), filled=True)
        d.draw_circle_sync(
            x, y, int(radius * pulse * 0.78), Color(255, 225, 95), filled=True
        )

    def _draw_cloud_fancy(
        self, d, x: int, y: int, w: int, opacity: float = 1.0
    ) -> None:
        base_r, base_g, base_b = 225, 235, 250
        shadow_r, shadow_g, shadow_b = 175, 190, 210

        color = Color(
            int(base_r * opacity),
            int(base_g * opacity),
            int(base_b * opacity),
        )
        shadow = Color(
            int(shadow_r * opacity * 0.7),
            int(shadow_g * opacity * 0.7),
            int(shadow_b * opacity * 0.7),
        )
        highlight = Color(
            int(255 * opacity),
            int(255 * opacity),
            int(255 * opacity),
        )

        h = w // 2
        r1 = max(4, w // 4)
        r2 = max(5, w // 3)
        r3 = max(3, w // 5)

        d.draw_circle_sync(x + w // 4 + 2, y + 3, r1, shadow, filled=True)
        d.draw_circle_sync(x + w // 2 + 2, y - h // 4 + 3, r2, shadow, filled=True)
        d.draw_circle_sync(x + w * 3 // 4 + 2, y + 3, r3, shadow, filled=True)

        d.draw_circle_sync(x + w // 5, y, r1, color, filled=True)
        d.draw_circle_sync(x + w // 2, y - h // 4, r2, color, filled=True)
        d.draw_circle_sync(x + w * 4 // 5, y, r1, color, filled=True)
        d.draw_circle_sync(x + w // 3, y + h // 8, r3, color, filled=True)
        d.draw_circle_sync(x + w * 2 // 3, y + h // 8, r3, color, filled=True)

        highlight_r = max(2, w // 8)
        d.draw_circle_sync(
            x + w // 2 - 3, y - h // 4 - 3, highlight_r, highlight, filled=True
        )

    def _draw_weather_icon_fancy(
        self, d, condition: str, x: int, y: int, size: int, phase: float
    ) -> None:
        cond = condition.lower()
        cx = x + size // 2
        cy = y + size // 2

        if "clear" in cond or "sun" in cond:
            pulse = 1.0 + math.sin(phase * 0.8) * 0.02

            # Draw sun rays first (behind the sun)
            sun_r = int(size * 0.3 * pulse)
            for i in range(8):
                angle = (i / 8) * math.pi * 2 + phase * 0.15
                ray_pulse = 1.0 + math.sin(phase * 1.0 + i * 0.8) * 0.08
                start_r = sun_r + 3
                end_r = sun_r + int(10 * ray_pulse)
                x1 = int(cx + math.cos(angle) * start_r)
                y1 = int(cy + math.sin(angle) * start_r)
                x2 = int(cx + math.cos(angle) * end_r)
                y2 = int(cy + math.sin(angle) * end_r)
                d.draw_line_sync(x1, y1, x2, y2, Color(255, 210, 80), 2)

            # Draw sun body (no glow circles - they appear as black without alpha support)
            d.draw_circle_sync(cx, cy, sun_r, Color(255, 200, 60), True)
            d.draw_circle_sync(cx, cy, int(sun_r * 0.7), Color(255, 230, 110), True)

        elif "fog" in cond or "mist" in cond or "haze" in cond:
            for i in range(8):
                px = x + size // 2 + int(math.sin(phase * 0.7 + i * 1.3) * (size * 0.4))
                py = y + size // 4 + (i % 4) * (size // 5)
                drift_x = int(math.sin(phase * 0.5 + i * 0.8) * 8)
                drift_y = int(math.cos(phase * 0.4 + i * 0.6) * 3)
                brightness = 0.7 + 0.25 * math.sin(phase * 0.6 + i * 0.9)
                particle_r = max(3, int((size // 8) * (0.6 + 0.4 * math.sin(i * 0.7))))
                fog_color = Color(
                    min(255, int(200 + 50 * brightness)),
                    min(255, int(210 + 40 * brightness)),
                    min(255, int(220 + 30 * brightness)),
                )
                d.draw_circle_sync(
                    px + drift_x, py + drift_y, particle_r, fog_color, True
                )

            for i in range(3):
                wisp_y = y + size // 3 + i * (size // 5)
                wave_offset = math.sin(phase * 0.9 + i * 1.1) * 10
                brightness = 0.7 + 0.2 * math.sin(phase * 0.7 + i * 0.5)
                wisp_color = Color(
                    min(255, int(180 + 70 * brightness)),
                    min(255, int(190 + 60 * brightness)),
                    min(255, int(200 + 50 * brightness)),
                )
                wisp_width = int(size * 0.7) - (i * 8)
                wisp_x = x + (size - wisp_width) // 2 + int(wave_offset)
                d.draw_line_sync(
                    wisp_x, wisp_y, wisp_x + wisp_width, wisp_y, wisp_color, 2
                )

        elif "cloud" in cond:
            cloud_w = int(size * 0.85)
            cloud_y = y + size // 4
            bob = int(math.sin(phase * 1.5) * 3)
            self._draw_cloud_fancy(d, x, cloud_y + bob, cloud_w, 1.0)

        elif "rain" in cond or "drizzle" in cond:
            cloud_w = int(size * 0.75)
            cloud_y = y + size // 8
            self._draw_cloud_fancy(d, x + size // 10, cloud_y, cloud_w, 0.8)

            for i in range(6):
                drop_phase = (phase * 5 + i * 0.9) % 1.0
                drop_x = x + size // 6 + i * (size // 7) + int(math.sin(i * 1.2) * 3)
                drop_y = y + size // 2 - 5 + int(drop_phase * (size // 2))
                drop_len = 8 + int(drop_phase * 6)
                drop_alpha = 0.4 + 0.5 * (1.0 - drop_phase)
                drop_color = Color(
                    int(100 * drop_alpha),
                    int(170 * drop_alpha),
                    min(255, int(240 * drop_alpha)),
                )
                d.draw_line_sync(
                    drop_x, drop_y, drop_x + 2, drop_y + drop_len, drop_color, 2
                )
                if drop_phase > 0.85:
                    splash_y = y + size - 5
                    splash_alpha = (drop_phase - 0.85) * 6
                    splash_color = Color(
                        int(120 * splash_alpha),
                        int(180 * splash_alpha),
                        min(255, int(230 * splash_alpha)),
                    )
                    d.draw_circle_sync(drop_x + 1, splash_y, 2, splash_color, True)

        elif "snow" in cond:
            cloud_w = int(size * 0.75)
            cloud_y = y + size // 8
            self._draw_cloud_fancy(d, x + size // 10, cloud_y, cloud_w, 0.85)

            for i in range(6):
                flake_phase = (phase * 1.5 + i * 1.1) % 1.0
                wobble_x = math.sin(phase * 2 + i * 1.5) * 6
                wobble_y = math.cos(phase * 1.8 + i * 0.9) * 2
                flake_x = x + size // 6 + i * (size // 7) + int(wobble_x)
                flake_y = (
                    y + size // 2 - 8 + int(flake_phase * (size // 2)) + int(wobble_y)
                )
                flake_size = max(2, 3 + int(math.sin(i * 0.8) * 2))
                flake_alpha = 0.5 + 0.4 * math.sin(phase * 3 + i)
                flake_color = Color(
                    min(255, int(240 * flake_alpha)),
                    min(255, int(245 * flake_alpha)),
                    min(255, int(255 * flake_alpha)),
                )
                d.draw_circle_sync(flake_x, flake_y, flake_size, flake_color, True)
                if flake_size > 2:
                    d.draw_circle_sync(
                        flake_x, flake_y, flake_size - 1, Color(255, 255, 255), True
                    )

        elif "thunder" in cond or "storm" in cond:
            cloud_w = int(size * 0.8)
            cloud_y = y + size // 8
            cloud_color_base = 70 + int(20 * math.sin(phase * 8))
            r1 = max(4, cloud_w // 4)
            r2 = max(5, cloud_w // 3)
            d.draw_circle_sync(
                x + cloud_w // 4,
                cloud_y,
                r1,
                Color(cloud_color_base, cloud_color_base + 5, cloud_color_base + 20),
                True,
            )
            d.draw_circle_sync(
                x + cloud_w // 2,
                cloud_y - cloud_w // 8,
                r2,
                Color(
                    cloud_color_base + 10, cloud_color_base + 15, cloud_color_base + 30
                ),
                True,
            )
            d.draw_circle_sync(
                x + cloud_w * 3 // 4,
                cloud_y,
                r1,
                Color(
                    cloud_color_base + 5, cloud_color_base + 10, cloud_color_base + 25
                ),
                True,
            )

            flash_on = int(phase * 12) % 7 < 2
            if flash_on:
                bolt_x = x + size // 2
                bolt_y = y + size // 2 - 5
                glow_color = Color(255, 255, 200)
                d.draw_circle_sync(bolt_x - 2, bolt_y + 8, 8, Color(80, 80, 50), True)
                d.draw_line_sync(bolt_x, bolt_y, bolt_x - 6, bolt_y + 12, glow_color, 3)
                d.draw_line_sync(
                    bolt_x - 6, bolt_y + 12, bolt_x + 2, bolt_y + 14, glow_color, 3
                )
                d.draw_line_sync(
                    bolt_x + 2, bolt_y + 14, bolt_x - 4, bolt_y + 26, glow_color, 3
                )
                d.draw_line_sync(
                    bolt_x - 1, bolt_y, bolt_x - 7, bolt_y + 12, Color(255, 255, 255), 2
                )
                d.draw_line_sync(
                    bolt_x - 7,
                    bolt_y + 12,
                    bolt_x + 1,
                    bolt_y + 14,
                    Color(255, 255, 255),
                    2,
                )
                d.draw_line_sync(
                    bolt_x + 1,
                    bolt_y + 14,
                    bolt_x - 5,
                    bolt_y + 26,
                    Color(255, 255, 255),
                    2,
                )
        else:
            cloud_w = int(size * 0.8)
            cloud_y = y + size // 4
            bob = int(math.sin(phase * 1.2) * 2)
            self._draw_cloud_fancy(d, x, cloud_y + bob, cloud_w, 0.9)

    def _draw_weather_icon_mini(
        self, d, condition: str, x: int, y: int, size: int, phase: float
    ) -> None:
        cond = condition.lower()

        if "clear" in cond or "sun" in cond:
            pulse = 1.0 + math.sin(phase * 3) * 0.08
            r = max(4, int(size * 0.32 * pulse))
            d.draw_circle_sync(x, y, r + 2, Color(255, 220, 100), True)
            d.draw_circle_sync(x, y, r, Color(255, 200, 60), True)
            for i in range(6):
                angle = (i / 6) * math.pi * 2 + phase * 0.5
                x1 = int(x + math.cos(angle) * (r + 2))
                y1 = int(y + math.sin(angle) * (r + 2))
                x2 = int(x + math.cos(angle) * (r + 5))
                y2 = int(y + math.sin(angle) * (r + 5))
                d.draw_line_sync(x1, y1, x2, y2, Color(255, 210, 80), 1)

        elif "fog" in cond or "mist" in cond or "haze" in cond:
            for i in range(5):
                px = x + int(math.sin(phase * 0.8 + i * 1.5) * (size * 0.3))
                py = y - size // 8 + (i % 3) * (size // 6)
                drift_x = int(math.sin(phase * 0.6 + i * 0.7) * 4)
                drift_y = int(math.cos(phase * 0.5 + i * 0.5) * 2)
                brightness = 0.7 + 0.25 * math.sin(phase * 0.7 + i * 0.8)
                particle_r = max(2, int((size // 10) * (0.5 + 0.5 * math.sin(i * 0.9))))
                fog_color = Color(
                    min(255, int(200 + 55 * brightness)),
                    min(255, int(210 + 45 * brightness)),
                    min(255, int(220 + 35 * brightness)),
                )
                d.draw_circle_sync(
                    px + drift_x, py + drift_y, particle_r, fog_color, True
                )

            for i in range(3):
                wisp_y = y - size // 6 + i * (size // 5)
                wave_offset = math.sin(phase * 1.0 + i * 0.8) * 3
                fade = 1.0 - (i * 0.1)
                brightness = (0.7 + 0.2 * math.sin(phase * 0.8 + i * 0.4)) * fade
                wisp_color = Color(
                    min(255, int(180 + 70 * brightness)),
                    min(255, int(190 + 60 * brightness)),
                    min(255, int(200 + 50 * brightness)),
                )
                wisp_width = size // 3 - (i * 2)
                d.draw_line_sync(
                    x - wisp_width // 2 + int(wave_offset),
                    wisp_y,
                    x + wisp_width // 2 + int(wave_offset),
                    wisp_y,
                    wisp_color,
                    1,
                )

        elif "cloud" in cond:
            r = max(3, size // 5)
            bob = int(math.sin(phase * 1.5) * 1)
            d.draw_circle_sync(x - r + 1, y + bob + 1, r, Color(180, 190, 205), True)
            d.draw_circle_sync(
                x + 1, y - r // 2 + bob + 1, int(r * 1.1), Color(190, 200, 215), True
            )
            d.draw_circle_sync(x + r + 1, y + bob + 1, r, Color(180, 190, 205), True)
            d.draw_circle_sync(x - r, y + bob, r, Color(220, 230, 245), True)
            d.draw_circle_sync(
                x, y - r // 2 + bob, int(r * 1.1), Color(235, 242, 255), True
            )
            d.draw_circle_sync(x + r, y + bob, r, Color(220, 230, 245), True)

        elif "rain" in cond or "drizzle" in cond:
            r = max(3, size // 6)
            d.draw_circle_sync(x - r, y - r, r, Color(175, 190, 210), True)
            d.draw_circle_sync(
                x + r // 2, y - r, int(r * 1.1), Color(185, 200, 220), True
            )
            for i in range(3):
                drop_phase = (phase * 4 + i * 0.8) % 1.0
                drop_x = x - r + i * r
                drop_y = y - 2 + int(drop_phase * 10)
                drop_alpha = 0.5 + 0.4 * (1.0 - drop_phase)
                drop_color = Color(
                    int(100 * drop_alpha),
                    int(170 * drop_alpha),
                    min(255, int(235 * drop_alpha)),
                )
                d.draw_line_sync(drop_x, drop_y, drop_x, drop_y + 4, drop_color, 1)

        elif "snow" in cond:
            r = max(3, size // 6)
            d.draw_circle_sync(x - r, y - r, r, Color(200, 215, 235), True)
            d.draw_circle_sync(
                x + r // 2, y - r, int(r * 1.1), Color(215, 228, 248), True
            )
            for i in range(3):
                flake_phase = (phase * 2 + i * 0.9) % 1.0
                wobble = math.sin(phase * 2.5 + i * 1.2) * 3
                flake_x = x - r + i * r + int(wobble)
                flake_y = y - 2 + int(flake_phase * 9)
                flake_alpha = 0.6 + 0.35 * math.sin(phase * 3 + i)
                flake_color = Color(
                    min(255, int(245 * flake_alpha)),
                    min(255, int(250 * flake_alpha)),
                    min(255, int(255 * flake_alpha)),
                )
                d.draw_circle_sync(flake_x, flake_y, 2, flake_color, True)

        elif "thunder" in cond or "storm" in cond:
            r = max(3, size // 6)
            flash = int(phase * 10) % 6 < 2
            cloud_bright = 100 if flash else 85
            d.draw_circle_sync(
                x - r,
                y - r,
                r,
                Color(cloud_bright - 15, cloud_bright - 10, cloud_bright + 10),
                True,
            )
            d.draw_circle_sync(
                x + r // 2,
                y - r,
                int(r * 1.1),
                Color(cloud_bright - 5, cloud_bright, cloud_bright + 20),
                True,
            )
            if flash:
                d.draw_line_sync(x, y, x - 2, y + 5, Color(255, 255, 180), 1)
                d.draw_line_sync(x - 2, y + 5, x + 1, y + 6, Color(255, 255, 180), 1)
                d.draw_line_sync(x + 1, y + 6, x - 1, y + 10, Color(255, 255, 180), 1)
        else:
            r = max(3, size // 5)
            bob = int(math.sin(phase * 1.2) * 1)
            d.draw_circle_sync(x, y + bob, r, Color(190, 205, 225), True)

    async def _gallery_loop(self) -> None:
        try:
            last_change = time.time()
            last_frame = time.perf_counter()
            while not self._stop_requested and not self._screensaver_active:
                if self._mode != DisplayMode.GALLERY:
                    break

                now_time = time.perf_counter()
                dt = min(0.05, now_time - last_frame)
                last_frame = now_time

                async with self._render_lock:
                    d = self._display
                    if not d or self._stop_requested or self._screensaver_active:
                        break

                    if not self._gallery_images:
                        self._draw_gradient_bg(d)
                        cx, cy = d.get_center()
                        d.draw_text_sync(
                            "No images",
                            cx - d.scale_x(55),
                            cy,
                            Palette.TEXT_MUTED,
                            d.scale_font(24),
                        )
                        self._draw_host_ip_overlay(d)
                        d.show_sync()
                    else:
                        img_path = self._gallery_images[self._gallery_index]
                        try:
                            d.clear_sync(Color(0, 0, 0))
                            await d.draw_image(img_path, 0, 0, d.width, d.height)
                            self._draw_host_ip_overlay(d)
                            d.show_sync()
                        except Exception as e:
                            logger.debug(f"Failed to display image: {e}")
                            self._draw_gradient_bg(d)
                            self._draw_host_ip_overlay(d)
                            d.show_sync()

                # Check if time to advance
                if time.time() - last_change >= self._gallery_interval:
                    if self._gallery_images:
                        self._gallery_index = (self._gallery_index + 1) % len(
                            self._gallery_images
                        )
                    last_change = time.time()

                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pass

    async def _waveform_loop(self) -> None:
        """Dedicated waveform loop for DisplayMode.WAVEFORM."""
        try:
            last_frame = time.perf_counter()

            while not self._stop_requested and not self._screensaver_active:
                if self._mode != DisplayMode.WAVEFORM:
                    break

                now = time.perf_counter()
                dt = min(0.05, now - last_frame)
                last_frame = now

                async with self._render_lock:
                    d = self._display
                    if not d or self._stop_requested or self._screensaver_active:
                        break

                    d.clear_sync(Color(10, 12, 18))
                    self._render_waveform_inline(d, dt)
                    self._draw_host_ip_overlay(d)
                    d.show_sync()

                await asyncio.sleep(0.016)
        except asyncio.CancelledError:
            pass

    def _init_starfield(self, num_stars: int = 200) -> None:
        self._stars = []
        if not self._display:
            return
        for _ in range(num_stars):
            self._stars.append(
                {
                    "x": random.uniform(0, self._display.width),
                    "y": random.uniform(0, self._display.height),
                    "z": random.uniform(0.1, 1.0),
                    "speed": random.uniform(0.3, 0.8),
                    "brightness_phase": random.uniform(0, 6.28),
                }
            )

    def _init_matrix(self, num_columns: int = 40) -> None:
        self._matrix_chars = "アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲンABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@#$%&*+=<>?|{}[]~"
        self._matrix_drops = []
        if not self._display:
            return

        col_width = max(10, self._display.width // num_columns)
        num_columns = self._display.width // col_width

        for i in range(num_columns):
            trail_len = random.randint(12, 30)
            self._matrix_drops.append(
                {
                    "x": i * col_width + col_width // 2,
                    "y": random.uniform(-500, 0),
                    "speed": random.uniform(2.0, 5.5),
                    "trail_len": trail_len,
                    "chars": [
                        random.choice(self._matrix_chars) for _ in range(trail_len)
                    ],
                    "change_timers": [
                        random.uniform(0, 0.25) for _ in range(trail_len)
                    ],
                    "glow_intensity": random.uniform(0.8, 1.2),
                }
            )

    def _init_bounce(self) -> None:
        if not self._display:
            return
        self._bounce_pos = [
            float(self._display.width // 4),
            float(self._display.height // 4),
        ]
        self._bounce_vel = [1.2, 0.9]

    def _hsv_to_rgb(self, h: float, s: float, v: float) -> Color:
        import colorsys

        r, g, b = colorsys.hsv_to_rgb(h, s, v)
        return Color(
            max(0, min(255, int(r * 255))),
            max(0, min(255, int(g * 255))),
            max(0, min(255, int(b * 255))),
        )

    async def _screensaver_loop(self) -> None:
        try:
            self._load_screensaver_settings()
            style = self._screensaver_style.lower()

            if style == "starfield":
                self._init_starfield(350)
            elif style == "matrix":
                self._init_matrix(45)
            elif style == "bounce":
                self._init_bounce()
            elif style == "fade":
                self._fade_hue = 0.0
                self._fade_blobs = []

            last_frame = time.perf_counter()
            target_fps = 60
            frame_time = 1.0 / target_fps

            while not self._stop_requested and self._screensaver_active:
                now = time.perf_counter()
                dt = now - last_frame
                last_frame = now

                if check_and_clear_activity():
                    await self._deactivate_screensaver()
                    break

                if not self._screensaver_active or self._stop_requested:
                    break

                try:
                    await asyncio.wait_for(self._render_lock.acquire(), timeout=0.02)
                except asyncio.TimeoutError:
                    await asyncio.sleep(0.002)
                    continue

                should_break = False
                try:
                    d = self._display
                    if not d or self._stop_requested or not self._screensaver_active:
                        should_break = True
                    else:
                        if style == "starfield":
                            await self._render_starfield(d, dt)
                        elif style == "matrix":
                            await self._render_matrix(d, dt)
                        elif style == "bounce":
                            await self._render_bounce(d, dt)
                        elif style == "fade":
                            await self._render_fade(d, dt)
                        else:
                            await self._render_starfield(d, dt)

                        d.show_sync()
                finally:
                    self._render_lock.release()

                if should_break:
                    break

                elapsed = time.perf_counter() - now
                sleep_time = max(0.001, frame_time - elapsed)
                await asyncio.sleep(sleep_time)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Screensaver loop error: {e}")

    async def _render_starfield(self, d: BaseDisplay, dt: float) -> None:
        d.clear_sync(Color(2, 2, 12))
        cx, cy = d.get_center()
        speed_mult = dt * 60

        for star in self._stars:
            star["z"] -= 0.005 * star["speed"] * speed_mult
            star["brightness_phase"] += dt * 3

            if star["z"] <= 0.01:
                star["x"] = random.uniform(0, d.width)
                star["y"] = random.uniform(0, d.height)
                star["z"] = 1.0
                star["speed"] = random.uniform(0.3, 0.8)

            proj_x = int(cx + (star["x"] - cx) / star["z"])
            proj_y = int(cy + (star["y"] - cy) / star["z"])

            size = max(1, int(4 * (1 - star["z"])))
            twinkle = 0.85 + 0.15 * math.sin(star["brightness_phase"])
            base_brightness = int(255 * (1 - star["z"] * 0.3) * twinkle)

            if 0 <= proj_x < d.width and 0 <= proj_y < d.height:
                r = min(255, int(base_brightness * 0.95))
                g = min(255, int(base_brightness * 0.98))
                b = min(255, int(base_brightness + 40))
                color = Color(r, g, b)

                if size <= 1:
                    d.fill_rect_sync(proj_x, proj_y, 2, 2, color)
                elif size == 2:
                    d.fill_rect_sync(proj_x - 1, proj_y - 1, 3, 3, color)
                else:
                    d.draw_circle_sync(proj_x, proj_y, size, color, True)

    async def _render_matrix(self, d: BaseDisplay, dt: float) -> None:
        d.clear_sync(Color(0, 5, 0))

        font_size = d.scale_font(13)
        char_height = font_size + 2
        speed_mult = dt * 60

        for drop in self._matrix_drops:
            drop["y"] += drop["speed"] * speed_mult

            trail_len = drop["trail_len"]
            total_height = trail_len * char_height

            if drop["y"] > d.height + total_height:
                drop["y"] = random.uniform(-400, -100)
                drop["speed"] = random.uniform(2.0, 5.5)
                drop["trail_len"] = random.randint(12, 30)
                drop["chars"] = [
                    random.choice(self._matrix_chars) for _ in range(drop["trail_len"])
                ]
                drop["change_timers"] = [
                    random.uniform(0, 0.2) for _ in range(drop["trail_len"])
                ]
                drop["glow_intensity"] = random.uniform(0.8, 1.2)

            glow = drop.get("glow_intensity", 1.0)

            for i in range(len(drop["chars"])):
                drop["change_timers"][i] -= dt
                if drop["change_timers"][i] <= 0:
                    drop["chars"][i] = random.choice(self._matrix_chars)
                    drop["change_timers"][i] = (
                        random.uniform(0.02, 0.08)
                        if i < 3
                        else random.uniform(0.06, 0.25)
                    )

            for i, char in enumerate(drop["chars"]):
                char_y = int(drop["y"] - i * char_height)

                if 0 <= char_y < d.height:
                    if i == 0:
                        color = Color(240, 255, 240)
                    elif i == 1:
                        color = Color(200, 255, 200)
                    elif i == 2:
                        color = Color(120, 255, 120)
                    elif i == 3:
                        color = Color(80, 240, 80)
                    else:
                        fade = max(0, int((230 - i * 12) * glow))
                        color = Color(0, fade, int(fade * 0.1))

                    d.draw_text_sync(char, int(drop["x"]), char_y, color, font_size)

    async def _render_bounce(self, d: BaseDisplay, dt: float) -> None:
        d.clear_sync(Color(3, 3, 10))

        speed_mult = dt * 60
        self._bounce_pos[0] += self._bounce_vel[0] * speed_mult
        self._bounce_pos[1] += self._bounce_vel[1] * speed_mult

        logo_text = "GPT Home"
        font_size = d.scale_font(48)
        logo_w, logo_h = d.get_text_size(logo_text, font_size)

        hit_edge = False
        if self._bounce_pos[0] <= 0:
            self._bounce_pos[0] = 0
            self._bounce_vel[0] = abs(self._bounce_vel[0]) * random.uniform(0.95, 1.05)
            hit_edge = True
        elif self._bounce_pos[0] + logo_w >= d.width:
            self._bounce_pos[0] = d.width - logo_w
            self._bounce_vel[0] = -abs(self._bounce_vel[0]) * random.uniform(0.95, 1.05)
            hit_edge = True

        if self._bounce_pos[1] <= 0:
            self._bounce_pos[1] = 0
            self._bounce_vel[1] = abs(self._bounce_vel[1]) * random.uniform(0.95, 1.05)
            hit_edge = True
        elif self._bounce_pos[1] + logo_h >= d.height:
            self._bounce_pos[1] = d.height - logo_h
            self._bounce_vel[1] = -abs(self._bounce_vel[1]) * random.uniform(0.95, 1.05)
            hit_edge = True

        if hit_edge:
            self._fade_hue = (self._fade_hue + 0.08 + random.uniform(0, 0.08)) % 1.0

        color = self._hsv_to_rgb(self._fade_hue, 0.85, 1.0)
        x, y = int(self._bounce_pos[0]), int(self._bounce_pos[1])

        glow_color = self._hsv_to_rgb(self._fade_hue, 0.6, 0.3)
        d.draw_text_sync(logo_text, x + 4, y + 4, glow_color, font_size)

        shadow_color = Color(color.r // 6, color.g // 6, color.b // 6)
        d.draw_text_sync(logo_text, x + 2, y + 2, shadow_color, font_size)

        d.draw_text_sync(logo_text, x, y, color, font_size)

    def _init_fade(self, d: BaseDisplay) -> None:
        width, height = d.width, d.height

        self._fade_clock_pos = [
            random.uniform(width * 0.2, width * 0.6),
            random.uniform(height * 0.2, height * 0.6),
        ]
        self._fade_clock_vel = [
            random.choice([-1, 1]) * random.uniform(0.18, 0.3),
            random.choice([-1, 1]) * random.uniform(0.12, 0.25),
        ]

        self._fade_blobs = []
        for i in range(7):
            self._fade_blobs.append(
                {
                    "x": random.uniform(0, width),
                    "y": random.uniform(0, height),
                    "vx": random.uniform(-0.4, 0.4),
                    "vy": random.uniform(-0.3, 0.3),
                    "radius": random.uniform(width * 0.12, width * 0.28),
                    "hue_offset": i * 0.14,
                    "pulse_phase": random.uniform(0, 6.28),
                }
            )

        self._fade_particles = []
        for _ in range(60):
            self._fade_particles.append(
                {
                    "x": random.uniform(0, width),
                    "y": random.uniform(0, height),
                    "vx": random.uniform(-0.6, 0.6),
                    "vy": random.uniform(-0.4, 0.4),
                    "size": random.uniform(2, 6),
                    "brightness": random.uniform(0.4, 0.9),
                    "phase": random.uniform(0, 6.28),
                    "phase_speed": random.uniform(1.5, 3.0),
                }
            )

    async def _render_fade(self, d: BaseDisplay, dt: float) -> None:
        if not self._fade_blobs:
            self._init_fade(d)

        self._fade_hue = (self._fade_hue + dt * 0.04) % 1.0
        t = time.perf_counter()

        base_hue = self._fade_hue
        for y_band in range(0, d.height, 6):
            band_t = y_band / d.height
            hue = (base_hue + band_t * 0.18) % 1.0
            sat = 0.55 + band_t * 0.25
            val = 0.1 + (1 - band_t) * 0.08
            color = self._hsv_to_rgb(hue, sat, val)
            d.fill_rect_sync(0, y_band, d.width, 7, color)

        for blob in self._fade_blobs:
            blob["x"] += blob["vx"] * dt * 60
            blob["y"] += blob["vy"] * dt * 60
            blob["pulse_phase"] = blob.get("pulse_phase", 0) + dt * 0.8

            if blob["x"] < -blob["radius"] * 0.4:
                blob["vx"] = abs(blob["vx"]) * random.uniform(0.9, 1.1)
            elif blob["x"] > d.width + blob["radius"] * 0.4:
                blob["vx"] = -abs(blob["vx"]) * random.uniform(0.9, 1.1)
            if blob["y"] < -blob["radius"] * 0.4:
                blob["vy"] = abs(blob["vy"]) * random.uniform(0.9, 1.1)
            elif blob["y"] > d.height + blob["radius"] * 0.4:
                blob["vy"] = -abs(blob["vy"]) * random.uniform(0.9, 1.1)

            blob_hue = (self._fade_hue + blob["hue_offset"]) % 1.0
            pulse = 1.0 + math.sin(blob["pulse_phase"]) * 0.2
            radius = int(blob["radius"] * pulse)

            for layer in range(5, 0, -1):
                layer_r = int(radius * (0.35 + layer * 0.13))
                layer_val = 0.04 + (5 - layer) * 0.025
                glow_color = self._hsv_to_rgb(blob_hue, 0.65, layer_val)
                d.draw_circle_sync(
                    int(blob["x"]), int(blob["y"]), layer_r, glow_color, True
                )

        for particle in self._fade_particles:
            particle["x"] += particle["vx"] * dt * 60
            particle["y"] += particle["vy"] * dt * 60
            particle["phase"] += dt * particle.get("phase_speed", 2.0)

            if particle["x"] < 0:
                particle["x"] = d.width
            elif particle["x"] > d.width:
                particle["x"] = 0
            if particle["y"] < 0:
                particle["y"] = d.height
            elif particle["y"] > d.height:
                particle["y"] = 0

            twinkle = 0.4 + 0.6 * math.sin(particle["phase"])
            brightness = particle["brightness"] * twinkle
            p_hue = (self._fade_hue + 0.5) % 1.0
            p_color = self._hsv_to_rgb(p_hue, 0.35, brightness)

            size = int(particle["size"] * (0.7 + twinkle * 0.5))
            if size > 3:
                d.draw_circle_sync(
                    int(particle["x"]), int(particle["y"]), size // 2, p_color, True
                )
            else:
                d.fill_rect_sync(
                    int(particle["x"]) - size // 2,
                    int(particle["y"]) - size // 2,
                    size,
                    size,
                    p_color,
                )

        clock_margin_x = d.scale_x(120)
        clock_margin_y = d.scale_y(60)

        self._fade_clock_pos[0] += self._fade_clock_vel[0] * dt * 60
        self._fade_clock_pos[1] += self._fade_clock_vel[1] * dt * 60

        # Bounce clock off edges with some randomness
        if self._fade_clock_pos[0] < clock_margin_x:
            self._fade_clock_pos[0] = clock_margin_x
            self._fade_clock_vel[0] = abs(self._fade_clock_vel[0]) * random.uniform(
                0.8, 1.2
            )
            self._fade_clock_vel[1] += random.uniform(-0.05, 0.05)
        elif self._fade_clock_pos[0] > d.width - clock_margin_x:
            self._fade_clock_pos[0] = d.width - clock_margin_x
            self._fade_clock_vel[0] = -abs(self._fade_clock_vel[0]) * random.uniform(
                0.8, 1.2
            )
            self._fade_clock_vel[1] += random.uniform(-0.05, 0.05)

        if self._fade_clock_pos[1] < clock_margin_y:
            self._fade_clock_pos[1] = clock_margin_y
            self._fade_clock_vel[1] = abs(self._fade_clock_vel[1]) * random.uniform(
                0.8, 1.2
            )
            self._fade_clock_vel[0] += random.uniform(-0.05, 0.05)
        elif self._fade_clock_pos[1] > d.height - clock_margin_y:
            self._fade_clock_pos[1] = d.height - clock_margin_y
            self._fade_clock_vel[1] = -abs(self._fade_clock_vel[1]) * random.uniform(
                0.8, 1.2
            )
            self._fade_clock_vel[0] += random.uniform(-0.05, 0.05)

        # Clamp velocity
        max_vel = 0.4
        self._fade_clock_vel[0] = max(-max_vel, min(max_vel, self._fade_clock_vel[0]))
        self._fade_clock_vel[1] = max(-max_vel, min(max_vel, self._fade_clock_vel[1]))

        now = datetime.now()
        time_str = now.strftime("%I:%M").lstrip("0")
        time_size = d.scale_font(56)

        clock_x = int(self._fade_clock_pos[0])
        clock_y = int(self._fade_clock_pos[1])

        time_w, time_h = d.get_text_size(time_str, time_size)

        text_hue = (self._fade_hue + 0.5) % 1.0
        glow_pulse = 0.8 + 0.2 * math.sin(t * 2)

        for glow_layer in range(3, 0, -1):
            glow_offset = glow_layer * 2
            glow_val = 0.15 * (4 - glow_layer) * glow_pulse
            glow_color = self._hsv_to_rgb(text_hue, 0.4, glow_val)
            d.draw_text_sync(
                time_str,
                clock_x - time_w // 2 - glow_offset,
                clock_y - time_h // 2,
                glow_color,
                time_size,
            )
            d.draw_text_sync(
                time_str,
                clock_x - time_w // 2 + glow_offset,
                clock_y - time_h // 2,
                glow_color,
                time_size,
            )

        # Draw main time text
        text_color = self._hsv_to_rgb(text_hue, 0.2, 0.95)
        d.draw_text_sync(
            time_str,
            clock_x - time_w // 2,
            clock_y - time_h // 2,
            text_color,
            time_size,
        )

        ampm = now.strftime("%p")
        ampm_size = d.scale_font(18)
        ampm_w, ampm_h = d.get_text_size(ampm, ampm_size)
        ampm_color = self._hsv_to_rgb(text_hue, 0.3, 0.6)
        d.draw_text_sync(
            ampm,
            clock_x - ampm_w // 2,
            clock_y + time_h // 2 + d.scale_y(8),
            ampm_color,
            ampm_size,
        )
