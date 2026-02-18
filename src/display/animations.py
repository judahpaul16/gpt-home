"""Tool-specific animations for the display manager."""

import asyncio
import math
import time
from typing import Any, Callable, Dict, Optional

import aiohttp

from .base import BaseDisplay, Color
from .palette import Palette, ScrollingText, ease_in_out_sine, lerp

FRAME_TIME = 1.0 / 120


async def timer_animation(
    d: BaseDisplay,
    context: Dict[str, Any],
    stop_check: Callable[[], bool],
    render_lock: asyncio.Lock,
    draw_bg: Callable,
    draw_overlay: Callable,
) -> None:
    """Render timer/alarm animation."""
    duration = context.get("duration", 0)
    name = context.get("name", "Timer")
    start_time = time.perf_counter()
    last_frame = start_time
    is_alarm = "alarm" in name.lower()
    rotation = 0.0

    while not stop_check():
        now = time.perf_counter()
        dt = now - last_frame
        last_frame = now
        elapsed = now - start_time

        async with render_lock:
            if stop_check():
                break

            draw_bg(d)
            cx, cy = d.get_center()

            if duration <= 0:
                rotation += dt * 120
                pulse = ease_in_out_sine((math.sin(elapsed * 2) + 1) / 2)

                d.draw_circle_sync(
                    cx, cy, d.scale_x(90), Color(40, 45, 65), filled=False
                )
                radius = d.scale_x(70)
                d.draw_circle_sync(cx, cy, radius, Color(55, 60, 85), filled=False)

                if hasattr(d, "draw_arc_sync"):
                    arc_len = 80 + 40 * pulse
                    d.draw_arc_sync(
                        cx,
                        cy,
                        radius,
                        int(rotation % 360),
                        int((rotation + arc_len) % 360),
                        Palette.ACCENT_CYAN,
                        4,
                    )

                icon_r = d.scale_x(28)
                d.draw_circle_sync(
                    cx,
                    cy,
                    icon_r,
                    Color(
                        50 + int(15 * pulse), 55 + int(15 * pulse), 80 + int(15 * pulse)
                    ),
                    filled=True,
                )

                if is_alarm:
                    d.draw_circle_sync(
                        cx,
                        cy - d.scale_y(3),
                        d.scale_x(10),
                        Palette.ACCENT_ORANGE,
                        filled=True,
                    )
                    d.draw_circle_sync(
                        cx,
                        cy - d.scale_y(14),
                        d.scale_x(4),
                        Palette.ACCENT_ORANGE,
                        filled=True,
                    )
                else:
                    angle = math.radians(rotation * 0.3)
                    hx = int(cx + math.cos(angle - 1) * d.scale_x(8))
                    hy = int(cy + math.sin(angle - 1) * d.scale_y(8))
                    mx = int(cx + math.cos(angle) * d.scale_x(14))
                    my = int(cy + math.sin(angle) * d.scale_y(14))
                    d.draw_line_sync(cx, cy, hx, hy, Palette.ACCENT_CYAN, 3)
                    d.draw_line_sync(cx, cy, mx, my, Palette.ACCENT_CYAN, 2)

                label = f"Setting {name}"
                label_size = d.scale_font(20)
                d.draw_text_sync(
                    label,
                    int(cx - len(label) * label_size * 0.25),
                    cy + d.scale_y(55),
                    Palette.TEXT_PRIMARY,
                    label_size,
                )
            else:
                remaining = max(0, duration - elapsed)
                progress = min(1.0, elapsed / duration)

                d.draw_circle_sync(
                    cx, cy, d.scale_x(90), Color(40, 45, 65), filled=False
                )
                radius = d.scale_x(75)
                d.draw_circle_sync(cx, cy, radius, Color(50, 55, 80), filled=False)

                if hasattr(d, "draw_arc_sync"):
                    r = int(lerp(80, Palette.ACCENT_GREEN.r, progress))
                    g = int(lerp(200, Palette.ACCENT_GREEN.g, progress))
                    b = int(lerp(255, Palette.ACCENT_GREEN.b, progress))
                    d.draw_arc_sync(
                        cx,
                        cy,
                        radius,
                        -90,
                        int(-90 + progress * 360),
                        Color(r, g, b),
                        6,
                    )

                mins, secs = int(remaining // 60), int(remaining % 60)
                time_str = f"{mins}:{secs:02d}" if mins > 0 else str(secs)
                time_size = d.scale_font(52)
                d.draw_text_sync(
                    time_str,
                    int(cx - len(time_str) * time_size * 0.27),
                    cy - d.scale_y(15),
                    Palette.TEXT_PRIMARY,
                    time_size,
                )

                unit = "remaining" if mins > 0 else "seconds"
                unit_size = d.scale_font(14)
                d.draw_text_sync(
                    unit,
                    int(cx - len(unit) * unit_size * 0.25),
                    cy + d.scale_y(25),
                    Palette.TEXT_MUTED,
                    unit_size,
                )

                name_size = d.scale_font(18)
                d.draw_text_sync(
                    name,
                    int(cx - len(name) * name_size * 0.25),
                    cy + d.scale_y(55),
                    Palette.TEXT_SECONDARY,
                    name_size,
                )

                if remaining <= 0:
                    break

            draw_overlay(d)
            d.show_sync()

        await asyncio.sleep(max(0.001, FRAME_TIME - (time.perf_counter() - now)))


async def light_animation(
    d: BaseDisplay,
    context: Dict[str, Any],
    stop_check: Callable[[], bool],
    render_lock: asyncio.Lock,
) -> None:
    """Render light control animation."""
    action = context.get("action", "toggle")
    is_on = "on" in action.lower() or "toggle" in action.lower()
    frame = 0

    while not stop_check():
        now = time.perf_counter()
        pulse = ease_in_out_sine((math.sin(now * 3) + 1) / 2)

        async with render_lock:
            if stop_check():
                break

            d.clear_sync(Color(18, 20, 28))
            cx, cy = d.get_center()

            if is_on:
                glow_radius = int(d.scale_x(60 + 40 * pulse))
                for r in range(5, 0, -1):
                    alpha = 0.15 * r * pulse
                    glow_color = Color(
                        int(255 * alpha), int(220 * alpha), int(100 * alpha)
                    )
                    d.draw_circle_sync(
                        cx,
                        cy - d.scale_y(20),
                        glow_radius + r * 15,
                        glow_color,
                        filled=True,
                    )
                bulb_color = Color(int(255 * pulse), int(240 * pulse), int(180 * pulse))
            else:
                bulb_color = Color(80, 85, 100)

            d.draw_circle_sync(
                cx, cy - d.scale_y(20), d.scale_x(40), bulb_color, filled=True
            )

            status = f"Lights {action.title()}"
            status_size = d.scale_font(24)
            status_w = len(status) * (status_size * 0.5)
            d.draw_text_sync(
                status,
                int(cx - status_w // 2),
                cy + d.scale_y(50),
                Palette.TEXT_PRIMARY,
                status_size,
            )

            dots = "." * ((frame // 15) % 4)
            proc_text = f"Controlling{dots}"
            proc_size = d.scale_font(14)
            d.draw_text_sync(
                proc_text,
                int(cx - len(proc_text) * proc_size * 0.25),
                cy + d.scale_y(80),
                Palette.TEXT_MUTED,
                proc_size,
            )

            d.show_sync()

        frame += 1
        await asyncio.sleep(max(0.001, FRAME_TIME - (time.perf_counter() - now)))


async def generic_tool_animation(
    d: BaseDisplay,
    tool_name: str,
    stop_check: Callable[[], bool],
    render_lock: asyncio.Lock,
) -> None:
    """Render generic tool animation with spinning dots."""
    frame = 0

    while not stop_check():
        t = (frame % 60) / 60.0
        phase = t * math.pi * 2

        async with render_lock:
            if stop_check():
                break

            d.clear_sync(Color(18, 20, 28))
            cx, cy = d.get_center()

            for j in range(8):
                angle = (j / 8) * math.pi * 2 + phase
                radius = d.scale_x(50) + int(10 * math.sin(phase * 2))
                x = cx + int(math.cos(angle) * radius)
                y = cy + int(math.sin(angle) * radius)
                dot_size = 4 + int(4 * (1 + math.sin(phase + j)))
                colors = [
                    Palette.ACCENT_CYAN,
                    Palette.ACCENT_BLUE,
                    Palette.ACCENT_PURPLE,
                    Palette.ACCENT_PINK,
                ]
                color = colors[(j + frame // 15) % len(colors)]
                d.draw_circle_sync(x, y, dot_size, color, filled=True)

            name = tool_name.replace("_", " ").title()
            name_size = d.scale_font(20)
            name_w = len(name) * (name_size * 0.5)
            d.draw_text_sync(
                name,
                int(cx - name_w // 2),
                cy + d.scale_y(80),
                Palette.TEXT_SECONDARY,
                name_size,
            )

            dots = "." * ((frame // 20) % 4)
            status = f"Processing{dots}"
            status_size = d.scale_font(14)
            status_w = len(status) * (status_size * 0.5)
            d.draw_text_sync(
                status,
                int(cx - status_w // 2),
                cy + d.scale_y(110),
                Palette.TEXT_MUTED,
                status_size,
            )

            d.show_sync()

        frame += 1
        await asyncio.sleep(0.016)
