"""Virtual console ownership for displays that render straight to the GPU.

The kernel console keeps painting the framebuffer (getty prompt, cursor
blink, kernel messages, screen blanking) until the active virtual
console is switched to graphics mode. Holding it in graphics mode for as
long as the display renders is what keeps the console from drawing over
the animations.
"""

import fcntl
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger("display.console")

KDSETMODE = 0x4B3A
KD_TEXT = 0x00
KD_GRAPHICS = 0x01

ACTIVE_CONSOLE = Path("/sys/class/tty/tty0/active")


class Console:
    def __init__(self) -> None:
        self._fd: Optional[int] = None
        self._path: Optional[str] = None

    @property
    def held(self) -> bool:
        return self._fd is not None

    def acquire(self) -> bool:
        if self._fd is not None:
            return True

        path = self._active_path()
        if path is None:
            logger.warning("No virtual console device is visible, the kernel console may draw over the display")
            return False

        try:
            fd = os.open(path, os.O_RDWR | os.O_NOCTTY)
        except OSError as e:
            logger.warning("Could not open %s: %s", path, e)
            return False

        try:
            fcntl.ioctl(fd, KDSETMODE, KD_GRAPHICS)
        except OSError as e:
            logger.warning("Could not switch %s to graphics mode: %s", path, e)
            os.close(fd)
            return False

        self._fd = fd
        self._path = path
        logger.debug("%s switched to graphics mode", path)
        return True

    def release(self) -> None:
        if self._fd is None:
            return
        try:
            fcntl.ioctl(self._fd, KDSETMODE, KD_TEXT)
            logger.debug("%s restored to text mode", self._path)
        except OSError as e:
            logger.warning("Could not restore %s to text mode: %s", self._path, e)
        finally:
            os.close(self._fd)
            self._fd = None
            self._path = None

    @staticmethod
    def _active_path() -> Optional[str]:
        name = ""
        try:
            name = ACTIVE_CONSOLE.read_text().strip()
        except OSError:
            pass
        for candidate in (f"/dev/{name}" if name else None, "/dev/tty1"):
            if candidate and os.path.exists(candidate):
                return candidate
        return None
