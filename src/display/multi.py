"""Multi-display support with mirroring capabilities.

This module provides a MultiDisplayManager that wraps multiple displays
and can mirror content across all enabled displays simultaneously.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseDisplay, Color, Colors, DisplayInfo, DisplayMode, ScreenType
from .detection import detect_displays
from .factory import DisplayFactory

logger = logging.getLogger(__name__)

SETTINGS_PATH = Path(__file__).parent.parent / "settings.json"


@dataclass
class DisplayConfig:
    """Configuration for a single display."""

    display_id: str
    enabled: bool = True
    info: Optional[DisplayInfo] = None


@dataclass
class MultiDisplayConfig:
    """Configuration for multi-display setup."""

    mirror_enabled: bool = False
    displays: Dict[str, DisplayConfig] = field(default_factory=dict)

    @classmethod
    def load(cls) -> "MultiDisplayConfig":
        """Load configuration from settings.json."""
        config = cls()
        try:
            if SETTINGS_PATH.exists():
                with SETTINGS_PATH.open("r") as f:
                    settings = json.load(f)
                multi_cfg = settings.get("multi_display", {})
                config.mirror_enabled = multi_cfg.get("mirror_enabled", False)
                for display_id, display_cfg in multi_cfg.get("displays", {}).items():
                    config.displays[display_id] = DisplayConfig(
                        display_id=display_id,
                        enabled=display_cfg.get("enabled", True),
                    )
        except Exception as e:
            logger.debug(f"Could not load multi-display config: {e}")
        return config

    def save(self) -> None:
        """Save configuration to settings.json."""
        try:
            settings = {}
            if SETTINGS_PATH.exists():
                with SETTINGS_PATH.open("r") as f:
                    settings = json.load(f)

            settings["multi_display"] = {
                "mirror_enabled": self.mirror_enabled,
                "displays": {
                    display_id: {"enabled": cfg.enabled}
                    for display_id, cfg in self.displays.items()
                },
            }

            with SETTINGS_PATH.open("w") as f:
                json.dump(settings, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save multi-display config: {e}")


def get_display_id(info: DisplayInfo) -> str:
    """Generate unique ID for a display."""
    if info.screen_type == ScreenType.I2C:
        return f"i2c_{info.bus}_{info.address:02x}"
    elif info.device_path:
        return info.device_path.replace("/dev/", "").replace("/", "_")
    return f"{info.screen_type.value}_{info.width}x{info.height}"


class MirroredDisplay(BaseDisplay):
    """A virtual display that mirrors operations to multiple physical displays."""

    supports_modes: bool = True

    def __init__(self, displays: List[BaseDisplay], primary: BaseDisplay):
        """Initialize with list of displays to mirror to.

        Args:
            displays: All displays to mirror content to
            primary: The primary display (used for dimensions)
        """
        self._displays = displays
        self._primary = primary

        # Use primary display's info
        super().__init__(primary.info)
        self.width = primary.width
        self.height = primary.height

    @property
    def primary(self) -> BaseDisplay:
        return self._primary

    @property
    def all_displays(self) -> List[BaseDisplay]:
        return self._displays

    async def initialize(self) -> bool:
        """Initialize all displays."""
        results = await asyncio.gather(
            *[d.initialize() for d in self._displays], return_exceptions=True
        )
        success = all(r is True for r in results if not isinstance(r, Exception))
        if not success:
            for i, r in enumerate(results):
                if isinstance(r, Exception):
                    logger.error(f"Display {i} init failed: {r}")
        return success

    async def clear(self, color: Color = Colors.BLACK) -> None:
        for d in self._displays:
            await d.clear(color)

    def clear_sync(self, color: Color = Colors.BLACK) -> None:
        for d in self._displays:
            d.clear_sync(color)

    async def fill_rect(
        self, x: int, y: int, w: int, h: int, color: Color = Colors.WHITE
    ) -> None:
        for d in self._displays:
            # Scale coordinates for displays with different resolutions
            sx, sy, sw, sh = self._scale_rect(d, x, y, w, h)
            await d.fill_rect(sx, sy, sw, sh, color)

    def fill_rect_sync(
        self, x: int, y: int, w: int, h: int, color: Color = Colors.WHITE
    ) -> None:
        for d in self._displays:
            sx, sy, sw, sh = self._scale_rect(d, x, y, w, h)
            d.fill_rect_sync(sx, sy, sw, sh, color)

    def _scale_rect(
        self, display: BaseDisplay, x: int, y: int, w: int, h: int
    ) -> tuple:
        """Scale rectangle coordinates for a display with different resolution."""
        if display.width == self.width and display.height == self.height:
            return x, y, w, h
        scale_x = display.width / self.width
        scale_y = display.height / self.height
        return (
            int(x * scale_x),
            int(y * scale_y),
            int(w * scale_x),
            int(h * scale_y),
        )

    def _scale_point(self, display: BaseDisplay, x: int, y: int) -> tuple:
        """Scale point coordinates for a display with different resolution."""
        if display.width == self.width and display.height == self.height:
            return x, y
        scale_x = display.width / self.width
        scale_y = display.height / self.height
        return int(x * scale_x), int(y * scale_y)

    def _scale_size(self, display: BaseDisplay, size: int) -> int:
        """Scale a size value for a display with different resolution."""
        if display.width == self.width:
            return size
        scale = min(display.width / self.width, display.height / self.height)
        return max(1, int(size * scale))

    async def draw_text(
        self,
        text: str,
        x: int,
        y: int,
        color: Color = Colors.WHITE,
        font_size: int = 16,
        font_name: Optional[str] = None,
    ) -> None:
        for d in self._displays:
            sx, sy = self._scale_point(d, x, y)
            sf = self._scale_size(d, font_size)
            await d.draw_text(text, sx, sy, color, sf, font_name)

    def draw_text_sync(
        self,
        text: str,
        x: int,
        y: int,
        color: Color = Colors.WHITE,
        font_size: int = 16,
        font_name: Optional[str] = None,
    ) -> None:
        for d in self._displays:
            sx, sy = self._scale_point(d, x, y)
            sf = self._scale_size(d, font_size)
            d.draw_text_sync(text, sx, sy, color, sf, font_name)

    async def draw_line(
        self, x1: int, y1: int, x2: int, y2: int, color: Color, width: int = 1
    ) -> None:
        for d in self._displays:
            sx1, sy1 = self._scale_point(d, x1, y1)
            sx2, sy2 = self._scale_point(d, x2, y2)
            sw = self._scale_size(d, width)
            await d.draw_line(sx1, sy1, sx2, sy2, color, sw)

    def draw_line_sync(
        self, x1: int, y1: int, x2: int, y2: int, color: Color, width: int = 1
    ) -> None:
        for d in self._displays:
            sx1, sy1 = self._scale_point(d, x1, y1)
            sx2, sy2 = self._scale_point(d, x2, y2)
            sw = self._scale_size(d, width)
            d.draw_line_sync(sx1, sy1, sx2, sy2, color, sw)

    async def draw_circle(
        self, cx: int, cy: int, radius: int, color: Color, filled: bool = False
    ) -> None:
        for d in self._displays:
            scx, scy = self._scale_point(d, cx, cy)
            sr = self._scale_size(d, radius)
            await d.draw_circle(scx, scy, sr, color, filled)

    def draw_circle_sync(
        self, cx: int, cy: int, radius: int, color: Color, filled: bool = False
    ) -> None:
        for d in self._displays:
            scx, scy = self._scale_point(d, cx, cy)
            sr = self._scale_size(d, radius)
            d.draw_circle_sync(scx, scy, sr, color, filled)

    def draw_rounded_rect_sync(
        self, x: int, y: int, w: int, h: int, radius: int, color: Color
    ) -> None:
        for d in self._displays:
            sx, sy, sw, sh = self._scale_rect(d, x, y, w, h)
            sr = self._scale_size(d, radius)
            d.draw_rounded_rect_sync(sx, sy, sw, sh, sr, color)

    def draw_arc_sync(
        self,
        cx: int,
        cy: int,
        radius: int,
        start: float,
        end: float,
        color: Color,
        width: int = 3,
    ) -> None:
        for d in self._displays:
            scx, scy = self._scale_point(d, cx, cy)
            sr = self._scale_size(d, radius)
            sw = self._scale_size(d, width)
            d.draw_arc_sync(scx, scy, sr, start, end, color, sw)

    def draw_pil_image_sync(
        self,
        img: Any,
        x: int,
        y: int,
        width: Optional[int] = None,
        height: Optional[int] = None,
    ) -> None:
        for d in self._displays:
            sx, sy = self._scale_point(d, x, y)
            if width and height:
                sw, sh, _, _ = self._scale_rect(d, 0, 0, width, height)
            else:
                sw, sh = None, None
            d.draw_pil_image_sync(img, sx, sy, sw, sh)

    async def draw_image(
        self,
        image_path: str,
        x: int,
        y: int,
        width: Optional[int] = None,
        height: Optional[int] = None,
    ) -> None:
        for d in self._displays:
            sx, sy = self._scale_point(d, x, y)
            if width and height:
                sw, sh, _, _ = self._scale_rect(d, 0, 0, width, height)
            else:
                sw, sh = None, None
            await d.draw_image(image_path, sx, sy, sw, sh)

    def get_text_size(
        self, text: str, font_size: int = 16, font_name: Optional[str] = None
    ) -> tuple:
        return self._primary.get_text_size(text, font_size, font_name)

    def set_clip(self, x: int, y: int, w: int, h: int) -> None:
        for d in self._displays:
            sx, sy, sw, sh = self._scale_rect(d, x, y, w, h)
            d.set_clip(sx, sy, sw, sh)

    def clear_clip(self) -> None:
        for d in self._displays:
            d.clear_clip()

    async def show(self) -> None:
        for d in self._displays:
            await d.show()

    def show_sync(self) -> None:
        for d in self._displays:
            d.show_sync()

    def restore_tty(self) -> None:
        for d in self._displays:
            d.restore_tty()

    async def shutdown(self) -> None:
        await asyncio.gather(
            *[d.shutdown() for d in self._displays], return_exceptions=True
        )


class MultiDisplayManager:
    """Manages multiple displays with mirroring support."""

    _instance: Optional["MultiDisplayManager"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._config = MultiDisplayConfig.load()
        self._displays: Dict[str, BaseDisplay] = {}
        self._display_infos: Dict[str, DisplayInfo] = {}
        self._initialized = True

    @classmethod
    def get_instance(cls) -> "MultiDisplayManager":
        return cls()

    def get_config(self) -> MultiDisplayConfig:
        """Get current configuration."""
        return self._config

    def set_mirror_enabled(self, enabled: bool) -> None:
        """Enable or disable mirroring."""
        self._config.mirror_enabled = enabled
        self._config.save()

    def set_display_enabled(self, display_id: str, enabled: bool) -> None:
        """Enable or disable a specific display."""
        if display_id not in self._config.displays:
            self._config.displays[display_id] = DisplayConfig(display_id=display_id)
        self._config.displays[display_id].enabled = enabled
        self._config.save()

    def is_display_enabled(self, display_id: str) -> bool:
        """Check if a display is enabled."""
        if display_id not in self._config.displays:
            return True  # Enabled by default
        return self._config.displays[display_id].enabled

    async def detect_and_create_displays(self) -> List[BaseDisplay]:
        """Detect all connected displays and create driver instances."""
        detected = detect_displays()
        displays = []

        for info in detected:
            display_id = get_display_id(info)
            self._display_infos[display_id] = info

            # Ensure config exists for this display
            if display_id not in self._config.displays:
                self._config.displays[display_id] = DisplayConfig(
                    display_id=display_id, enabled=True, info=info
                )

            # Only create enabled full displays (not I2C)
            if info.screen_type == ScreenType.I2C:
                continue

            if not self.is_display_enabled(display_id):
                logger.info(f"Display {display_id} is disabled, skipping")
                continue

            display = DisplayFactory.create(info)
            if display and display.supports_modes:
                self._displays[display_id] = display
                displays.append(display)
                logger.info(f"Created display: {display_id}")

        self._config.save()
        return displays

    def get_enabled_full_displays(self) -> List[BaseDisplay]:
        """Get list of enabled full displays."""
        return list(self._displays.values())

    def get_mirrored_display(self) -> Optional[BaseDisplay]:
        """Get a mirrored display if mirroring is enabled and multiple displays exist.

        Returns:
            MirroredDisplay if mirroring enabled with multiple displays,
            single display if only one, or None if no displays.
        """
        displays = self.get_enabled_full_displays()

        if not displays:
            return None

        if len(displays) == 1:
            return displays[0]

        if self._config.mirror_enabled:
            # Use largest display as primary
            primary = max(displays, key=lambda d: d.width * d.height)
            return MirroredDisplay(displays, primary)

        # Not mirroring - return the primary/first display
        return displays[0]

    def get_all_display_info(self) -> List[Dict[str, Any]]:
        """Get info about all detected displays."""
        result = []
        for display_id, info in self._display_infos.items():
            result.append(
                {
                    "id": display_id,
                    "type": info.screen_type.value,
                    "width": info.width,
                    "height": info.height,
                    "device_path": info.device_path,
                    "driver": info.driver,
                    "enabled": self.is_display_enabled(display_id),
                    "supports_modes": info.screen_type != ScreenType.I2C,
                }
            )
        return result

    async def shutdown(self) -> None:
        """Shutdown all displays."""
        for display in self._displays.values():
            try:
                await display.shutdown()
            except Exception as e:
                logger.warning(f"Error shutting down display: {e}")
        self._displays.clear()


def get_multi_display_manager() -> MultiDisplayManager:
    """Get the multi-display manager singleton."""
    return MultiDisplayManager.get_instance()
