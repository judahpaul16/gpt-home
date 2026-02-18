import logging
from typing import List, Optional, Tuple

from .base import BaseDisplay, DisplayInfo, ScreenType
from .detection import detect_displays

logger = logging.getLogger("display.factory")


class DisplayFactory:
    @staticmethod
    def create(info: DisplayInfo) -> Optional[BaseDisplay]:
        if info.screen_type == ScreenType.HDMI:
            return DisplayFactory._create_kmsdrm_display(info)
        elif info.screen_type == ScreenType.SPI_TFT:
            return DisplayFactory._create_fbdev_display(info)
        elif info.screen_type == ScreenType.I2C:
            return DisplayFactory._create_i2c_display(info)
        return None

    @staticmethod
    def _create_kmsdrm_display(info: DisplayInfo) -> Optional[BaseDisplay]:
        logger.debug("Creating KMSDRM display: %dx%d", info.width, info.height)
        try:
            from .drivers.kmsdrm import KmsdrmDisplay

            return KmsdrmDisplay(info)
        except Exception as e:
            logger.error("Failed to create KmsdrmDisplay: %s", e)
        return None

    @staticmethod
    def _create_fbdev_display(info: DisplayInfo) -> Optional[BaseDisplay]:
        if info.driver == "kmsdrm":
            logger.debug(
                "Creating KMSDRM display for TFT: %dx%d on %s",
                info.width,
                info.height,
                info.device_path,
            )
            try:
                from .drivers.kmsdrm import KmsdrmDisplay

                return KmsdrmDisplay(info)
            except Exception as e:
                logger.error("Failed to create KmsdrmDisplay for TFT: %s", e)
            return None

        logger.debug(
            "Creating framebuffer display: %dx%d on %s",
            info.width,
            info.height,
            info.device_path,
        )
        try:
            from .drivers.fbdev import FbdevDisplay

            return FbdevDisplay(info)
        except Exception as e:
            logger.error("Failed to create FbdevDisplay: %s", e)
        return None

    @staticmethod
    def _create_i2c_display(info: DisplayInfo) -> Optional[BaseDisplay]:
        try:
            from .drivers.i2c import I2COledDisplay

            return I2COledDisplay(info)
        except ImportError:
            return None

    @staticmethod
    def auto_detect() -> Optional[BaseDisplay]:
        displays = detect_displays()
        priority = [ScreenType.HDMI, ScreenType.SPI_TFT, ScreenType.I2C]

        for screen_type in priority:
            for info in displays:
                if info.screen_type == screen_type:
                    display = DisplayFactory.create(info)
                    if display:
                        return display
        return None

    @staticmethod
    def auto_detect_full_display() -> Optional[BaseDisplay]:
        displays = detect_displays()
        full_display_types = [ScreenType.HDMI, ScreenType.SPI_TFT]

        preferred_connector = DisplayFactory._get_cmdline_connector()
        if preferred_connector:
            for info in displays:
                if (
                    info.screen_type == ScreenType.HDMI
                    and info.connector == preferred_connector
                ):
                    display = DisplayFactory.create(info)
                    if display and display.supports_modes:
                        return display

        for screen_type in full_display_types:
            for info in displays:
                if info.screen_type == screen_type:
                    display = DisplayFactory.create(info)
                    if display and display.supports_modes:
                        return display
        return None

    @staticmethod
    def _get_cmdline_connector() -> Optional[str]:
        import re

        for path in ["/boot/firmware/cmdline.txt", "/boot/cmdline.txt"]:
            try:
                cmdline = open(path).read().strip()
                match = re.search(r"video=([^:]+):", cmdline)
                if match:
                    return match.group(1)
            except Exception:
                pass
        return None

    @staticmethod
    def detect_simple_display() -> Optional[BaseDisplay]:
        displays = detect_displays()

        for info in displays:
            if info.screen_type == ScreenType.I2C:
                display = DisplayFactory.create(info)
                if display and not display.supports_modes:
                    return display
        return None

    @staticmethod
    def detect_all_categorized() -> Tuple[Optional[BaseDisplay], Optional[BaseDisplay]]:
        full_display = DisplayFactory.auto_detect_full_display()
        simple_display = DisplayFactory.detect_simple_display()
        return (full_display, simple_display)

    @staticmethod
    def create_all() -> List[BaseDisplay]:
        displays = []
        detected = detect_displays()

        for info in detected:
            display = DisplayFactory.create(info)
            if display:
                displays.append(display)
        return displays

    @staticmethod
    def create_full_displays() -> List[BaseDisplay]:
        displays = []
        detected = detect_displays()

        for info in detected:
            if info.screen_type == ScreenType.I2C:
                continue
            display = DisplayFactory.create(info)
            if display and display.supports_modes:
                displays.append(display)
        return displays
