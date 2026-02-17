import logging
import os
import re
import subprocess
from pathlib import Path
from typing import List, Optional

from .base import DisplayInfo, ScreenType

logger = logging.getLogger("display.detection")

_logged_no_displays = False

_TFT_OVERLAY_NAMES = ["piscreen", "waveshare35a", "tft35a", "pitft35"]


def _read_hardware_mode() -> Optional[str]:
    for path in ["/boot/firmware/config.txt", "/boot/config.txt"]:
        if not Path(path).exists():
            continue
        try:
            has_tft = False
            has_vc4 = False
            with open(path) as f:
                for line in f:
                    stripped = line.strip()
                    if stripped.startswith("#"):
                        continue
                    if any(
                        f"dtoverlay={name}" in stripped for name in _TFT_OVERLAY_NAMES
                    ):
                        has_tft = True
                    if (
                        "dtoverlay=vc4-kms-v3d" in stripped
                        or "dtoverlay=vc4-fkms-v3d" in stripped
                    ):
                        has_vc4 = True
            if has_tft and has_vc4:
                return "conflict"
            if has_tft:
                return "tft"
            return "hdmi"
        except Exception:
            pass
    return None


def detect_displays() -> List[DisplayInfo]:
    displays = []

    drm_display = _detect_drm()
    if drm_display:
        displays.append(drm_display)

    drm_tft_display = _detect_drm_tft()
    if drm_tft_display:
        displays.append(drm_tft_display)
    else:
        spi_tft_display = _detect_spi_tft()
        if spi_tft_display:
            displays.append(spi_tft_display)

    i2c_displays = _detect_i2c_oled()
    displays.extend(i2c_displays)

    hw_mode = _read_hardware_mode()
    if hw_mode == "tft":
        tft_displays = [d for d in displays if d.screen_type == ScreenType.SPI_TFT]
        if tft_displays:
            displays = tft_displays + [
                d for d in displays if d.screen_type == ScreenType.I2C
            ]
    elif hw_mode == "hdmi":
        displays = [d for d in displays if d.screen_type != ScreenType.SPI_TFT]

    global _logged_no_displays
    if not displays:
        if not _logged_no_displays:
            _log_detection_diagnostics()
            _logged_no_displays = True
    else:
        _logged_no_displays = False

    return displays


def _log_detection_diagnostics() -> None:
    """One-shot diagnostics when no displays are found."""
    parts = []
    dri = Path("/dev/dri")
    if dri.exists():
        parts.append(f"/dev/dri: {[c.name for c in sorted(dri.iterdir())]}")
    else:
        parts.append("/dev/dri: absent")

    for fb in ["fb0", "fb1"]:
        p = Path(f"/dev/{fb}")
        if p.exists():
            rw = os.access(p, os.R_OK | os.W_OK)
            parts.append(f"/dev/{fb}: exists (rw={rw})")

    drm_class = Path("/sys/class/drm")
    if drm_class.exists():
        connectors = [c.name for c in drm_class.iterdir() if "-" in c.name]
        parts.append(f"DRM connectors: {connectors}")

    fb_class = Path("/sys/class/graphics")
    if fb_class.exists():
        fbs = []
        for fb_dir in fb_class.iterdir():
            if fb_dir.name.startswith("fb"):
                name_file = fb_dir / "name"
                name = name_file.read_text().strip() if name_file.exists() else "?"
                fbs.append(f"{fb_dir.name}={name}")
        if fbs:
            parts.append(f"Framebuffers: {fbs}")

    logger.warning("No displays detected. %s", "; ".join(parts))


def detect_full_displays() -> List[DisplayInfo]:
    all_displays = detect_displays()
    return [d for d in all_displays if d.screen_type != ScreenType.I2C]


def detect_simple_displays() -> List[DisplayInfo]:
    all_displays = detect_displays()
    return [d for d in all_displays if d.screen_type == ScreenType.I2C]


def _detect_drm() -> Optional[DisplayInfo]:
    dri_path = Path("/dev/dri")
    drm_class = Path("/sys/class/drm")

    if dri_path.exists() and drm_class.exists():
        hdmi_cards = set()
        for connector in drm_class.iterdir():
            if "hdmi" in connector.name.lower():
                card_match = re.match(r"(card\d+)", connector.name)
                if card_match:
                    hdmi_cards.add(card_match.group(1))

        for card_name in sorted(hdmi_cards):
            card_path = dri_path / card_name
            if card_path.exists() and os.access(card_path, os.R_OK | os.W_OK):
                width, height = _get_drm_resolution(card_path)
                return DisplayInfo(
                    screen_type=ScreenType.HDMI,
                    width=width,
                    height=height,
                    device_path=str(card_path),
                    driver="kmsdrm",
                )

    hdmi_connector = _check_hdmi_connected()
    if hdmi_connector:
        width, height = _get_drm_resolution_from_sysfs()
        logger.debug(
            "HDMI connected via sysfs (%s): %dx%d", hdmi_connector, width, height
        )
        return DisplayInfo(
            screen_type=ScreenType.HDMI,
            width=width,
            height=height,
            device_path="/dev/dri/card0",
            driver="kmsdrm",
        )

    return None


def _detect_drm_tft() -> Optional[DisplayInfo]:
    drm_class = Path("/sys/class/drm")
    if not drm_class.exists():
        return None

    for connector in drm_class.iterdir():
        name = connector.name.lower()

        if "-" not in connector.name:
            continue
        if "hdmi" in name:
            continue
        if not any(x in name for x in ["spi", "panel", "unknown"]):
            continue

        status_file = connector / "status"
        if status_file.exists():
            try:
                status = status_file.read_text().strip()
                if status != "connected":
                    continue
            except Exception:
                pass

        modes_file = connector / "modes"
        if not modes_file.exists():
            continue

        try:
            modes = modes_file.read_text().strip()
            if not modes:
                continue

            first_mode = modes.split("\n")[0]
            match = re.search(r"(\d+)x(\d+)", first_mode)
            if match:
                w, h = int(match.group(1)), int(match.group(2))

                if w > 800 or h > 600:
                    continue

                card_match = re.match(r"(card\d+)", connector.name)
                if card_match:
                    card_path = f"/dev/dri/{card_match.group(1)}"
                else:
                    card_path = "/dev/dri/card1"

                if not Path(card_path).exists():
                    continue
                if not os.access(card_path, os.R_OK | os.W_OK):
                    continue

                logger.debug(
                    "DRM TFT detected: %dx%d at %s (connector: %s)",
                    w,
                    h,
                    card_path,
                    connector.name,
                )
                return DisplayInfo(
                    screen_type=ScreenType.SPI_TFT,
                    width=w,
                    height=h,
                    device_path=card_path,
                    driver="kmsdrm",
                )
        except Exception:
            pass

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


def _detect_spi_tft() -> Optional[DisplayInfo]:
    for fb_name in ["fb1", "fb0"]:
        fb_path = Path(f"/dev/{fb_name}")

        if not fb_path.exists():
            continue
        if not os.access(fb_path, os.R_OK | os.W_OK):
            continue

        width, height = _get_fb_resolution(fb_path)

        if width >= 800 or height >= 600:
            continue

        if width > 0 and height > 0:
            logger.debug("SPI TFT detected at %s: %dx%d", fb_path, width, height)
            return DisplayInfo(
                screen_type=ScreenType.SPI_TFT,
                width=width,
                height=height,
                device_path=str(fb_path),
                driver="fbdev",
            )

    fbtft_path = Path("/sys/class/graphics")
    if fbtft_path.exists():
        for fb_dir in fbtft_path.iterdir():
            if not fb_dir.name.startswith("fb"):
                continue
            name_file = fb_dir / "name"
            if name_file.exists():
                try:
                    name = name_file.read_text().strip()
                    if any(
                        x in name.lower()
                        for x in ["ili", "tft", "st7", "flexfb", "waveshare"]
                    ):
                        fb_path = Path(f"/dev/{fb_dir.name}")
                        if fb_path.exists() and os.access(fb_path, os.R_OK | os.W_OK):
                            width, height = _get_fb_resolution(fb_path)
                            if width > 0 and height > 0:
                                logger.debug(
                                    "fbtft detected: %s at %s: %dx%d",
                                    name,
                                    fb_path,
                                    width,
                                    height,
                                )
                                return DisplayInfo(
                                    screen_type=ScreenType.SPI_TFT,
                                    width=width,
                                    height=height,
                                    device_path=str(fb_path),
                                    driver="fbdev",
                                )
                except Exception:
                    pass

    return None


def _get_fb_resolution(fb_path: Path) -> tuple[int, int]:
    """Get framebuffer resolution from sysfs or fbset."""
    fb_name = fb_path.name

    # Try sysfs first
    sysfs_path = Path(f"/sys/class/graphics/{fb_name}")
    if sysfs_path.exists():
        # Try virtual_size
        virtual_size = sysfs_path / "virtual_size"
        if virtual_size.exists():
            try:
                content = virtual_size.read_text().strip()
                if "," in content:
                    w, h = content.split(",")
                    return int(w), int(h)
            except Exception:
                pass

        # Try modes
        modes_file = sysfs_path / "modes"
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

    # Try fbset command
    try:
        result = subprocess.run(
            ["fbset", "-fb", str(fb_path), "-s"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            # Parse geometry line: geometry 480 320 480 320 16
            match = re.search(r"geometry\s+(\d+)\s+(\d+)", result.stdout)
            if match:
                return int(match.group(1)), int(match.group(2))
    except Exception:
        pass

    # Default for common 3.5" TFT displays
    return 480, 320


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
