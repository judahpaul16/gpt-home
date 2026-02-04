"""Screensaver rendering functions for the display manager."""

import math
import random
from typing import Any, Dict, List

from .base import BaseDisplay, Color
from .palette import Palette, lerp


async def render_starfield(
    d: BaseDisplay,
    dt: float,
    stars: List[Dict[str, float]],
    frame: int,
) -> None:
    """Render starfield screensaver."""
    d.clear_sync(Color(0, 0, 0))

    if not stars:
        for _ in range(100):
            stars.append(
                {
                    "x": random.uniform(0, d.width),
                    "y": random.uniform(0, d.height),
                    "z": random.uniform(0.1, 1.0),
                    "speed": random.uniform(20, 100),
                }
            )

    cx, cy = d.get_center()
    for star in stars:
        star["z"] -= dt * 0.3
        if star["z"] <= 0.01:
            star["x"] = random.uniform(0, d.width)
            star["y"] = random.uniform(0, d.height)
            star["z"] = 1.0
            star["speed"] = random.uniform(20, 100)

        px = cx + (star["x"] - cx) / star["z"]
        py = cy + (star["y"] - cy) / star["z"]

        if 0 <= px < d.width and 0 <= py < d.height:
            brightness = int(255 * (1.0 - star["z"]))
            size = max(1, int(3 * (1.0 - star["z"])))
            color = Color(brightness, brightness, brightness)
            d.fill_rect_sync(int(px), int(py), size, size, color)

    d.show_sync()


async def render_matrix(
    d: BaseDisplay,
    dt: float,
    drops: List[Dict[str, Any]],
    frame: int,
) -> None:
    """Render matrix rain screensaver."""
    d.clear_sync(Color(0, 0, 0))

    col_width = 14
    num_cols = d.width // col_width

    if not drops:
        for i in range(num_cols):
            drops.append(
                {
                    "x": i * col_width,
                    "y": random.randint(-d.height, 0),
                    "speed": random.uniform(100, 300),
                    "chars": [chr(random.randint(0x30A0, 0x30FF)) for _ in range(20)],
                    "length": random.randint(5, 15),
                }
            )

    for drop in drops:
        drop["y"] += drop["speed"] * dt

        if drop["y"] > d.height + 200:
            drop["y"] = random.randint(-200, -50)
            drop["speed"] = random.uniform(100, 300)
            drop["length"] = random.randint(5, 15)

        for i in range(drop["length"]):
            char_y = int(drop["y"] - i * 14)
            if 0 <= char_y < d.height:
                if i == 0:
                    color = Color(180, 255, 180)
                else:
                    fade = 1.0 - (i / drop["length"])
                    green = int(200 * fade)
                    color = Color(0, green, 0)

                char = drop["chars"][i % len(drop["chars"])]
                d.draw_text_sync(char, drop["x"], char_y, color, 12)

    d.show_sync()


async def render_bounce(
    d: BaseDisplay,
    dt: float,
    pos: List[float],
    vel: List[float],
    frame: int,
) -> None:
    """Render bouncing logo screensaver."""
    d.clear_sync(Color(0, 0, 0))

    logo_w, logo_h = 120, 40

    pos[0] += vel[0] * dt * 100
    pos[1] += vel[1] * dt * 100

    if pos[0] <= 0 or pos[0] + logo_w >= d.width:
        vel[0] = -vel[0]
        pos[0] = max(0, min(d.width - logo_w, pos[0]))

    if pos[1] <= 0 or pos[1] + logo_h >= d.height:
        vel[1] = -vel[1]
        pos[1] = max(0, min(d.height - logo_h, pos[1]))

    hue = (frame * 2) % 360
    r, g, b = hsv_to_rgb(hue / 360, 0.8, 1.0)
    color = Color(int(r * 255), int(g * 255), int(b * 255))

    x, y = int(pos[0]), int(pos[1])
    d.draw_rounded_rect_sync(x, y, logo_w, logo_h, 8, color)
    d.draw_text_sync("GPT", x + 15, y + 10, Color(0, 0, 0), 20)

    d.show_sync()


async def render_fade(
    d: BaseDisplay,
    dt: float,
    hue: float,
    clock_pos: List[float],
    clock_vel: List[float],
    blobs: List[Dict[str, float]],
    particles: List[Dict[str, float]],
    frame: int,
) -> float:
    """Render ambient fade screensaver with floating clock."""
    from datetime import datetime

    hue = (hue + dt * 15) % 360

    r, g, b = hsv_to_rgb(hue / 360, 0.3, 0.15)
    d.clear_sync(Color(int(r * 255), int(g * 255), int(b * 255)))

    if not blobs:
        for _ in range(5):
            blobs.append(
                {
                    "x": random.uniform(0, d.width),
                    "y": random.uniform(0, d.height),
                    "vx": random.uniform(-20, 20),
                    "vy": random.uniform(-20, 20),
                    "radius": random.uniform(50, 150),
                    "hue_offset": random.uniform(0, 60),
                }
            )

    for blob in blobs:
        blob["x"] += blob["vx"] * dt
        blob["y"] += blob["vy"] * dt

        if blob["x"] < -blob["radius"] or blob["x"] > d.width + blob["radius"]:
            blob["vx"] = -blob["vx"]
        if blob["y"] < -blob["radius"] or blob["y"] > d.height + blob["radius"]:
            blob["vy"] = -blob["vy"]

        blob_hue = (hue + blob["hue_offset"]) % 360
        br, bg, bb = hsv_to_rgb(blob_hue / 360, 0.4, 0.2)

        for ring in range(3, 0, -1):
            alpha = 0.3 / ring
            radius = int(blob["radius"] * ring / 3)
            ring_color = Color(
                int(br * 255 * alpha),
                int(bg * 255 * alpha),
                int(bb * 255 * alpha),
            )
            d.draw_circle_sync(int(blob["x"]), int(blob["y"]), radius, ring_color, True)

    clock_pos[0] += clock_vel[0] * dt * 30
    clock_pos[1] += clock_vel[1] * dt * 30

    margin = 100
    if clock_pos[0] < margin or clock_pos[0] > d.width - margin:
        clock_vel[0] = -clock_vel[0]
    if clock_pos[1] < margin or clock_pos[1] > d.height - margin:
        clock_vel[1] = -clock_vel[1]

    now = datetime.now()
    time_str = now.strftime("%I:%M").lstrip("0")
    time_size = d.scale_font(48)
    time_w, _ = d.get_text_size(time_str, time_size)

    text_hue = (hue + 180) % 360
    tr, tg, tb = hsv_to_rgb(text_hue / 360, 0.5, 0.9)
    text_color = Color(int(tr * 255), int(tg * 255), int(tb * 255))

    d.draw_text_sync(
        time_str,
        int(clock_pos[0] - time_w // 2),
        int(clock_pos[1]),
        text_color,
        time_size,
    )

    d.show_sync()
    return hue


def hsv_to_rgb(h: float, s: float, v: float) -> tuple:
    """Convert HSV to RGB (0-1 range)."""
    if s == 0:
        return v, v, v

    i = int(h * 6)
    f = h * 6 - i
    p = v * (1 - s)
    q = v * (1 - f * s)
    t = v * (1 - (1 - f) * s)

    i %= 6
    if i == 0:
        return v, t, p
    if i == 1:
        return q, v, p
    if i == 2:
        return p, v, t
    if i == 3:
        return p, q, v
    if i == 4:
        return t, p, v
    return v, p, q
