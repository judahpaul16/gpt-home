import logging
from typing import List, Optional, Tuple

from .base import BaseDisplay, DisplayInfo, ScreenType
from .detection import detect_displays

logger = logging.getLogger(__name__)


class DisplayFactory:
    @staticmethod
    def create(info: DisplayInfo) -> Optional[BaseDisplay]:
        if (
            info.screen_type == ScreenType.HDMI
            or info.screen_type == ScreenType.SPI_TFT
        ):
            return DisplayFactory._create_kmsdrm_display(info)
        elif info.screen_type == ScreenType.I2C:
            return DisplayFactory._create_i2c_display(info)
        return None

    @staticmethod
    def _create_kmsdrm_display(info: DisplayInfo) -> Optional[BaseDisplay]:
        logger.info(f"Creating KMSDRM display: {info.width}x{info.height}")
        try:
            from .drivers.kmsdrm import KmsdrmDisplay

            display = KmsdrmDisplay(info)
            return display
        except ImportError as e:
            logger.error(f"Failed to import KmsdrmDisplay: {e}")
        except Exception as e:
            logger.error(f"Failed to create KmsdrmDisplay: {e}")
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

        for screen_type in full_display_types:
            for info in displays:
                if info.screen_type == screen_type:
                    display = DisplayFactory.create(info)
                    if display and display.supports_modes:
                        return display
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
