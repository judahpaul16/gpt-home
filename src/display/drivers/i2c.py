import logging
import textwrap
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from ..base import BaseDisplay, Color, Colors, DisplayInfo

logger = logging.getLogger(__name__)


class I2cDisplay(BaseDisplay):
    """I2C display driver for simple text output.

    This is a simple text-only display used for showing assistant responses
    and status messages. It does NOT support the complex display modes
    (SMART, CLOCK, WEATHER, GALLERY, WAVEFORM) - those are only available
    on full graphical displays like PiScreen or HDMI framebuffer.

    The I2C display is an optional peripheral that provides a convenient way
    to see responses without looking at the web interface.
    """

    # I2C display is a simple text display, not a full graphical display
    supports_modes: bool = False

    def __init__(self, info: DisplayInfo):
        super().__init__(info)
        self._device = None
        self._image: Optional[Image.Image] = None
        self._draw: Optional[ImageDraw.ImageDraw] = None
        self._font_cache = {}
        self._clip_rect = None

    async def initialize(self) -> bool:
        try:
            import adafruit_ssd1306
            import busio
            from board import SCL, SDA

            i2c = busio.I2C(SCL, SDA)
            self._device = adafruit_ssd1306.SSD1306_I2C(
                self.width, self.height, i2c, addr=self.info.address or 0x3C
            )

            if self.info.rotation:
                self._device.rotation = self.info.rotation

            self._device.fill(0)
            self._device.show()

            self._image = Image.new("1", (self.width, self.height), 0)
            self._draw = ImageDraw.Draw(self._image)

            self._running = True
            logger.info(f"I2C display initialized: {self.width}x{self.height}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize I2C display: {e}")
            return False

    def _color_to_fill(self, color: Color) -> int:
        return 0 if color.r < 128 and color.g < 128 and color.b < 128 else 1

    def clear_sync(self, color: Color = Colors.BLACK) -> None:
        if self._draw:
            fill = self._color_to_fill(color)
            self._draw.rectangle([(0, 0), (self.width, self.height)], fill=fill)

    def fill_rect_sync(self, x: int, y: int, w: int, h: int, color: Color) -> None:
        if self._draw:
            fill = self._color_to_fill(color)
            self._draw.rectangle([(x, y), (x + w, y + h)], fill=fill)

    def set_clip(self, x: int, y: int, w: int, h: int) -> None:
        self._clip_rect = (x, y, w, h)

    def clear_clip(self) -> None:
        self._clip_rect = None

    def draw_text_sync(
        self,
        text: str,
        x: int,
        y: int,
        color: Color = Colors.WHITE,
        font_size: int = 10,
        font_name: Optional[str] = None,
    ) -> None:
        if self._draw:
            fill = self._color_to_fill(color)
            font = self._get_font(font_size, font_name)
            self._draw.text((x, y), text, fill=fill, font=font)

    def draw_line_sync(
        self, x1: int, y1: int, x2: int, y2: int, color: Color, width: int = 1
    ) -> None:
        if self._draw:
            fill = self._color_to_fill(color)
            self._draw.line([(x1, y1), (x2, y2)], fill=fill, width=width)

    def draw_circle_sync(
        self, cx: int, cy: int, radius: int, color: Color, filled: bool = False
    ) -> None:
        if self._draw:
            fill = self._color_to_fill(color)
            bbox = [(cx - radius, cy - radius), (cx + radius, cy + radius)]
            if filled:
                self._draw.ellipse(bbox, fill=fill)
            else:
                self._draw.ellipse(bbox, outline=fill)

    def draw_rounded_rect_sync(
        self, x: int, y: int, w: int, h: int, radius: int, color: Color
    ) -> None:
        if self._draw:
            fill = self._color_to_fill(color)
            self._draw.rounded_rectangle(
                [(x, y), (x + w, y + h)], radius=radius, fill=fill
            )

    def draw_arc_sync(
        self,
        cx: int,
        cy: int,
        radius: int,
        start: float,
        end: float,
        color: Color,
        width: int = 1,
    ) -> None:
        if self._draw:
            fill = self._color_to_fill(color)
            bbox = [(cx - radius, cy - radius), (cx + radius, cy + radius)]
            self._draw.arc(bbox, start=start, end=end, fill=fill, width=width)

    def show_sync(self) -> None:
        if self._device and self._image:
            self._device.image(self._image)
            self._device.show()

    async def clear(self, color: Color = Colors.BLACK) -> None:
        self.clear_sync(color)

    async def fill_rect(self, x: int, y: int, w: int, h: int, color: Color) -> None:
        self.fill_rect_sync(x, y, w, h, color)

    async def draw_text(
        self,
        text: str,
        x: int,
        y: int,
        color: Color = Colors.WHITE,
        font_size: int = 10,
        font_name: Optional[str] = None,
    ) -> None:
        self.draw_text_sync(text, x, y, color, font_size, font_name)

    async def draw_line(
        self, x1: int, y1: int, x2: int, y2: int, color: Color, width: int = 1
    ) -> None:
        self.draw_line_sync(x1, y1, x2, y2, color, width)

    async def draw_circle(
        self, cx: int, cy: int, radius: int, color: Color, filled: bool = False
    ) -> None:
        self.draw_circle_sync(cx, cy, radius, color, filled)

    async def draw_image(
        self,
        image_path: str,
        x: int,
        y: int,
        width: Optional[int] = None,
        height: Optional[int] = None,
    ) -> None:
        if not self._image:
            return
        try:
            img = Image.open(image_path).convert("1")
            if width or height:
                new_width = width or img.width
                new_height = height or img.height
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            self._image.paste(img, (x, y))
        except Exception as e:
            logger.error(f"Failed to draw image: {e}")

    async def show(self) -> None:
        self.show_sync()

    async def shutdown(self) -> None:
        self._running = False
        await self.stop_animation()
        if self._device:
            self._device.fill(0)
            self._device.show()

    def set_rotation(self, rotation: int) -> None:
        if self._device:
            self._device.rotation = rotation
            self._device.show()

    def _get_font(self, size: int, font_name: Optional[str] = None):
        cache_key = (size, font_name)
        if cache_key in self._font_cache:
            return self._font_cache[cache_key]

        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        ]

        if font_name:
            font_paths.insert(0, font_name)

        for path in font_paths:
            if Path(path).exists():
                try:
                    font = ImageFont.truetype(path, size)
                    self._font_cache[cache_key] = font
                    return font
                except Exception:
                    continue

        font = ImageFont.load_default()
        self._font_cache[cache_key] = font
        return font

    def display_text(self, text: str, x: int = 0, y: int = 0) -> None:
        """Display text on the I2C display.

        This is the primary method for showing assistant responses on the
        simple I2C display. Text is automatically wrapped to fit the
        display width.

        Args:
            text: Text to display (will be wrapped automatically)
            x: Starting X position (default 0)
            y: Starting Y position (default 0, but typically 10 to leave header)
        """
        if not self._draw:
            return

        # Clear the text area (preserve header if y > 0)
        if y > 0:
            self._draw.rectangle([(0, y), (self.width, self.height)], fill=0)
        else:
            self._draw.rectangle([(0, 0), (self.width, self.height)], fill=0)

        # Calculate characters per line based on display width
        # Assuming ~6 pixels per character for default font
        chars_per_line = self.width // 6
        lines = textwrap.fill(text, chars_per_line).split("\n")

        # Calculate how many lines fit on display
        line_height = 10
        max_lines = (self.height - y) // line_height

        # Display text lines
        for i, line in enumerate(lines[:max_lines]):
            self._draw.text((x, y + i * line_height), line, fill=1)

        self.show_sync()

    async def display_text_async(self, text: str, x: int = 0, y: int = 10) -> None:
        """Async wrapper for display_text."""
        self.display_text(text, x, y)

    def display_header(self, ip_address: str = "", cpu_temp: int = 0) -> None:
        """Display IP address and CPU temperature in header area.

        Args:
            ip_address: IP address to display
            cpu_temp: CPU temperature in Celsius
        """
        if not self._draw:
            return

        # Clear header area only
        self._draw.rectangle([(0, 0), (self.width, 9)], fill=0)

        # Display IP
        if ip_address:
            self._draw.text((0, 0), ip_address, fill=1)

        # Display temperature
        if cpu_temp > 0:
            temp_str = f"{cpu_temp}C"
            # Right-align temperature
            temp_x = self.width - len(temp_str) * 6 - 2
            self._draw.text((temp_x, 0), temp_str, fill=1)

        self.show_sync()

    def display_status(self, status: str) -> None:
        """Display a status message (e.g., 'Listening...', 'Thinking...').

        Args:
            status: Status message to display
        """
        self.display_text(status, x=0, y=10)
