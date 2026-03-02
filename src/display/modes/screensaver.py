"""Screensaver display mode implementations."""

import asyncio
import logging
import math
import random
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable, Dict, List

from ..base import BaseDisplay, Color

if TYPE_CHECKING:
    from ..manager import DisplayManager


def hsv_to_rgb(h: float, s: float, v: float) -> Color:
    """Convert HSV to RGB Color."""
    import colorsys

    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return Color(
        max(0, min(255, int(r * 255))),
        max(0, min(255, int(g * 255))),
        max(0, min(255, int(b * 255))),
    )


def init_starfield(d: BaseDisplay, num_stars: int = 200) -> List[Dict]:
    """Initialize starfield particles."""
    stars = []
    for _ in range(num_stars):
        stars.append(
            {
                "x": random.uniform(0, d.width),
                "y": random.uniform(0, d.height),
                "z": random.uniform(0.1, 1.0),
                "speed": random.uniform(0.3, 0.8),
                "brightness_phase": random.uniform(0, 6.28),
            }
        )
    return stars


def init_matrix(d: BaseDisplay, num_columns: int = 40) -> tuple:
    """Initialize matrix rain. Returns (matrix_chars, matrix_drops)."""
    matrix_chars = "アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲンABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@#$%&*+=<>?|{}[]~"
    matrix_drops = []

    col_width = max(10, d.width // num_columns)
    num_columns = d.width // col_width

    for i in range(num_columns):
        trail_len = random.randint(12, 30)
        matrix_drops.append(
            {
                "x": i * col_width + col_width // 2,
                "y": random.uniform(-500, 0),
                "speed": random.uniform(2.0, 5.5),
                "trail_len": trail_len,
                "chars": [random.choice(matrix_chars) for _ in range(trail_len)],
                "change_timers": [random.uniform(0, 0.25) for _ in range(trail_len)],
                "glow_intensity": random.uniform(0.8, 1.2),
            }
        )
    return matrix_chars, matrix_drops


def init_bounce(d: BaseDisplay) -> tuple:
    """Initialize bounce screensaver. Returns (pos, vel, hue)."""
    pos = [float(d.width // 4), float(d.height // 4)]
    vel = [1.2, 0.9]
    hue = 0.0
    return pos, vel, hue


def init_fade(d: BaseDisplay) -> Dict[str, Any]:
    """Initialize fade screensaver state."""
    width, height = d.width, d.height

    clock_pos = [
        random.uniform(width * 0.2, width * 0.6),
        random.uniform(height * 0.2, height * 0.6),
    ]
    clock_vel = [
        random.choice([-1, 1]) * random.uniform(0.18, 0.3),
        random.choice([-1, 1]) * random.uniform(0.12, 0.25),
    ]

    blobs = []
    for i in range(7):
        blobs.append(
            {
                "x": random.uniform(0, width),
                "y": random.uniform(0, height),
                "vx": random.uniform(-0.4, 0.4),
                "vy": random.uniform(-0.3, 0.3),
                "radius": random.uniform(width * 0.12, width * 0.28),
                "hue_offset": i * 0.14,
                "pulse_phase": random.uniform(0, 6.28),
            }
        )

    particles = []
    for _ in range(60):
        particles.append(
            {
                "x": random.uniform(0, width),
                "y": random.uniform(0, height),
                "vx": random.uniform(-0.6, 0.6),
                "vy": random.uniform(-0.4, 0.4),
                "size": random.uniform(2, 6),
                "brightness": random.uniform(0.4, 0.9),
                "phase": random.uniform(0, 6.28),
                "phase_speed": random.uniform(1.5, 3.0),
            }
        )

    return {
        "clock_pos": clock_pos,
        "clock_vel": clock_vel,
        "blobs": blobs,
        "particles": particles,
        "hue": 0.0,
    }


async def render_starfield(
    d: BaseDisplay, dt: float, stars: List[Dict], matrix_chars: str = None
) -> None:
    """Render starfield screensaver."""
    d.clear_sync(Color(2, 2, 12))
    cx, cy = d.get_center()
    speed_mult = dt * 60

    for star in stars:
        star["z"] -= 0.005 * star["speed"] * speed_mult
        star["brightness_phase"] += dt * 3

        if star["z"] <= 0.01:
            star["x"] = random.uniform(0, d.width)
            star["y"] = random.uniform(0, d.height)
            star["z"] = 1.0
            star["speed"] = random.uniform(0.3, 0.8)

        proj_x = int(cx + (star["x"] - cx) / star["z"])
        proj_y = int(cy + (star["y"] - cy) / star["z"])

        size = max(1, int(4 * (1 - star["z"])))
        twinkle = 0.85 + 0.15 * math.sin(star["brightness_phase"])
        base_brightness = int(255 * (1 - star["z"] * 0.3) * twinkle)

        if 0 <= proj_x < d.width and 0 <= proj_y < d.height:
            r = min(255, int(base_brightness * 0.95))
            g = min(255, int(base_brightness * 0.98))
            b = min(255, int(base_brightness + 40))
            color = Color(r, g, b)

            if size <= 1:
                d.fill_rect_sync(proj_x, proj_y, 2, 2, color)
            elif size == 2:
                d.fill_rect_sync(proj_x - 1, proj_y - 1, 3, 3, color)
            else:
                d.draw_circle_sync(proj_x, proj_y, size, color, True)


async def render_matrix(
    d: BaseDisplay, dt: float, matrix_chars: str, matrix_drops: List[Dict]
) -> None:
    """Render matrix rain screensaver."""
    d.clear_sync(Color(0, 5, 0))

    font_size = d.scale_font(13)
    char_height = font_size + 2
    speed_mult = dt * 60

    for drop in matrix_drops:
        drop["y"] += drop["speed"] * speed_mult

        trail_len = drop["trail_len"]
        total_height = trail_len * char_height

        if drop["y"] > d.height + total_height:
            drop["y"] = random.uniform(-400, -100)
            drop["speed"] = random.uniform(2.0, 5.5)
            drop["trail_len"] = random.randint(12, 30)
            drop["chars"] = [
                random.choice(matrix_chars) for _ in range(drop["trail_len"])
            ]
            drop["change_timers"] = [
                random.uniform(0, 0.2) for _ in range(drop["trail_len"])
            ]
            drop["glow_intensity"] = random.uniform(0.8, 1.2)

        glow = drop.get("glow_intensity", 1.0)

        for i in range(len(drop["chars"])):
            drop["change_timers"][i] -= dt
            if drop["change_timers"][i] <= 0:
                drop["chars"][i] = random.choice(matrix_chars)
                drop["change_timers"][i] = (
                    random.uniform(0.02, 0.08) if i < 3 else random.uniform(0.06, 0.25)
                )

        for i, char in enumerate(drop["chars"]):
            char_y = int(drop["y"] - i * char_height)

            if 0 <= char_y < d.height:
                if i == 0:
                    color = Color(240, 255, 240)
                elif i == 1:
                    color = Color(200, 255, 200)
                elif i == 2:
                    color = Color(120, 255, 120)
                elif i == 3:
                    color = Color(80, 240, 80)
                else:
                    fade = max(0, int((230 - i * 12) * glow))
                    color = Color(0, fade, int(fade * 0.1))

                d.draw_text_sync(char, int(drop["x"]), char_y, color, font_size)


async def render_bounce(
    d: BaseDisplay, dt: float, pos: List[float], vel: List[float], hue: float,
    text: str = "GPT Home",
) -> float:
    """Render bouncing logo screensaver. Returns updated hue."""
    d.clear_sync(Color(3, 3, 10))

    speed_mult = dt * 60
    pos[0] += vel[0] * speed_mult
    pos[1] += vel[1] * speed_mult

    logo_text = text
    font_size = d.scale_font(48)
    logo_w, logo_h = d.get_text_size(logo_text, font_size)

    hit_edge = False
    if pos[0] <= 0:
        pos[0] = 0
        vel[0] = abs(vel[0]) * random.uniform(0.95, 1.05)
        hit_edge = True
    elif pos[0] + logo_w >= d.width:
        pos[0] = d.width - logo_w
        vel[0] = -abs(vel[0]) * random.uniform(0.95, 1.05)
        hit_edge = True

    if pos[1] <= 0:
        pos[1] = 0
        vel[1] = abs(vel[1]) * random.uniform(0.95, 1.05)
        hit_edge = True
    elif pos[1] + logo_h >= d.height:
        pos[1] = d.height - logo_h
        vel[1] = -abs(vel[1]) * random.uniform(0.95, 1.05)
        hit_edge = True

    if hit_edge:
        hue = (hue + 0.08 + random.uniform(0, 0.08)) % 1.0

    color = hsv_to_rgb(hue, 0.85, 1.0)
    x, y = int(pos[0]), int(pos[1])

    glow_color = hsv_to_rgb(hue, 0.6, 0.3)
    d.draw_text_sync(logo_text, x + 4, y + 4, glow_color, font_size)

    shadow_color = Color(color.r // 6, color.g // 6, color.b // 6)
    d.draw_text_sync(logo_text, x + 2, y + 2, shadow_color, font_size)

    d.draw_text_sync(logo_text, x, y, color, font_size)

    return hue


async def render_fade(d: BaseDisplay, dt: float, state: Dict[str, Any]) -> None:
    """Render ambient fade screensaver with floating clock."""
    blobs = state["blobs"]
    particles = state["particles"]
    clock_pos = state["clock_pos"]
    clock_vel = state["clock_vel"]

    state["hue"] = (state["hue"] + dt * 0.04) % 1.0
    hue = state["hue"]
    t = time.perf_counter()

    # Background gradient
    base_hue = hue
    for y_band in range(0, d.height, 6):
        band_t = y_band / d.height
        band_hue = (base_hue + band_t * 0.18) % 1.0
        sat = 0.55 + band_t * 0.25
        val = 0.1 + (1 - band_t) * 0.08
        color = hsv_to_rgb(band_hue, sat, val)
        d.fill_rect_sync(0, y_band, d.width, 7, color)

    # Floating blobs
    for blob in blobs:
        blob["x"] += blob["vx"] * dt * 60
        blob["y"] += blob["vy"] * dt * 60
        blob["pulse_phase"] = blob.get("pulse_phase", 0) + dt * 0.8

        if blob["x"] < -blob["radius"] * 0.4:
            blob["vx"] = abs(blob["vx"]) * random.uniform(0.9, 1.1)
        elif blob["x"] > d.width + blob["radius"] * 0.4:
            blob["vx"] = -abs(blob["vx"]) * random.uniform(0.9, 1.1)
        if blob["y"] < -blob["radius"] * 0.4:
            blob["vy"] = abs(blob["vy"]) * random.uniform(0.9, 1.1)
        elif blob["y"] > d.height + blob["radius"] * 0.4:
            blob["vy"] = -abs(blob["vy"]) * random.uniform(0.9, 1.1)

        blob_hue = (hue + blob["hue_offset"]) % 1.0
        pulse = 1.0 + math.sin(blob["pulse_phase"]) * 0.2
        radius = int(blob["radius"] * pulse)

        for layer in range(5, 0, -1):
            layer_r = int(radius * (0.35 + layer * 0.13))
            layer_val = 0.04 + (5 - layer) * 0.025
            glow_color = hsv_to_rgb(blob_hue, 0.65, layer_val)
            d.draw_circle_sync(
                int(blob["x"]), int(blob["y"]), layer_r, glow_color, True
            )

    # Particles
    for particle in particles:
        particle["x"] += particle["vx"] * dt * 60
        particle["y"] += particle["vy"] * dt * 60
        particle["phase"] += dt * particle.get("phase_speed", 2.0)

        if particle["x"] < 0:
            particle["x"] = d.width
        elif particle["x"] > d.width:
            particle["x"] = 0
        if particle["y"] < 0:
            particle["y"] = d.height
        elif particle["y"] > d.height:
            particle["y"] = 0

        twinkle = 0.4 + 0.6 * math.sin(particle["phase"])
        brightness = particle["brightness"] * twinkle
        p_hue = (hue + 0.5) % 1.0
        p_color = hsv_to_rgb(p_hue, 0.35, brightness)

        size = int(particle["size"] * (0.7 + twinkle * 0.5))
        if size > 3:
            d.draw_circle_sync(
                int(particle["x"]), int(particle["y"]), size // 2, p_color, True
            )
        else:
            d.fill_rect_sync(
                int(particle["x"]) - size // 2,
                int(particle["y"]) - size // 2,
                size,
                size,
                p_color,
            )

    # Floating clock
    clock_margin_x = d.scale_x(120)
    clock_margin_y = d.scale_y(60)

    clock_pos[0] += clock_vel[0] * dt * 60
    clock_pos[1] += clock_vel[1] * dt * 60

    if clock_pos[0] < clock_margin_x:
        clock_pos[0] = clock_margin_x
        clock_vel[0] = abs(clock_vel[0]) * random.uniform(0.8, 1.2)
        clock_vel[1] += random.uniform(-0.05, 0.05)
    elif clock_pos[0] > d.width - clock_margin_x:
        clock_pos[0] = d.width - clock_margin_x
        clock_vel[0] = -abs(clock_vel[0]) * random.uniform(0.8, 1.2)
        clock_vel[1] += random.uniform(-0.05, 0.05)

    if clock_pos[1] < clock_margin_y:
        clock_pos[1] = clock_margin_y
        clock_vel[1] = abs(clock_vel[1]) * random.uniform(0.8, 1.2)
        clock_vel[0] += random.uniform(-0.05, 0.05)
    elif clock_pos[1] > d.height - clock_margin_y:
        clock_pos[1] = d.height - clock_margin_y
        clock_vel[1] = -abs(clock_vel[1]) * random.uniform(0.8, 1.2)
        clock_vel[0] += random.uniform(-0.05, 0.05)

    max_vel = 0.4
    clock_vel[0] = max(-max_vel, min(max_vel, clock_vel[0]))
    clock_vel[1] = max(-max_vel, min(max_vel, clock_vel[1]))

    now = datetime.now()
    time_str = now.strftime("%I:%M").lstrip("0")
    time_size = d.scale_font(56)

    clock_x = int(clock_pos[0])
    clock_y = int(clock_pos[1])

    time_w, time_h = d.get_text_size(time_str, time_size)

    text_hue = (hue + 0.5) % 1.0
    glow_pulse = 0.8 + 0.2 * math.sin(t * 2)

    for glow_layer in range(3, 0, -1):
        glow_offset = glow_layer * 2
        glow_val = 0.15 * (4 - glow_layer) * glow_pulse
        glow_color = hsv_to_rgb(text_hue, 0.4, glow_val)
        d.draw_text_sync(
            time_str,
            clock_x - time_w // 2 - glow_offset,
            clock_y - time_h // 2,
            glow_color,
            time_size,
        )
        d.draw_text_sync(
            time_str,
            clock_x - time_w // 2 + glow_offset,
            clock_y - time_h // 2,
            glow_color,
            time_size,
        )

    text_color = hsv_to_rgb(text_hue, 0.2, 0.95)
    d.draw_text_sync(
        time_str,
        clock_x - time_w // 2,
        clock_y - time_h // 2,
        text_color,
        time_size,
    )

    ampm = now.strftime("%p")
    ampm_size = d.scale_font(18)
    ampm_w, ampm_h = d.get_text_size(ampm, ampm_size)
    ampm_color = hsv_to_rgb(text_hue, 0.3, 0.6)
    d.draw_text_sync(
        ampm,
        clock_x - ampm_w // 2,
        clock_y + time_h // 2 + d.scale_y(8),
        ampm_color,
        ampm_size,
    )


def init_style(d: BaseDisplay, style: str, settings: Dict = None) -> Dict[str, Any]:
    if style == "matrix":
        chars, drops = init_matrix(d, max(4, d.width // 12))
        return {"matrix_chars": chars, "matrix_drops": drops}
    elif style == "bounce":
        pos, vel, hue = init_bounce(d)
        text = (settings or {}).get("screensaver_bounce_text", "GPT Home")
        return {"pos": pos, "vel": vel, "hue": hue, "text": text}
    elif style == "fade":
        return {"fade": init_fade(d)}
    else:
        return {"stars": init_starfield(d, max(80, d.width * d.height // 550))}


async def render_style(d: BaseDisplay, style: str, dt: float, state: Dict[str, Any]) -> None:
    if style == "matrix":
        await render_matrix(d, dt, state["matrix_chars"], state["matrix_drops"])
    elif style == "bounce":
        state["hue"] = await render_bounce(
            d, dt, state["pos"], state["vel"], state["hue"], state["text"],
        )
    elif style == "fade":
        await render_fade(d, dt, state["fade"])
    else:
        await render_starfield(d, dt, state["stars"])


async def screensaver_loop(
    manager: "DisplayManager",
    style: str,
    stop_check: Callable[[], bool],
    activity_check: Callable[[], bool],
    deactivate_callback: Callable,
) -> None:
    d = manager._display
    if not d:
        return

    style = style.lower()
    if style not in ("starfield", "matrix", "bounce", "fade"):
        style = "starfield"

    try:
        from src.common import load_settings
        settings = load_settings()
    except Exception:
        settings = {}

    state = init_style(d, style, settings)
    last_frame = time.perf_counter()
    frame_time = 1.0 / 60

    try:
        while not stop_check() and manager._screensaver_active:
            now = time.perf_counter()
            dt = now - last_frame
            last_frame = now

            if activity_check():
                await deactivate_callback()
                break

            if not manager._screensaver_active or stop_check():
                break

            try:
                await asyncio.wait_for(manager._render_lock.acquire(), timeout=0.02)
            except asyncio.TimeoutError:
                await asyncio.sleep(0.002)
                continue

            should_break = False
            try:
                if not d or stop_check() or not manager._screensaver_active:
                    should_break = True
                else:
                    await render_style(d, style, dt, state)
                    d.show_sync()
            finally:
                manager._render_lock.release()

            if should_break:
                break

            elapsed = time.perf_counter() - now
            await asyncio.sleep(max(0.001, frame_time - elapsed))

    except asyncio.CancelledError:
        pass
    except Exception as e:
        logging.getLogger("display.modes.screensaver").error(
            "Screensaver loop error: %s", e
        )
        try:
            await deactivate_callback()
        except Exception:
            manager._screensaver_active = False
