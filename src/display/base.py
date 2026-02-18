import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, List, Optional, Tuple

if TYPE_CHECKING:
    from PIL import Image


class DisplayMode(Enum):
    SMART = auto()
    CLOCK = auto()
    WEATHER = auto()
    GALLERY = auto()
    WAVEFORM = auto()
    OFF = auto()


class ScreenType(Enum):
    HDMI = "hdmi"
    SPI_TFT = "spi_tft"
    I2C = "i2c"


@dataclass
class DisplayInfo:
    screen_type: ScreenType
    width: int
    height: int
    device_path: Optional[str] = None
    bus: Optional[int] = None
    address: Optional[int] = None
    rotation: int = 0
    driver: Optional[str] = None
    connector: Optional[str] = None


@dataclass
class Color:
    r: int
    g: int
    b: int

    def to_tuple(self) -> Tuple[int, int, int]:
        return (self.r, self.g, self.b)

    def to_hex(self) -> str:
        return f"#{self.r:02x}{self.g:02x}{self.b:02x}"

    @classmethod
    def from_hex(cls, hex_color: str) -> "Color":
        hex_color = hex_color.lstrip("#")
        return cls(
            int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        )


class Colors:
    BLACK = Color(0, 0, 0)
    WHITE = Color(255, 255, 255)
    RED = Color(255, 0, 0)
    GREEN = Color(0, 255, 0)
    BLUE = Color(0, 0, 255)
    YELLOW = Color(255, 255, 0)
    CYAN = Color(0, 255, 255)
    MAGENTA = Color(255, 0, 255)
    ORANGE = Color(255, 165, 0)
    GRAY = Color(128, 128, 128)
    DARK_GRAY = Color(64, 64, 64)
    LIGHT_GRAY = Color(192, 192, 192)

    PRIMARY = Color(99, 102, 241)
    ACCENT = Color(139, 92, 246)
    SUCCESS = Color(16, 185, 129)
    WARNING = Color(245, 158, 11)
    ERROR = Color(239, 68, 68)


class BaseDisplay(ABC):
    """Base class for all display drivers.

    Displays are categorized into two types:
    - Full displays (supports_modes=True): Support all display modes (SMART, CLOCK,
      WEATHER, GALLERY, WAVEFORM, OFF) with animations and graphics. Examples:
      TFT LCD, HDMI framebuffer displays.
    - Simple displays (supports_modes=False): Text-only displays used for showing
      responses and status messages. Examples: I2C display (128x32, 128x64).
    """

    # Override in subclasses to indicate display capabilities
    supports_modes: bool = True  # Full graphical displays support modes

    def __init__(self, info: DisplayInfo):
        self.info = info
        self.width = info.width
        self.height = info.height
        self._running = False
        self._current_mode = DisplayMode.SMART
        self._animation_task: Optional[asyncio.Task] = None

    @abstractmethod
    async def initialize(self) -> bool:
        pass

    @abstractmethod
    async def clear(self, color: Color = Colors.BLACK) -> None:
        pass

    @abstractmethod
    async def fill_rect(self, x: int, y: int, w: int, h: int, color: Color) -> None:
        pass

    @abstractmethod
    async def draw_text(
        self,
        text: str,
        x: int,
        y: int,
        color: Color = Colors.WHITE,
        font_size: int = 16,
        font_name: Optional[str] = None,
    ) -> None:
        pass

    @abstractmethod
    async def draw_line(
        self, x1: int, y1: int, x2: int, y2: int, color: Color, width: int = 1
    ) -> None:
        pass

    @abstractmethod
    async def draw_circle(
        self, cx: int, cy: int, radius: int, color: Color, filled: bool = False
    ) -> None:
        pass

    @abstractmethod
    async def draw_image(
        self,
        image_path: str,
        x: int,
        y: int,
        width: Optional[int] = None,
        height: Optional[int] = None,
    ) -> None:
        pass

    @abstractmethod
    async def show(self) -> None:
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        pass

    def clear_sync(self, color: "Color" = None) -> None:
        """Synchronous clear - override in drivers for performance."""
        if color is None:
            color = Colors.BLACK
        pass

    def fill_rect_sync(self, x: int, y: int, w: int, h: int, color: "Color") -> None:
        """Synchronous fill rectangle - override in drivers for performance."""
        pass

    def get_text_size(
        self, text: str, font_size: int = 16, font_name: Optional[str] = None
    ) -> tuple:
        """Get the pixel width and height of rendered text.

        Override in drivers for accurate measurement using actual font metrics.

        Returns:
            Tuple of (width, height) in pixels
        """
        # Fallback estimate - override in drivers for accuracy
        return (len(text) * int(font_size * 0.6), font_size)

    def set_clip(self, x: int, y: int, w: int, h: int) -> None:
        """Set clipping rectangle for subsequent draw operations."""
        pass

    def clear_clip(self) -> None:
        """Clear clipping rectangle."""
        pass

    def draw_text_sync(
        self,
        text: str,
        x: int,
        y: int,
        color: "Color" = None,
        font_size: int = 16,
        font_name: Optional[str] = None,
    ) -> None:
        """Synchronous draw text - override in drivers for performance."""
        if color is None:
            color = Colors.WHITE
        pass

    def draw_line_sync(
        self, x1: int, y1: int, x2: int, y2: int, color: "Color", width: int = 1
    ) -> None:
        """Synchronous draw line - override in drivers for performance."""
        pass

    def draw_circle_sync(
        self, cx: int, cy: int, radius: int, color: "Color", filled: bool = False
    ) -> None:
        """Synchronous draw circle - override in drivers for performance."""
        pass

    def draw_rounded_rect_sync(
        self, x: int, y: int, w: int, h: int, radius: int, color: "Color"
    ) -> None:
        """Synchronous draw rounded rectangle - override in drivers for performance."""
        pass

    def draw_arc_sync(
        self,
        cx: int,
        cy: int,
        radius: int,
        start: float,
        end: float,
        color: "Color",
        width: int = 3,
    ) -> None:
        """Synchronous draw arc - override in drivers for performance."""
        pass

    def draw_pil_image_sync(
        self,
        img: "Image.Image",
        x: int,
        y: int,
        width: Optional[int] = None,
        height: Optional[int] = None,
    ) -> None:
        """Synchronous draw PIL image - override in drivers for performance."""
        pass

    def show_sync(self) -> None:
        """Synchronous show/flip buffers - override in drivers for performance."""
        pass

    def restore_tty(self) -> None:
        """Restore TTY to text mode - override in drivers that modify TTY state."""
        pass

    def scale_x(self, x: int, base_width: int = 480) -> int:
        return int(x * self.width / base_width)

    def scale_y(self, y: int, base_height: int = 320) -> int:
        return int(y * self.height / base_height)

    def scale_font(self, size: int, base_width: int = 480) -> int:
        scale = min(self.width / base_width, self.height / 320)
        return max(8, int(size * scale))

    def get_center(self) -> Tuple[int, int]:
        return (self.width // 2, self.height // 2)

    async def start_animation(self, coro) -> None:
        await self.stop_animation()
        self._animation_task = asyncio.create_task(coro)

    async def stop_animation(self) -> None:
        if self._animation_task and not self._animation_task.done():
            self._animation_task.cancel()
            try:
                await self._animation_task
            except asyncio.CancelledError:
                pass
            self._animation_task = None

    @property
    def current_mode(self) -> DisplayMode:
        return self._current_mode

    @current_mode.setter
    def current_mode(self, mode: DisplayMode) -> None:
        self._current_mode = mode

    def display_text(self, text: str, x: int = 0, y: int = 0) -> None:
        """Simple text display method for text-only displays.

        This is used by simple displays (like I2C display) to show response text.
        Full displays may override this but typically use the more complex
        animation methods instead.
        """
        pass  # Default no-op, override in simple display drivers
