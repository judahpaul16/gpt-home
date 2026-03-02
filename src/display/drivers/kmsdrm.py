"""SDL2 KMSDRM Display Driver - Direct rendering to display hardware via /dev/dri."""

import logging
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from PIL import Image

from ..base import BaseDisplay, Color, Colors, DisplayInfo

logger = logging.getLogger("display.kmsdrm")


@contextmanager
def _suppress_stderr():
    stderr_fd = sys.stderr.fileno()
    orig_stderr_fd = os.dup(stderr_fd)
    devnull = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull, stderr_fd)
        yield
    finally:
        os.dup2(orig_stderr_fd, stderr_fd)
        os.close(orig_stderr_fd)
        os.close(devnull)


class KmsdrmDisplay(BaseDisplay):
    supports_modes: bool = True

    def __init__(self, info: DisplayInfo):
        super().__init__(info)
        self._pygame = None
        self._screen = None
        self._back_buffer = None
        self._font_cache: Dict[Tuple[int, Optional[str]], Any] = {}
        self._initialized = False

    async def initialize(self) -> bool:
        logger.debug("Initializing KMSDRM display...")

        os.environ["SDL_VIDEODRIVER"] = "kmsdrm"
        os.environ["SDL_KMSDRM_REQUIRE_DRM_MASTER"] = "0"
        os.environ.setdefault("XDG_RUNTIME_DIR", "/tmp")

        try:
            import pygame

            self._pygame = pygame
            pygame.display.init()
            pygame.font.init()

            self._screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
            self.width, self.height = self._screen.get_size()

            pygame.mouse.set_visible(False)

            self._back_buffer = pygame.Surface(
                (self.width, self.height)
            ).convert(self._screen)
            self._back_buffer.fill((0, 0, 0))

            screen_bits = self._screen.get_bitsize()
            screen_masks = self._screen.get_masks()
            logger.debug(
                "Screen surface: %d-bit, masks R=0x%X G=0x%X B=0x%X",
                screen_bits, screen_masks[0], screen_masks[1], screen_masks[2],
            )

            self._running = True
            self._initialized = True

            logger.debug(
                "KMSDRM initialized: %dx%d (driver: %s)",
                self.width,
                self.height,
                pygame.display.get_driver(),
            )
            return True

        except Exception as e:
            logger.error("KMSDRM init failed: %s", e)
            if self._pygame:
                try:
                    self._pygame.quit()
                except Exception:
                    pass
            self._pygame = None
            return False

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
        """Get the pixel width and height of rendered text.

        Returns:
            Tuple of (width, height) in pixels
        """
        if self._pygame:
            font = self._get_font(size, font_path)
            return font.size(text)
        return (len(text) * int(size * 0.6), size)

    def set_clip(self, x: int, y: int, w: int, h: int) -> None:
        """Set clipping rectangle for subsequent draw operations."""
        if self._back_buffer:
            self._back_buffer.set_clip((x, y, w, h))

    def clear_clip(self) -> None:
        """Clear clipping rectangle."""
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

    def show_sync(self) -> None:
        if not self._screen or not self._back_buffer or not self._pygame:
            return

        self._screen.blit(self._back_buffer, (0, 0))

        with _suppress_stderr():
            self._pygame.display.flip()

    async def show(self) -> None:
        self.show_sync()

    async def shutdown(self) -> None:
        logger.debug("Shutting down KMSDRM display")
        self._running = False
        self._initialized = False

        if self._pygame:
            try:
                self._pygame.quit()
            except Exception:
                pass
            self._pygame = None

        self._screen = None
        self._back_buffer = None
        self._font_cache.clear()


def check_drm_support() -> dict:
    status = {
        "available": False,
        "drm_devices": [],
        "sdl_driver": None,
        "error": None,
    }

    drm_path = Path("/dev/dri")
    if drm_path.exists():
        for device in drm_path.iterdir():
            if device.name.startswith("card"):
                status["drm_devices"].append(str(device))

    if not status["drm_devices"]:
        status["error"] = "No DRM devices found in /dev/dri"
        return status

    try:
        os.environ["SDL_VIDEODRIVER"] = "kmsdrm"
        os.environ["SDL_KMSDRM_REQUIRE_DRM_MASTER"] = "0"

        import pygame

        pygame.init()
        driver = pygame.display.get_driver()
        status["sdl_driver"] = driver
        status["available"] = "kmsdrm" in driver.lower()
        pygame.quit()
    except Exception as e:
        status["error"] = str(e)

    return status
