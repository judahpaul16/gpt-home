import logging
import os
import re
import subprocess
from pathlib import Path
from typing import List, Optional

from .base import DisplayInfo, ScreenType

logger = logging.getLogger(__name__)

_logged_no_drm = False


def detect_displays() -> List[DisplayInfo]:
    displays = []

    drm_display = _detect_drm()
    if drm_display:
        displays.append(drm_display)

    i2c_displays = _detect_i2c_oled()
    displays.extend(i2c_displays)

    return displays


def detect_full_displays() -> List[DisplayInfo]:
    all_displays = detect_displays()
    return [d for d in all_displays if d.screen_type != ScreenType.I2C]


def detect_simple_displays() -> List[DisplayInfo]:
    all_displays = detect_displays()
    return [d for d in all_displays if d.screen_type == ScreenType.I2C]


def _detect_drm() -> Optional[DisplayInfo]:
    global _logged_no_drm

    """Detect DRM/KMS display devices.

    Tries multiple methods in order:
    1. Direct /dev/dri/card* access check
    2. Sysfs HDMI connection status
    3. SDL/pygame KMSDRM initialization probe
    """
    dri_path = Path("/dev/dri")
    accessible_card = None

    # Method 1: Check /dev/dri directory directly
    if dri_path.exists():
        drm_cards = list(dri_path.glob("card*"))
        for card in sorted(drm_cards):
            if os.access(card, os.R_OK | os.W_OK):
                accessible_card = card
                break
            else:
                logger.debug(f"No read/write access to {card}")

    if accessible_card:
        _logged_no_drm = False
        width, height = _get_drm_resolution(accessible_card)
        return DisplayInfo(
            screen_type=ScreenType.HDMI,
            width=width,
            height=height,
            device_path=str(accessible_card),
            driver="kmsdrm",
        )

    # Method 2: Check sysfs HDMI connection status
    hdmi_connector = _check_hdmi_connected()
    if hdmi_connector:
        _logged_no_drm = False
        width, height = _get_drm_resolution_from_sysfs()
        logger.info(f"HDMI connected via sysfs ({hdmi_connector}): {width}x{height}")
        return DisplayInfo(
            screen_type=ScreenType.HDMI,
            width=width,
            height=height,
            device_path="/dev/dri/card0",
            driver="kmsdrm",
        )

    # Method 3: Try pygame KMSDRM probe as last resort
    # This can detect displays even when /dev/dri permissions are tricky
    try:
        import pygame

        os.environ["SDL_VIDEODRIVER"] = "kmsdrm"
        os.environ["SDL_KMSDRM_REQUIRE_DRM_MASTER"] = "0"
        os.environ.setdefault("XDG_RUNTIME_DIR", "/tmp")

        pygame.display.init()
        driver = pygame.display.get_driver()

        if "kmsdrm" in driver.lower():
            info = pygame.display.Info()
            width = info.current_w if info.current_w > 0 else 1920
            height = info.current_h if info.current_h > 0 else 1080
            pygame.display.quit()

            logger.info(f"SDL KMSDRM probe successful: {width}x{height}")
            return DisplayInfo(
                screen_type=ScreenType.HDMI,
                width=width,
                height=height,
                device_path="/dev/dri/card0",
                driver="kmsdrm",
            )

        pygame.display.quit()
    except Exception:
        pass

    if not _logged_no_drm:
        logger.debug("No DRM display detected")
        _log_display_debug_info()
        _logged_no_drm = True

    return None


def _check_hdmi_connected() -> Optional[str]:
    """Check if HDMI is connected via sysfs."""
    drm_class = Path("/sys/class/drm")
    if not drm_class.exists():
        return None

    for connector in drm_class.iterdir():
        name = connector.name.lower()
        if "hdmi" in name:
            status_file = connector / "status"
            if status_file.exists():
                try:
                    status = status_file.read_text().strip()
                    if status == "connected":
                        return connector.name
                except Exception:
                    pass
    return None


def _get_drm_resolution_from_sysfs() -> tuple[int, int]:
    """Get resolution from sysfs modes file."""
    drm_class = Path("/sys/class/drm")

    # Try various connector names
    for pattern in [
        "card0-HDMI-A-1",
        "card0-HDMI-A-2",
        "card1-HDMI-A-1",
        "card0-HDMI-1",
        "card1-HDMI-1",
    ]:
        modes_file = drm_class / pattern / "modes"
        if modes_file.exists():
            try:
                modes = modes_file.read_text().strip()
                if modes:
                    first_mode = modes.split("\n")[0]
                    match = re.search(r"(\d+)x(\d+)", first_mode)
                    if match:
                        return int(match.group(1)), int(match.group(2))
            except Exception:
                pass

    return 1920, 1080


def _log_display_debug_info():
    """Log debug information about display detection (debug level only)."""
    dri_path = Path("/dev/dri")
    if dri_path.exists():
        try:
            contents = list(dri_path.iterdir())
            logger.debug(f"/dev/dri contents: {[c.name for c in contents]}")
        except Exception as e:
            logger.debug(f"Error listing /dev/dri: {e}")
    else:
        logger.debug("/dev/dri does not exist")

    # Check sysfs for connected displays
    drm_class = Path("/sys/class/drm")
    if drm_class.exists():
        try:
            for connector in drm_class.iterdir():
                if "card" in connector.name:
                    status_file = connector / "status"
                    if status_file.exists():
                        try:
                            status = status_file.read_text().strip()
                            logger.debug(f"  {connector.name}: {status}")
                        except Exception:
                            pass
        except Exception:
            pass


def _get_drm_resolution(card_path: Path) -> tuple[int, int]:
    width, height = 1920, 1080

    # Try modetest first
    try:
        result = subprocess.run(
            ["modetest", "-M", card_path.name, "-c"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.split("\n"):
                match = re.search(r"(\d{3,4})x(\d{3,4})", line)
                if match:
                    w, h = int(match.group(1)), int(match.group(2))
                    if w >= 640 and h >= 480:
                        return w, h
    except Exception:
        pass

    # Try sysfs modes
    return _get_drm_resolution_from_sysfs()


def _detect_i2c_oled() -> List[DisplayInfo]:
    displays = []

    if not Path("/dev/i2c-1").exists():
        return displays

    oled_addresses = [0x3C, 0x3D]

    for addr in oled_addresses:
        if _probe_i2c_device(1, addr):
            width, height = 128, 32
            displays.append(
                DisplayInfo(
                    screen_type=ScreenType.I2C,
                    width=width,
                    height=height,
                    bus=1,
                    address=addr,
                    driver="ssd1306",
                )
            )
            break

    return displays


def _probe_i2c_device(bus: int, address: int) -> bool:
    # Use i2cdetect first (has timeout) as it's more reliable
    try:
        result = subprocess.run(
            ["i2cdetect", "-y", str(bus)],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0:
            addr_str = f"{address:02x}"
            return addr_str in result.stdout.lower()
    except Exception:
        pass

    # Fallback to smbus2 if i2cdetect unavailable
    try:
        import smbus2

        with smbus2.SMBus(bus) as i2c:
            i2c.read_byte(address)
            return True
    except Exception:
        pass

    return False


def get_display_info_string(displays: List[DisplayInfo]) -> str:
    if not displays:
        return "No displays detected"

    lines = []
    for d in displays:
        if d.screen_type == ScreenType.I2C:
            lines.append(
                f"I2C display: {d.width}x{d.height} at bus={d.bus} addr=0x{d.address:02x}"
            )
        else:
            lines.append(f"{d.screen_type.value}: {d.width}x{d.height} via {d.driver}")

    return "\n".join(lines)


def check_display_access() -> dict:
    access = {
        "drm": False,
        "framebuffer": False,
        "i2c": False,
        "errors": [],
    }

    drm_path = Path("/dev/dri/card0")
    if drm_path.exists():
        if os.access(drm_path, os.R_OK | os.W_OK):
            access["drm"] = True
        else:
            access["errors"].append(f"No read/write access to {drm_path}")
    else:
        access["errors"].append("/dev/dri/card0 not found")

    fb_path = Path("/dev/fb0")
    if fb_path.exists():
        if os.access(fb_path, os.R_OK | os.W_OK):
            access["framebuffer"] = True
        else:
            access["errors"].append(f"No read/write access to {fb_path}")

    i2c_path = Path("/dev/i2c-1")
    if i2c_path.exists():
        if os.access(i2c_path, os.R_OK | os.W_OK):
            access["i2c"] = True
        else:
            access["errors"].append(f"No read/write access to {i2c_path}")

    return access


def check_drm_status() -> dict:
    status = {
        "available": False,
        "devices": [],
        "render_nodes": [],
        "driver": None,
        "errors": [],
    }

    dri_path = Path("/dev/dri")
    if not dri_path.exists():
        status["errors"].append("/dev/dri not found")
        return status

    for card in dri_path.glob("card*"):
        accessible = os.access(card, os.R_OK | os.W_OK)
        status["devices"].append(
            {
                "path": str(card),
                "accessible": accessible,
            }
        )
        if accessible:
            status["available"] = True

    for render in dri_path.glob("renderD*"):
        accessible = os.access(render, os.R_OK | os.W_OK)
        status["render_nodes"].append(
            {
                "path": str(render),
                "accessible": accessible,
            }
        )

    if status["available"]:
        try:
            result = subprocess.run(
                ["cat", "/sys/class/drm/card0/device/driver/module/drivers"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                status["driver"] = (
                    result.stdout.strip().split(":")[-1]
                    if ":" in result.stdout
                    else result.stdout.strip()
                )
        except Exception:
            pass

    return status
