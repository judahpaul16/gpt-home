"""Color palette and utility classes for display rendering."""

import math
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from .base import Color


class Palette:
    """Standard color palette for display modes."""

    BG_DARK = Color(30, 35, 55)
    BG_MID = Color(40, 48, 75)
    BG_CARD = Color(55, 65, 100)
    BG_ELEVATED = Color(70, 82, 120)
    ACCENT_BLUE = Color(100, 140, 255)
    ACCENT_PURPLE = Color(180, 130, 255)
    ACCENT_CYAN = Color(80, 230, 255)
    ACCENT_GREEN = Color(70, 230, 170)
    ACCENT_ORANGE = Color(255, 170, 90)
    ACCENT_PINK = Color(255, 140, 200)
    SPOTIFY_GREEN = Color(30, 215, 96)
    TEXT_PRIMARY = Color(255, 255, 255)
    TEXT_SECONDARY = Color(200, 210, 230)
    TEXT_MUTED = Color(150, 165, 195)


class ScrollingText:
    """Handles Spotify-style scrolling text animation."""

    def __init__(
        self, text: str, max_width: int, font_size: int, char_width_ratio: float = 0.55
    ):
        self.text = text
        self.max_width = max_width
        self.font_size = font_size
        self.char_width = int(font_size * char_width_ratio)
        self.text_width = len(text) * self.char_width
        self.needs_scroll = self.text_width > max_width
        self.scroll_offset = 0.0
        self.scroll_speed = 50.0
        self.pause_time = 2.0
        self.pause_timer = self.pause_time
        self.scroll_direction = 1
        self.state = "pause_start"

    def update(self, dt: float) -> None:
        if not self.needs_scroll:
            return

        max_scroll = self.text_width - self.max_width + self.char_width * 2

        if self.state == "pause_start":
            self.pause_timer -= dt
            if self.pause_timer <= 0:
                self.state = "scrolling"
                self.scroll_direction = 1
        elif self.state == "scrolling":
            self.scroll_offset += self.scroll_speed * dt
            if self.scroll_offset >= max_scroll:
                self.scroll_offset = max_scroll
                self.state = "pause_end"
                self.pause_timer = self.pause_time
        elif self.state == "pause_end":
            self.pause_timer -= dt
            if self.pause_timer <= 0:
                self.state = "scrolling_back"
        elif self.state == "scrolling_back":
            self.scroll_offset -= self.scroll_speed * 1.5 * dt
            if self.scroll_offset <= 0:
                self.scroll_offset = 0
                self.state = "pause_start"
                self.pause_timer = self.pause_time

    def get_offset(self) -> int:
        return int(self.scroll_offset)

    def reset(self, new_text: str = None) -> None:
        if new_text is not None:
            self.text = new_text
            self.text_width = len(new_text) * self.char_width
            self.needs_scroll = self.text_width > self.max_width
        self.scroll_offset = 0.0
        self.pause_timer = self.pause_time
        self.state = "pause_start"


def lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation between a and b."""
    return a + (b - a) * min(1.0, max(0.0, t))


def ease_out_cubic(t: float) -> float:
    """Cubic ease-out function."""
    return 1.0 - pow(1.0 - min(1.0, max(0.0, t)), 3)


def ease_out_quad(t: float) -> float:
    """Quadratic ease-out function."""
    t = min(1.0, max(0.0, t))
    return 1.0 - (1.0 - t) * (1.0 - t)


def ease_in_out_sine(t: float) -> float:
    """Sine ease-in-out function."""
    return -(math.cos(math.pi * t) - 1) / 2
