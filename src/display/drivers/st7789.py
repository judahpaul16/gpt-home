import logging
import os
import time
from typing import Any, Dict, Optional, Tuple

import numpy as np
from PIL import Image

from ..base import BaseDisplay, Color, Colors, DisplayInfo

logger = logging.getLogger("display.st7789")

_ST7789_SWRESET = 0x01
_ST7789_SLPOUT = 0x11
_ST7789_NORON = 0x13
_ST7789_INVON = 0x21
_ST7789_DISPON = 0x29
_ST7789_DISPOFF = 0x28
_ST7789_SLPIN = 0x10
_ST7789_CASET = 0x2A
_ST7789_RASET = 0x2B
_ST7789_RAMWR = 0x2C
_ST7789_COLMOD = 0x3A
_ST7789_MADCTL = 0x36

_MADCTL_ROTATION = {
    0: 0x00,
    90: 0x60,
    180: 0xC0,
    270: 0xA0,
}


class St7789Display(BaseDisplay):
    supports_modes: bool = False

    def __init__(self, info: DisplayInfo):
        super().__init__(info)
        self._pygame = None
        self._back_buffer = None
        self._font_cache: Dict[Tuple[int, Optional[str]], Any] = {}
        self._spi = None
        self._dc_pin = info.gpio_dc
        self._rst_pin = info.gpio_rst
        self._bl_pin = info.gpio_bl
        self._initialized = False
        self._gpio_request = None
        self._gpiod_Value = None
        self._bl_active_low = info.gpio_bl_active_low
        self._col_offset = 0
        self._row_offset = 0
        self._caset_cmd = None
        self._raset_cmd = None
        self._rgb565_buf = None

    def _compute_offsets(self):
        r = self.info.rotation % 360
        native_w, native_h = 240, 280
        if r in (0, 180):
            self._col_offset = 0
            self._row_offset = (320 - native_h) // 2
        else:
            self._col_offset = (320 - native_h) // 2
            self._row_offset = 0

    async def initialize(self) -> bool:
        logger.debug("Initializing SPI LCD display (%dx%d)...", self.width, self.height)

        try:
            import spidev
        except ImportError:
            logger.error("spidev not installed")
            return False

        try:
            import gpiod
            from gpiod.line import Direction, Value
            self._gpiod_Value = Value
        except ImportError:
            logger.error("gpiod not installed")
            return False

        bus = self.info.spi_bus if self.info.spi_bus is not None else 0
        cs = self.info.spi_cs if self.info.spi_cs is not None else 0
        spi_device = f"/dev/spidev{bus}.{cs}"

        if not os.path.exists(spi_device):
            logger.error("SPI device %s not found", spi_device)
            return False

        chip_path = "/dev/gpiochip0"
        if not os.path.exists(chip_path):
            logger.error("GPIO chip %s not found", chip_path)
            return False

        try:
            self._spi = spidev.SpiDev()
            self._spi.open(bus, cs)
            self._spi.max_speed_hz = self.info.spi_speed_hz or 62_500_000
            self._spi.mode = 0
            self._spi.no_cs = False

            if self._dc_pin is None:
                logger.error("gpio_dc pin is required for SPI LCD")
                return False

            line_config = {
                self._dc_pin: gpiod.LineSettings(
                    direction=Direction.OUTPUT, output_value=Value.ACTIVE
                ),
            }
            if self._rst_pin is not None:
                line_config[self._rst_pin] = gpiod.LineSettings(
                    direction=Direction.OUTPUT, output_value=Value.ACTIVE
                )
            if self._bl_pin is not None:
                bl_off = Value.ACTIVE if self._bl_active_low else Value.INACTIVE
                line_config[self._bl_pin] = gpiod.LineSettings(
                    direction=Direction.OUTPUT, output_value=bl_off
                )

            self._gpio_request = gpiod.request_lines(
                chip_path, consumer="st7789", config=line_config
            )

            self._hw_reset()
            self._init_st7789()

            if self._bl_pin is not None:
                self._gpio_set(self._bl_pin, not self._bl_active_low)

            import pygame
            self._pygame = pygame
            pygame.font.init()

            self._back_buffer = pygame.Surface((self.width, self.height))
            self._back_buffer.fill((0, 0, 0))

            self._compute_offsets()
            self._precompute_window_cmds()
            self._rgb565_buf = np.empty((self.height, self.width), dtype=np.uint16)

            self.show_sync()

            self._running = True
            self._initialized = True

            logger.debug(
                "SPI LCD initialized: %dx%d on spidev%d.%d",
                self.width, self.height, bus, cs,
            )
            return True

        except Exception as e:
            logger.error("SPI LCD init failed: %s", e)
            self._cleanup_hw()
            return False

    def _gpio_set(self, pin: int, high: bool):
        Value = self._gpiod_Value
        self._gpio_request.set_value(pin, Value.ACTIVE if high else Value.INACTIVE)

    def _hw_reset(self):
        if self._rst_pin is None:
            return
        self._gpio_set(self._rst_pin, True)
        time.sleep(0.05)
        self._gpio_set(self._rst_pin, False)
        time.sleep(0.05)
        self._gpio_set(self._rst_pin, True)
        time.sleep(0.15)

    def _send_command(self, cmd: int, data: bytes = None):
        self._gpio_set(self._dc_pin, False)
        self._spi.writebytes([cmd])
        if data:
            self._gpio_set(self._dc_pin, True)
            self._spi.writebytes2(list(data))

    def _init_st7789(self):
        self._send_command(_ST7789_SWRESET)
        time.sleep(0.15)

        self._send_command(_ST7789_SLPOUT)
        time.sleep(0.5)

        self._send_command(_ST7789_COLMOD, bytes([0x05]))

        rotation = self.info.rotation % 360
        madctl = _MADCTL_ROTATION.get(rotation, 0x00)
        self._send_command(_ST7789_MADCTL, bytes([madctl]))

        self._send_command(_ST7789_INVON)

        self._send_command(_ST7789_NORON)
        time.sleep(0.01)

        self._send_command(_ST7789_DISPON)
        time.sleep(0.1)

    def _precompute_window_cmds(self):
        x0, y0 = self._col_offset, self._row_offset
        x1 = x0 + self.width - 1
        y1 = y0 + self.height - 1
        self._caset_cmd = bytes([
            (x0 >> 8) & 0xFF, x0 & 0xFF,
            (x1 >> 8) & 0xFF, x1 & 0xFF,
        ])
        self._raset_cmd = bytes([
            (y0 >> 8) & 0xFF, y0 & 0xFF,
            (y1 >> 8) & 0xFF, y1 & 0xFF,
        ])

    def _set_window(self):
        self._send_command(_ST7789_CASET, self._caset_cmd)
        self._send_command(_ST7789_RASET, self._raset_cmd)

    def _cleanup_hw(self):
        if self._spi:
            try:
                self._spi.close()
            except Exception:
                pass
            self._spi = None
        if hasattr(self, '_gpio_request') and self._gpio_request:
            try:
                if self._bl_pin is not None:
                    self._gpio_set(self._bl_pin, self._bl_active_low)
                self._gpio_request.release()
            except Exception:
                pass
            self._gpio_request = None

    def _get_font(self, size: int, font_path: Optional[str] = None) -> Any:
        cache_key = (size, font_path)
        if cache_key not in self._font_cache:
            try:
                if font_path and os.path.exists(font_path):
                    self._font_cache[cache_key] = self._pygame.font.Font(
                        font_path, size
                    )
                else:
                    for path in [
                        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                        "/usr/share/fonts/opentype/noto/NotoSansCJKSC-Regular.otf",
                        "/usr/share/fonts/opentype/noto/NotoSansCJKJP-Regular.otf",
                        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
                        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
                        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                        "/usr/share/fonts/TTF/DejaVuSans.ttf",
                        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
                    ]:
                        if os.path.exists(path):
                            self._font_cache[cache_key] = self._pygame.font.Font(
                                path, size
                            )
                            break
                    else:
                        self._font_cache[cache_key] = self._pygame.font.Font(None, size)
            except Exception:
                self._font_cache[cache_key] = self._pygame.font.Font(None, size)
        return self._font_cache[cache_key]

    def clear_sync(self, color: Color = Colors.BLACK) -> None:
        if self._back_buffer:
            self._back_buffer.fill((color.r, color.g, color.b))

    def fill_rect_sync(
        self, x: int, y: int, w: int, h: int, color: Color = Colors.WHITE
    ) -> None:
        if self._back_buffer and self._pygame:
            self._pygame.draw.rect(
                self._back_buffer, (color.r, color.g, color.b), (x, y, w, h)
            )

    def get_text_size(
        self, text: str, size: int = 24, font_path: Optional[str] = None
    ) -> Tuple[int, int]:
        if self._pygame:
            font = self._get_font(size, font_path)
            return font.size(text)
        return (len(text) * int(size * 0.6), size)

    def set_clip(self, x: int, y: int, w: int, h: int) -> None:
        if self._back_buffer:
            self._back_buffer.set_clip((x, y, w, h))

    def clear_clip(self) -> None:
        if self._back_buffer:
            self._back_buffer.set_clip(None)

    def draw_text_sync(
        self,
        text: str,
        x: int,
        y: int,
        color: Color = Colors.WHITE,
        size: int = 24,
        font_path: Optional[str] = None,
    ) -> None:
        if self._back_buffer and self._pygame:
            font = self._get_font(size, font_path)
            surface = font.render(text, True, (color.r, color.g, color.b))
            self._back_buffer.blit(surface, (x, y))

    def draw_line_sync(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        color: Color = Colors.WHITE,
        width: int = 1,
    ) -> None:
        if self._back_buffer and self._pygame:
            self._pygame.draw.line(
                self._back_buffer,
                (color.r, color.g, color.b),
                (x1, y1),
                (x2, y2),
                width,
            )

    def draw_circle_sync(
        self,
        cx: int,
        cy: int,
        radius: int,
        color: Color = Colors.WHITE,
        filled: bool = True,
    ) -> None:
        if self._back_buffer and self._pygame:
            if filled:
                self._pygame.draw.circle(
                    self._back_buffer, (color.r, color.g, color.b), (cx, cy), radius
                )
            else:
                self._pygame.draw.circle(
                    self._back_buffer, (color.r, color.g, color.b), (cx, cy), radius, 1
                )

    def draw_rounded_rect_sync(
        self, x: int, y: int, w: int, h: int, radius: int, color: Color = Colors.WHITE
    ) -> None:
        if self._back_buffer and self._pygame:
            rect = self._pygame.Rect(x, y, w, h)
            self._pygame.draw.rect(
                self._back_buffer,
                (color.r, color.g, color.b),
                rect,
                border_radius=radius,
            )

    def draw_arc_sync(
        self,
        cx: int,
        cy: int,
        radius: int,
        start_angle: float,
        end_angle: float,
        color: Color = Colors.WHITE,
        width: int = 1,
    ) -> None:
        if self._back_buffer and self._pygame:
            rect = self._pygame.Rect(cx - radius, cy - radius, radius * 2, radius * 2)
            self._pygame.draw.arc(
                self._back_buffer,
                (color.r, color.g, color.b),
                rect,
                start_angle,
                end_angle,
                width,
            )

    def draw_pil_image_sync(
        self, img: Image.Image, x: int, y: int, w: int = 0, h: int = 0
    ) -> None:
        if self._back_buffer and self._pygame:
            if w > 0 and h > 0 and (img.width != w or img.height != h):
                img = img.resize((w, h), Image.Resampling.LANCZOS)
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            raw_data = img.tobytes()
            surface = self._pygame.image.fromstring(raw_data, img.size, "RGBA")
            self._back_buffer.blit(surface, (x, y))

    def show_sync(self) -> None:
        if not self._back_buffer or not self._pygame or not self._spi:
            return

        raw = self._pygame.image.tostring(self._back_buffer, "RGB")
        arr = np.frombuffer(raw, dtype=np.uint8).reshape(self.height, self.width, 3)

        r = arr[:, :, 0].astype(np.uint16)
        g = arr[:, :, 1].astype(np.uint16)
        b = arr[:, :, 2].astype(np.uint16)
        np.bitwise_or(
            np.bitwise_or(np.left_shift(r, 8) & 0xF800, np.left_shift(g, 3) & 0x07E0),
            np.right_shift(b, 3),
            out=self._rgb565_buf,
        )

        pixel_data = self._rgb565_buf.astype(">u2").tobytes()

        self._set_window()

        self._gpio_set(self._dc_pin, False)
        self._spi.writebytes([_ST7789_RAMWR])
        self._gpio_set(self._dc_pin, True)
        self._spi.writebytes2(pixel_data)

    async def clear(self, color: Color = Colors.BLACK) -> None:
        self.clear_sync(color)

    async def fill_rect(
        self, x: int, y: int, w: int, h: int, color: Color = Colors.WHITE
    ) -> None:
        self.fill_rect_sync(x, y, w, h, color)

    async def draw_text(
        self,
        text: str,
        x: int,
        y: int,
        color: Color = Colors.WHITE,
        size: int = 24,
        font_path: Optional[str] = None,
    ) -> None:
        self.draw_text_sync(text, x, y, color, size, font_path)

    async def draw_line(
        self, x1: int, y1: int, x2: int, y2: int, color: Color = Colors.WHITE
    ) -> None:
        self.draw_line_sync(x1, y1, x2, y2, color)

    async def draw_circle(
        self,
        cx: int,
        cy: int,
        radius: int,
        color: Color = Colors.WHITE,
        filled: bool = True,
    ) -> None:
        self.draw_circle_sync(cx, cy, radius, color, filled)

    async def draw_image(
        self, image_path: str, x: int, y: int, width: int = 0, height: int = 0
    ) -> None:
        try:
            if self._pygame:
                img = self._pygame.image.load(image_path)
                if width > 0 and height > 0:
                    img = self._pygame.transform.scale(img, (width, height))
                if self._back_buffer:
                    self._back_buffer.blit(img, (x, y))
        except Exception as e:
            logger.error("Failed to load image %s: %s", image_path, e)

    async def show(self) -> None:
        self.show_sync()

    async def shutdown(self) -> None:
        logger.debug("Shutting down SPI LCD display")
        self._running = False
        self._initialized = False

        if self._spi:
            try:
                self._send_command(_ST7789_DISPOFF)
                self._send_command(_ST7789_SLPIN)
            except Exception:
                pass

        self._cleanup_hw()

        if self._pygame:
            try:
                self._pygame.font.quit()
            except Exception:
                pass
            self._pygame = None

        self._back_buffer = None
        self._font_cache.clear()
        self._rgb565_buf = None
