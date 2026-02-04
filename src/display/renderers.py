"""Shared rendering utilities for display modes."""

import subprocess
from typing import List, Optional

from .base import BaseDisplay, Color
from .palette import Palette


def draw_gradient_bg(d: BaseDisplay, bg_color: Optional[Color] = None) -> None:
    """Draw clean solid dark background."""
    color = bg_color or Color(18, 20, 28)
    d.clear_sync(color)


def draw_weather_gradient(d: BaseDisplay, top: tuple, bottom: tuple) -> None:
    """Draw weather-themed gradient background."""
    for y in range(d.height):
        t = y / d.height
        noise = ((y * 23) % 9 - 4) / 512.0
        t = max(0.0, min(1.0, t + noise))
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        d.fill_rect_sync(0, y, d.width, 1, Color(r, g, b))


def get_cpu_temp() -> Optional[int]:
    """Get CPU temperature in Celsius."""
    try:
        output = subprocess.check_output(["vcgencmd", "measure_temp"]).decode()
        return int(float(output.split("=")[1].split("'")[0]))
    except Exception:
        return None


def draw_host_ip_overlay(d: BaseDisplay, host_ip: str) -> None:
    """Draw host IP address in top-left and CPU temp in top-right."""
    font_size = d.scale_font(12)
    padding = d.scale_x(5)

    if host_ip:
        d.draw_text_sync(host_ip, padding, padding, Color(100, 110, 130), font_size)

    cpu_temp = get_cpu_temp()
    if cpu_temp is not None:
        temp_str = f"CPU: {cpu_temp}°C"
        text_width, _ = d.get_text_size(temp_str, font_size)
        d.draw_text_sync(
            temp_str,
            d.width - text_width - padding,
            padding,
            Color(100, 110, 130),
            font_size,
        )


def wrap_text(text: str, max_chars: int) -> List[str]:
    """Wrap text to fit within max characters per line."""
    if not text:
        return []

    words = text.split()
    lines = []
    current_line = ""

    for word in words:
        if not current_line:
            current_line = word
        elif len(current_line) + 1 + len(word) <= max_chars:
            current_line += " " + word
        else:
            lines.append(current_line)
            current_line = word

    if current_line:
        lines.append(current_line)

    return lines


def render_waveform_bars(
    d: BaseDisplay,
    waveform_values: List[float],
    voice_gated: bool = True,
) -> None:
    """Render waveform bars centered on display."""
    if not waveform_values:
        return

    cx, cy = d.get_center()
    bar_count = 32
    total_bar_area = d.width - d.scale_x(80)
    bar_width = max(8, total_bar_area // (bar_count + bar_count // 2))
    spacing = max(3, bar_width // 3)
    total_width = bar_count * (bar_width + spacing) - spacing
    start_x = cx - total_width // 2

    for i in range(bar_count):
        x = start_x + i * (bar_width + spacing)
        pos_factor = i / (bar_count - 1)
        val = waveform_values[i] if i < len(waveform_values) else 0.0

        max_height = d.scale_y(120)
        half_height = max(1, int(val * max_height))
        y = cy - half_height
        height = half_height * 2

        if val > 0.005:
            intensity = min(1.0, val * 1.5)
            r = int(50 + 180 * intensity * (0.3 + 0.7 * pos_factor))
            g = int(120 + 100 * intensity * (1.0 - 0.3 * pos_factor))
            b = int(200 + 55 * intensity)
            bar_color = Color(min(255, r), min(255, g), min(255, b))

            if val > 0.3:
                glow_alpha = min(0.4, (val - 0.3) * 0.8)
                glow_r = int(r * glow_alpha)
                glow_g = int(g * glow_alpha)
                glow_b = int(b * glow_alpha)
                d.fill_rect_sync(
                    x - 1,
                    y - 2,
                    bar_width + 2,
                    height + 4,
                    Color(glow_r // 3, glow_g // 3, glow_b // 2),
                )

            d.fill_rect_sync(x, y, bar_width, height, bar_color)

            if height > 6:
                highlight_h = max(2, height // 6)
                d.fill_rect_sync(
                    x + 1,
                    y + 1,
                    max(1, bar_width - 2),
                    highlight_h,
                    Color(min(255, r + 40), min(255, g + 30), min(255, b + 20)),
                )
        else:
            d.fill_rect_sync(x, cy - 1, bar_width, 2, Color(40, 50, 60))
