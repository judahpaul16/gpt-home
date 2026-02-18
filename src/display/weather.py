"""Weather rendering utilities and icons."""

import logging
import math
import os
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

import aiohttp

from .base import BaseDisplay, Color

logger = logging.getLogger(__name__)


def draw_weather_gradient(
    d: BaseDisplay, top_color: Color, bottom_color: Color, steps: int = 32
) -> None:
    """Draw a smooth vertical gradient for weather backgrounds."""
    step_h = d.height // steps
    for i in range(steps):
        t = i / (steps - 1)
        r = int(top_color.r + (bottom_color.r - top_color.r) * t)
        g = int(top_color.g + (bottom_color.g - top_color.g) * t)
        b = int(top_color.b + (bottom_color.b - top_color.b) * t)
        y = i * step_h
        h = step_h + 1 if i < steps - 1 else d.height - y
        d.fill_rect_sync(0, y, d.width, h, Color(r, g, b))


def draw_cloud(d: BaseDisplay, x: int, y: int, w: int) -> None:
    """Draw a basic cloud shape."""
    color = Color(235, 240, 248)
    shadow = Color(200, 210, 220)
    h = w // 2
    d.draw_circle_sync(x + w // 4, y + 4, w // 4, shadow, filled=True)
    d.draw_circle_sync(x + w // 2, y - h // 3 + 4, w // 3, shadow, filled=True)
    d.draw_circle_sync(x + w * 3 // 4, y + 4, w // 4, shadow, filled=True)
    d.draw_circle_sync(x + w // 4, y, w // 4, color, filled=True)
    d.draw_circle_sync(x + w // 2, y - h // 3, w // 3, color, filled=True)
    d.draw_circle_sync(x + w * 3 // 4, y, w // 4, color, filled=True)
    d.fill_rect_sync(x + w // 4, y, w // 2, h // 2, color)


def draw_cloud_fancy(
    d: BaseDisplay, x: int, y: int, w: int, opacity: float = 1.0
) -> None:
    """Draw a fancy cloud with highlights and shadows."""
    base_r, base_g, base_b = 225, 235, 250
    shadow_r, shadow_g, shadow_b = 175, 190, 210

    color = Color(
        int(base_r * opacity),
        int(base_g * opacity),
        int(base_b * opacity),
    )
    shadow = Color(
        int(shadow_r * opacity * 0.7),
        int(shadow_g * opacity * 0.7),
        int(shadow_b * opacity * 0.7),
    )
    highlight = Color(
        int(255 * opacity),
        int(255 * opacity),
        int(255 * opacity),
    )

    h = w // 2
    r1 = max(4, w // 4)
    r2 = max(5, w // 3)
    r3 = max(3, w // 5)

    d.draw_circle_sync(x + w // 4 + 2, y + 3, r1, shadow, filled=True)
    d.draw_circle_sync(x + w // 2 + 2, y - h // 4 + 3, r2, shadow, filled=True)
    d.draw_circle_sync(x + w * 3 // 4 + 2, y + 3, r3, shadow, filled=True)

    d.draw_circle_sync(x + w // 5, y, r1, color, filled=True)
    d.draw_circle_sync(x + w // 2, y - h // 4, r2, color, filled=True)
    d.draw_circle_sync(x + w * 4 // 5, y, r1, color, filled=True)
    d.draw_circle_sync(x + w // 3, y + h // 8, r3, color, filled=True)
    d.draw_circle_sync(x + w * 2 // 3, y + h // 8, r3, color, filled=True)

    highlight_r = max(2, w // 8)
    d.draw_circle_sync(
        x + w // 2 - 3, y - h // 4 - 3, highlight_r, highlight, filled=True
    )


def draw_sun(d: BaseDisplay, x: int, y: int, phase: float) -> None:
    """Draw an animated sun with rays."""
    radius = d.scale_x(38)
    pulse = 1.0 + math.sin(phase * 0.5) * 0.01

    # Draw rays first (behind sun body)
    for i in range(12):
        angle = (i / 12) * math.pi * 2 + phase * 0.05
        ray_len = d.scale_x(22) + math.sin(phase * 0.4 + i * 0.5) * d.scale_x(2)
        start_r = radius + d.scale_x(10)
        end_r = start_r + ray_len
        x1 = x + int(math.cos(angle) * start_r)
        y1 = y + int(math.sin(angle) * start_r)
        x2 = x + int(math.cos(angle) * end_r)
        y2 = y + int(math.sin(angle) * end_r)
        d.draw_line_sync(x1, y1, x2, y2, Color(255, 205, 65), 3)

    # Draw sun body
    d.draw_circle_sync(x, y, int(radius * pulse), Color(255, 195, 55), filled=True)
    d.draw_circle_sync(
        x, y, int(radius * pulse * 0.78), Color(255, 225, 95), filled=True
    )


def draw_weather_icon(
    d: BaseDisplay, condition: str, x: int, y: int, size: int, phase: float
) -> None:
    """Draw a weather icon based on condition."""
    cond = condition.lower()
    if "clear" in cond or "sun" in cond:
        pulse = 1.0 + math.sin(phase * 2) * 0.1
        r = int(size * 0.4 * pulse)
        d.draw_circle_sync(x + size // 2, y + size // 2, r, Color(255, 200, 50), True)
        for i in range(8):
            angle = (i / 8) * math.pi * 2 + phase * 0.5
            cx, cy = x + size // 2, y + size // 2
            start_r = r + 4
            end_r = r + 10
            x1 = int(cx + math.cos(angle) * start_r)
            y1 = int(cy + math.sin(angle) * start_r)
            x2 = int(cx + math.cos(angle) * end_r)
            y2 = int(cy + math.sin(angle) * end_r)
            d.draw_line_sync(x1, y1, x2, y2, Color(255, 200, 50), 2)
    elif "cloud" in cond:
        draw_cloud(d, x, y + size // 4, size)
    elif "rain" in cond or "drizzle" in cond:
        draw_cloud(d, x, y + size // 6, int(size * 0.8))
        for i in range(3):
            drop_x = x + size // 4 + i * (size // 4)
            drop_y = y + size // 2 + int(math.sin(phase * 3 + i) * 5)
            d.draw_line_sync(
                drop_x, drop_y, drop_x, drop_y + size // 5, Color(100, 160, 220), 2
            )
    elif "snow" in cond:
        draw_cloud(d, x, y + size // 6, int(size * 0.8))
        for i in range(3):
            flake_x = x + size // 4 + i * (size // 4)
            flake_y = y + size // 2 + int(math.sin(phase * 2 + i) * 4)
            d.draw_circle_sync(flake_x, flake_y, 3, Color(220, 230, 255), True)
    elif "thunder" in cond:
        draw_cloud(d, x, y + size // 6, int(size * 0.8))
        bolt_x = x + size // 2
        bolt_y = y + size // 2
        if int(phase * 10) % 20 < 3:
            d.draw_line_sync(
                bolt_x, bolt_y, bolt_x - 5, bolt_y + 10, Color(255, 255, 100), 2
            )
            d.draw_line_sync(
                bolt_x - 5,
                bolt_y + 10,
                bolt_x + 3,
                bolt_y + 12,
                Color(255, 255, 100),
                2,
            )
            d.draw_line_sync(
                bolt_x + 3,
                bolt_y + 12,
                bolt_x - 2,
                bolt_y + 22,
                Color(255, 255, 100),
                2,
            )
    else:
        draw_cloud(d, x, y + size // 4, size)


def draw_weather_icon_fancy(
    d: BaseDisplay, condition: str, x: int, y: int, size: int, phase: float
) -> None:
    """Draw a fancy animated weather icon."""
    cond = condition.lower()
    cx = x + size // 2
    cy = y + size // 2

    if "clear" in cond or "sun" in cond:
        pulse = 1.0 + math.sin(phase * 0.8) * 0.02
        sun_r = int(size * 0.3 * pulse)
        for i in range(8):
            angle = (i / 8) * math.pi * 2 + phase * 0.15
            ray_pulse = 1.0 + math.sin(phase * 1.0 + i * 0.8) * 0.08
            start_r = sun_r + 3
            end_r = sun_r + int(10 * ray_pulse)
            x1 = int(cx + math.cos(angle) * start_r)
            y1 = int(cy + math.sin(angle) * start_r)
            x2 = int(cx + math.cos(angle) * end_r)
            y2 = int(cy + math.sin(angle) * end_r)
            d.draw_line_sync(x1, y1, x2, y2, Color(255, 210, 80), 2)
        d.draw_circle_sync(cx, cy, sun_r, Color(255, 200, 60), True)
        d.draw_circle_sync(cx, cy, int(sun_r * 0.7), Color(255, 230, 110), True)

    elif "fog" in cond or "mist" in cond or "haze" in cond:
        for i in range(8):
            px = x + size // 2 + int(math.sin(phase * 0.7 + i * 1.3) * (size * 0.4))
            py = y + size // 4 + (i % 4) * (size // 5)
            drift_x = int(math.sin(phase * 0.5 + i * 0.8) * 8)
            drift_y = int(math.cos(phase * 0.4 + i * 0.6) * 3)
            brightness = 0.7 + 0.25 * math.sin(phase * 0.6 + i * 0.9)
            particle_r = max(3, int((size // 8) * (0.6 + 0.4 * math.sin(i * 0.7))))
            fog_color = Color(
                min(255, int(200 + 50 * brightness)),
                min(255, int(210 + 40 * brightness)),
                min(255, int(220 + 30 * brightness)),
            )
            d.draw_circle_sync(px + drift_x, py + drift_y, particle_r, fog_color, True)

        for i in range(3):
            wisp_y = y + size // 3 + i * (size // 5)
            wave_offset = math.sin(phase * 0.9 + i * 1.1) * 10
            brightness = 0.7 + 0.2 * math.sin(phase * 0.7 + i * 0.5)
            wisp_color = Color(
                min(255, int(180 + 70 * brightness)),
                min(255, int(190 + 60 * brightness)),
                min(255, int(200 + 50 * brightness)),
            )
            wisp_width = int(size * 0.7) - (i * 8)
            wisp_x = x + (size - wisp_width) // 2 + int(wave_offset)
            d.draw_line_sync(wisp_x, wisp_y, wisp_x + wisp_width, wisp_y, wisp_color, 2)

    elif "cloud" in cond:
        cloud_w = int(size * 0.85)
        cloud_y = y + size // 4
        bob = int(math.sin(phase * 1.5) * 3)
        draw_cloud_fancy(d, x, cloud_y + bob, cloud_w, 1.0)

    elif "rain" in cond or "drizzle" in cond:
        cloud_w = int(size * 0.75)
        cloud_y = y + size // 8
        draw_cloud_fancy(d, x + size // 10, cloud_y, cloud_w, 0.8)

        for i in range(6):
            drop_phase = (phase * 5 + i * 0.9) % 1.0
            drop_x = x + size // 6 + i * (size // 7) + int(math.sin(i * 1.2) * 3)
            drop_y = y + size // 2 - 5 + int(drop_phase * (size // 2))
            drop_len = 8 + int(drop_phase * 6)
            drop_alpha = 0.4 + 0.5 * (1.0 - drop_phase)
            drop_color = Color(
                int(100 * drop_alpha),
                int(170 * drop_alpha),
                min(255, int(240 * drop_alpha)),
            )
            d.draw_line_sync(
                drop_x, drop_y, drop_x + 2, drop_y + drop_len, drop_color, 2
            )
            if drop_phase > 0.85:
                splash_y = y + size - 5
                splash_alpha = (drop_phase - 0.85) * 6
                splash_color = Color(
                    int(120 * splash_alpha),
                    int(180 * splash_alpha),
                    min(255, int(230 * splash_alpha)),
                )
                d.draw_circle_sync(drop_x + 1, splash_y, 2, splash_color, True)

    elif "snow" in cond:
        cloud_w = int(size * 0.75)
        cloud_y = y + size // 8
        draw_cloud_fancy(d, x + size // 10, cloud_y, cloud_w, 0.85)

        for i in range(6):
            flake_phase = (phase * 1.5 + i * 1.1) % 1.0
            wobble_x = math.sin(phase * 2 + i * 1.5) * 6
            wobble_y = math.cos(phase * 1.8 + i * 0.9) * 2
            flake_x = x + size // 6 + i * (size // 7) + int(wobble_x)
            flake_y = y + size // 2 - 8 + int(flake_phase * (size // 2)) + int(wobble_y)
            flake_size = max(2, 3 + int(math.sin(i * 0.8) * 2))
            flake_alpha = 0.5 + 0.4 * math.sin(phase * 3 + i)
            flake_color = Color(
                min(255, int(240 * flake_alpha)),
                min(255, int(245 * flake_alpha)),
                min(255, int(255 * flake_alpha)),
            )
            d.draw_circle_sync(flake_x, flake_y, flake_size, flake_color, True)
            if flake_size > 2:
                d.draw_circle_sync(
                    flake_x, flake_y, flake_size - 1, Color(255, 255, 255), True
                )

    elif "thunder" in cond or "storm" in cond:
        cloud_w = int(size * 0.8)
        cloud_y = y + size // 8
        cloud_color_base = 70 + int(20 * math.sin(phase * 8))
        r1 = max(4, cloud_w // 4)
        r2 = max(5, cloud_w // 3)
        d.draw_circle_sync(
            x + cloud_w // 4,
            cloud_y,
            r1,
            Color(cloud_color_base, cloud_color_base + 5, cloud_color_base + 20),
            True,
        )
        d.draw_circle_sync(
            x + cloud_w // 2,
            cloud_y - cloud_w // 8,
            r2,
            Color(cloud_color_base + 10, cloud_color_base + 15, cloud_color_base + 30),
            True,
        )
        d.draw_circle_sync(
            x + cloud_w * 3 // 4,
            cloud_y,
            r1,
            Color(cloud_color_base + 5, cloud_color_base + 10, cloud_color_base + 25),
            True,
        )

        flash_on = int(phase * 12) % 7 < 2
        if flash_on:
            bolt_x = x + size // 2
            bolt_y = y + size // 2 - 5
            glow_color = Color(255, 255, 200)
            d.draw_circle_sync(bolt_x - 2, bolt_y + 8, 8, Color(80, 80, 50), True)
            d.draw_line_sync(bolt_x, bolt_y, bolt_x - 6, bolt_y + 12, glow_color, 3)
            d.draw_line_sync(
                bolt_x - 6, bolt_y + 12, bolt_x + 2, bolt_y + 14, glow_color, 3
            )
            d.draw_line_sync(
                bolt_x + 2, bolt_y + 14, bolt_x - 4, bolt_y + 26, glow_color, 3
            )
            d.draw_line_sync(
                bolt_x - 1, bolt_y, bolt_x - 7, bolt_y + 12, Color(255, 255, 255), 2
            )
            d.draw_line_sync(
                bolt_x - 7,
                bolt_y + 12,
                bolt_x + 1,
                bolt_y + 14,
                Color(255, 255, 255),
                2,
            )
            d.draw_line_sync(
                bolt_x + 1,
                bolt_y + 14,
                bolt_x - 5,
                bolt_y + 26,
                Color(255, 255, 255),
                2,
            )
    else:
        cloud_w = int(size * 0.8)
        cloud_y = y + size // 4
        bob = int(math.sin(phase * 1.2) * 2)
        draw_cloud_fancy(d, x, cloud_y + bob, cloud_w, 0.9)


def draw_weather_icon_mini(
    d: BaseDisplay, condition: str, x: int, y: int, size: int, phase: float
) -> None:
    """Draw a mini weather icon for forecast display."""
    cond = condition.lower()

    if "clear" in cond or "sun" in cond:
        pulse = 1.0 + math.sin(phase * 3) * 0.08
        r = max(4, int(size * 0.32 * pulse))
        d.draw_circle_sync(x, y, r + 2, Color(255, 220, 100), True)
        d.draw_circle_sync(x, y, r, Color(255, 200, 60), True)
        for i in range(6):
            angle = (i / 6) * math.pi * 2 + phase * 0.5
            x1 = int(x + math.cos(angle) * (r + 2))
            y1 = int(y + math.sin(angle) * (r + 2))
            x2 = int(x + math.cos(angle) * (r + 5))
            y2 = int(y + math.sin(angle) * (r + 5))
            d.draw_line_sync(x1, y1, x2, y2, Color(255, 210, 80), 1)

    elif "fog" in cond or "mist" in cond or "haze" in cond:
        for i in range(5):
            px = x + int(math.sin(phase * 0.8 + i * 1.5) * (size * 0.3))
            py = y - size // 8 + (i % 3) * (size // 6)
            drift_x = int(math.sin(phase * 0.6 + i * 0.7) * 4)
            drift_y = int(math.cos(phase * 0.5 + i * 0.5) * 2)
            brightness = 0.7 + 0.25 * math.sin(phase * 0.7 + i * 0.8)
            particle_r = max(2, int((size // 10) * (0.5 + 0.5 * math.sin(i * 0.9))))
            fog_color = Color(
                min(255, int(200 + 55 * brightness)),
                min(255, int(210 + 45 * brightness)),
                min(255, int(220 + 35 * brightness)),
            )
            d.draw_circle_sync(px + drift_x, py + drift_y, particle_r, fog_color, True)

        for i in range(3):
            wisp_y = y - size // 6 + i * (size // 5)
            wave_offset = math.sin(phase * 1.0 + i * 0.8) * 3
            fade = 1.0 - (i * 0.1)
            brightness = (0.7 + 0.2 * math.sin(phase * 0.8 + i * 0.4)) * fade
            wisp_color = Color(
                min(255, int(180 + 70 * brightness)),
                min(255, int(190 + 60 * brightness)),
                min(255, int(200 + 50 * brightness)),
            )
            wisp_width = size // 3 - (i * 2)
            d.draw_line_sync(
                x - wisp_width // 2 + int(wave_offset),
                wisp_y,
                x + wisp_width // 2 + int(wave_offset),
                wisp_y,
                wisp_color,
                1,
            )

    elif "cloud" in cond:
        r = max(3, size // 5)
        bob = int(math.sin(phase * 1.5) * 1)
        d.draw_circle_sync(x - r + 1, y + bob + 1, r, Color(180, 190, 205), True)
        d.draw_circle_sync(
            x + 1, y - r // 2 + bob + 1, int(r * 1.1), Color(190, 200, 215), True
        )
        d.draw_circle_sync(x + r + 1, y + bob + 1, r, Color(180, 190, 205), True)
        d.draw_circle_sync(x - r, y + bob, r, Color(220, 230, 245), True)
        d.draw_circle_sync(
            x, y - r // 2 + bob, int(r * 1.1), Color(235, 242, 255), True
        )
        d.draw_circle_sync(x + r, y + bob, r, Color(220, 230, 245), True)

    elif "rain" in cond or "drizzle" in cond:
        r = max(3, size // 6)
        d.draw_circle_sync(x - r, y - r, r, Color(175, 190, 210), True)
        d.draw_circle_sync(x + r // 2, y - r, int(r * 1.1), Color(185, 200, 220), True)
        for i in range(3):
            drop_phase = (phase * 4 + i * 0.8) % 1.0
            drop_x = x - r + i * r
            drop_y = y - 2 + int(drop_phase * 10)
            drop_alpha = 0.5 + 0.4 * (1.0 - drop_phase)
            drop_color = Color(
                int(100 * drop_alpha),
                int(170 * drop_alpha),
                min(255, int(235 * drop_alpha)),
            )
            d.draw_line_sync(drop_x, drop_y, drop_x, drop_y + 4, drop_color, 1)

    elif "snow" in cond:
        r = max(3, size // 6)
        d.draw_circle_sync(x - r, y - r, r, Color(200, 215, 235), True)
        d.draw_circle_sync(x + r // 2, y - r, int(r * 1.1), Color(215, 228, 248), True)
        for i in range(3):
            flake_phase = (phase * 2 + i * 0.9) % 1.0
            wobble = math.sin(phase * 2.5 + i * 1.2) * 3
            flake_x = x - r + i * r + int(wobble)
            flake_y = y - 2 + int(flake_phase * 9)
            flake_alpha = 0.6 + 0.35 * math.sin(phase * 3 + i)
            flake_color = Color(
                min(255, int(245 * flake_alpha)),
                min(255, int(250 * flake_alpha)),
                min(255, int(255 * flake_alpha)),
            )
            d.draw_circle_sync(flake_x, flake_y, 2, flake_color, True)

    elif "thunder" in cond or "storm" in cond:
        r = max(3, size // 6)
        flash = int(phase * 10) % 6 < 2
        cloud_bright = 100 if flash else 85
        d.draw_circle_sync(
            x - r,
            y - r,
            r,
            Color(cloud_bright - 15, cloud_bright - 10, cloud_bright + 10),
            True,
        )
        d.draw_circle_sync(
            x + r // 2,
            y - r,
            int(r * 1.1),
            Color(cloud_bright - 5, cloud_bright, cloud_bright + 20),
            True,
        )
        if flash:
            d.draw_line_sync(x, y, x - 2, y + 5, Color(255, 255, 180), 1)
            d.draw_line_sync(x - 2, y + 5, x + 1, y + 6, Color(255, 255, 180), 1)
            d.draw_line_sync(x + 1, y + 6, x - 1, y + 10, Color(255, 255, 180), 1)
    else:
        r = max(3, size // 5)
        bob = int(math.sin(phase * 1.2) * 1)
        d.draw_circle_sync(x, y + bob, r, Color(190, 205, 225), True)


def get_weather_colors(condition: str, hour: int) -> tuple:
    """Get appropriate colors based on weather condition and time of day."""
    cond = condition.lower()
    is_night = hour < 6 or hour >= 20
    is_dawn = 6 <= hour < 8
    is_dusk = 18 <= hour < 20
    is_golden_hour = is_dawn or is_dusk

    if "clear" in cond or "sun" in cond:
        if is_night:
            top_color = Color(8, 12, 35)
            bottom_color = Color(25, 35, 70)
            accent_color = Color(100, 120, 200)
        elif is_golden_hour:
            top_color = Color(255, 140, 80)
            bottom_color = Color(255, 200, 140)
            accent_color = Color(255, 220, 180)
        else:
            top_color = Color(45, 130, 220)
            bottom_color = Color(135, 200, 255)
            accent_color = Color(255, 255, 255)
    elif "rain" in cond or "drizzle" in cond:
        top_color = Color(35, 45, 60)
        bottom_color = Color(55, 70, 90)
        accent_color = Color(100, 150, 200)
    elif "cloud" in cond:
        if is_night:
            top_color = Color(25, 30, 50)
            bottom_color = Color(45, 55, 80)
            accent_color = Color(140, 160, 200)
        else:
            top_color = Color(90, 110, 140)
            bottom_color = Color(140, 165, 200)
            accent_color = Color(200, 215, 240)
    elif "snow" in cond:
        top_color = Color(180, 195, 220)
        bottom_color = Color(220, 235, 255)
        accent_color = Color(255, 255, 255)
    elif "thunder" in cond:
        top_color = Color(20, 20, 35)
        bottom_color = Color(40, 40, 60)
        accent_color = Color(255, 255, 150)
    else:
        top_color = Color(30, 50, 80)
        bottom_color = Color(60, 90, 130)
        accent_color = Color(150, 180, 220)

    return top_color, bottom_color, accent_color, is_night


def wmo_code_to_condition(code: int) -> str:
    """Convert WMO weather code to simple condition string."""
    if code == 0:
        return "Clear"
    elif code in (1, 2, 3):
        return "Cloudy"
    elif code in (45, 48):
        return "Fog"
    elif code in (51, 53, 55, 56, 57):
        return "Drizzle"
    elif code in (61, 63, 65, 66, 67, 80, 81, 82):
        return "Rain"
    elif code in (71, 73, 75, 77, 85, 86):
        return "Snow"
    elif code in (95, 96, 99):
        return "Thunderstorm"
    else:
        return "Clear"


async def fetch_weather_data(
    location: Optional[str] = None,
    on_data: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    """Fetch weather data from APIs.

    Args:
        location: Optional location string to geocode
        on_data: Optional callback to receive the data

    Returns:
        Weather data dictionary
    """
    default_data = {
        "temperature": 70,
        "condition": "Clear",
        "location": "Unknown",
        "high": 75,
        "low": 65,
        "forecast": [],
    }

    try:
        try:
            from src.common import load_settings
        except ImportError:
            from common import load_settings

        settings = load_settings()
        lat = None
        lon = None
        city = ""

        if location:
            city = location
            try:
                async with aiohttp.ClientSession() as session:
                    geo_response = await session.get(
                        f"https://nominatim.openstreetmap.org/search?q={location}&format=json",
                        headers={"User-Agent": "GPT-Home/1.0"},
                        timeout=5,
                    )
                    if geo_response.status == 200:
                        geo_data = await geo_response.json()
                        if geo_data:
                            lat = float(geo_data[0]["lat"])
                            lon = float(geo_data[0]["lon"])
            except Exception as geo_err:
                logger.debug(f"Weather: Geocoding failed for {location}: {geo_err}")

        if not lat or not lon:
            lat = settings.get("lat")
            lon = settings.get("lon")
            city = settings.get("city", "") or city

        if not lat or not lon:
            try:
                async with aiohttp.ClientSession() as session:
                    geo_response = await session.get(
                        "http://ip-api.com/json/?fields=lat,lon,city", timeout=5
                    )
                    if geo_response.status == 200:
                        geo_data = await geo_response.json()
                        lat = geo_data.get("lat")
                        lon = geo_data.get("lon")
                        if not city:
                            city = geo_data.get("city", "")
            except Exception as geo_err:
                logger.debug(f"Weather: IP geolocation failed: {geo_err}")

        if not lat or not lon:
            logger.warning("Weather: Could not determine location")
            if on_data:
                on_data(default_data)
            return default_data

        api_key = os.getenv("OPEN_WEATHER_API_KEY")
        async with aiohttp.ClientSession() as session:
            # Try OpenWeatherMap first if API key is set
            if api_key:
                try:
                    response = await session.get(
                        f"https://api.openweathermap.org/data/3.0/onecall?"
                        f"lat={lat}&lon={lon}&appid={api_key}&units=imperial"
                        f"&exclude=minutely,hourly,alerts",
                        timeout=10,
                    )
                    if response.status == 200:
                        data = await response.json()
                        current = data.get("current", {})
                        weather_info = current.get("weather", [{}])[0]
                        daily = data.get("daily", [])

                        # Build forecast from daily data
                        forecast = []
                        day_names = [
                            "Sun",
                            "Mon",
                            "Tue",
                            "Wed",
                            "Thu",
                            "Fri",
                            "Sat",
                        ]
                        for i, day_data in enumerate(daily[:7]):
                            dt = datetime.fromtimestamp(day_data.get("dt", 0))
                            day_weather = day_data.get("weather", [{}])[0]
                            forecast.append(
                                {
                                    "day": day_names[dt.weekday()]
                                    if i > 0
                                    else "Today",
                                    "high": round(
                                        day_data.get("temp", {}).get("max", 0)
                                    ),
                                    "low": round(
                                        day_data.get("temp", {}).get("min", 0)
                                    ),
                                    "condition": day_weather.get("main", "Clear"),
                                }
                            )

                        today = daily[0] if daily else {}
                        result = {
                            "temperature": round(current.get("temp", 0)),
                            "condition": weather_info.get("main", "Clear"),
                            "location": city,
                            "high": round(today.get("temp", {}).get("max", 0))
                            if today
                            else None,
                            "low": round(today.get("temp", {}).get("min", 0))
                            if today
                            else None,
                            "forecast": forecast,
                        }
                        if on_data:
                            on_data(result)
                        return result
                except Exception as owm_err:
                    logger.debug(f"Weather: OpenWeatherMap failed: {owm_err}")

            # Fallback to Open-Meteo (free, no API key) with daily forecast
            response = await session.get(
                f"https://api.open-meteo.com/v1/forecast?"
                f"latitude={lat}&longitude={lon}"
                f"&current=temperature_2m,weather_code"
                f"&daily=temperature_2m_max,temperature_2m_min,weather_code"
                f"&temperature_unit=fahrenheit"
                f"&timezone=auto",
                timeout=10,
            )
            if response.status == 200:
                data = await response.json()
                current = data.get("current", {})
                temp = current.get("temperature_2m")
                weather_code = current.get("weather_code", 0)
                condition = wmo_code_to_condition(weather_code)

                # Parse daily forecast
                daily = data.get("daily", {})
                dates = daily.get("time", [])
                highs = daily.get("temperature_2m_max", [])
                lows = daily.get("temperature_2m_min", [])
                codes = daily.get("weather_code", [])

                forecast = []
                day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
                for i in range(min(7, len(dates))):
                    try:
                        dt = datetime.strptime(dates[i], "%Y-%m-%d")
                        day_name = "Today" if i == 0 else day_names[dt.weekday()]
                        forecast.append(
                            {
                                "day": day_name,
                                "high": round(highs[i]) if i < len(highs) else None,
                                "low": round(lows[i]) if i < len(lows) else None,
                                "condition": wmo_code_to_condition(
                                    codes[i] if i < len(codes) else 0
                                ),
                            }
                        )
                    except (ValueError, IndexError):
                        continue

                today_high = round(highs[0]) if highs else None
                today_low = round(lows[0]) if lows else None

                result = {
                    "temperature": round(temp) if temp is not None else None,
                    "condition": condition,
                    "location": city,
                    "high": today_high,
                    "low": today_low,
                    "forecast": forecast,
                }
                if on_data:
                    on_data(result)
                return result

    except Exception as e:
        logger.warning(f"Weather: Failed to fetch data: {e}")

    if on_data:
        on_data(default_data)
    return default_data
