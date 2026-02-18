"""Weather display mode loop."""

import asyncio
import logging
import math
import random
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from ..base import Color, DisplayMode
from ..renderers import draw_host_ip_overlay
from ..weather import (
    draw_cloud_fancy,
    draw_sun,
    draw_weather_gradient,
    draw_weather_icon_fancy,
    draw_weather_icon_mini,
    get_weather_colors,
)

if TYPE_CHECKING:
    from ..manager import DisplayManager


async def weather_loop(
    manager: "DisplayManager",
    stop_check: Callable[[], bool],
    screensaver_check: Callable[[], bool],
    fetch_forecast: bool = False,
    location: Optional[str] = None,
) -> None:
    """Main weather display loop with animated elements."""
    try:
        last_frame = time.perf_counter()
        rain_drops: List[Dict] = []
        snow_flakes: List[Dict] = []

        random.seed()
        clouds = _init_clouds()
        stars = _init_stars()

        if (
            fetch_forecast
            or not manager._weather_data
            or manager._weather_data.get("temperature") is None
        ):
            await manager._fetch_weather_data(location=location)

        last_weather_fetch = asyncio.get_event_loop().time()
        weather_refresh_interval = 600

        phase = 0.0
        glow_phase = 0.0
        last_frame_time = time.time()
        target_fps = 60
        frame_duration = 1.0 / target_fps

        while not stop_check() and not screensaver_check():
            if manager._mode not in (DisplayMode.WEATHER, DisplayMode.SMART):
                break
            if (
                manager._mode == DisplayMode.SMART
                and manager._state.name != "TOOL_ANIMATION"
            ):
                break
            if (
                manager._mode == DisplayMode.SMART
                and manager._tool_animation_start > 0
                and time.time() - manager._tool_animation_start
                > manager._tool_animation_timeout
            ):
                asyncio.create_task(manager.resume_idle())
                break

            current_frame_time = time.time()
            delta_time = current_frame_time - last_frame_time
            last_frame_time = current_frame_time

            manager._frame += 1
            phase += delta_time * 0.8
            glow_phase += delta_time * 1.2

            # Periodically refresh weather data
            current_time = asyncio.get_event_loop().time()
            if current_time - last_weather_fetch > weather_refresh_interval:
                await manager._fetch_weather_data()
                last_weather_fetch = current_time

            if stop_check() or screensaver_check():
                break

            now_time = time.perf_counter()
            dt = min(0.05, now_time - last_frame)
            last_frame = now_time

            async with manager._render_lock:
                d = manager._display
                if not d or stop_check():
                    break

                if not manager._weather_data:
                    manager._weather_data = {}

                cond = manager._weather_data.get("condition", "clear").lower()
                temp = manager._weather_data.get("temperature")
                loc = manager._weather_data.get("location", "")
                forecast = manager._weather_data.get("forecast", [])
                high_temp = manager._weather_data.get("high")
                low_temp = manager._weather_data.get("low")

                now = datetime.now()
                hour = now.hour
                top_color, bottom_color, accent_color, is_night = get_weather_colors(
                    cond, hour
                )

                draw_weather_gradient(d, top_color, bottom_color)

                # Draw stars at night
                if is_night:
                    _render_stars(d, stars, delta_time)

                # Draw sun or moon
                if "clear" in cond or "sun" in cond:
                    if is_night:
                        _render_moon(d, glow_phase)
                    else:
                        draw_sun(d, d.width - d.scale_x(100), d.scale_y(90), phase)

                # Draw clouds
                _update_and_render_clouds(d, clouds, delta_time)

                # Draw rain if applicable
                if "rain" in cond or "drizzle" in cond:
                    _render_rain(d, rain_drops, delta_time, manager._frame)

                # Draw snow if applicable
                if "snow" in cond:
                    _render_snow(d, snow_flakes, delta_time, manager._frame)

                # Thunder flash
                if "thunder" in cond and random.random() < 0.02:
                    d.draw_rounded_rect_sync(
                        0, 0, d.width, d.height, 0, Color(255, 255, 255)
                    )

                # Render weather card and forecast
                _render_weather_card(
                    d,
                    cond,
                    temp,
                    loc,
                    high_temp,
                    low_temp,
                    forecast,
                    phase,
                )

                draw_host_ip_overlay(d, manager._get_host_ip())
                d.show_sync()

            elapsed = time.time() - current_frame_time
            sleep_time = max(0.001, frame_duration - elapsed)
            await asyncio.sleep(sleep_time)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logging.getLogger("display.modes.weather").error(
            "Weather loop error: %s", e, exc_info=True
        )


def _init_clouds() -> List[Dict]:
    """Initialize cloud particles."""
    return [
        {
            "x": float(random.randint(-100, 800)),
            "y": random.randint(20, 120),
            "w": random.randint(60, 140),
            "speed": random.uniform(0.15, 0.35),
            "opacity": random.uniform(0.4, 0.9),
            "bob_offset": random.uniform(0, 6.28),
            "bob_speed": random.uniform(0.008, 0.02),
        }
        for _ in range(6)
    ]


def _init_stars() -> List[Dict]:
    """Initialize star particles for night sky."""
    return [
        {
            "x": random.randint(0, 800),
            "y": random.randint(0, 200),
            "size": random.uniform(1, 3),
            "twinkle_phase": random.uniform(0, 6.28),
            "twinkle_speed": random.uniform(0.02, 0.06),
        }
        for _ in range(60)
    ]


def _render_stars(d, stars: List[Dict], delta_time: float) -> None:
    """Render twinkling stars."""
    for star in stars:
        star["twinkle_phase"] += star["twinkle_speed"] * delta_time * 60
        brightness = max(0.0, 0.5 + 0.5 * math.sin(star["twinkle_phase"]))
        star_color = Color(
            min(255, int(180 * brightness)),
            min(255, int(195 * brightness)),
            min(255, int(255 * brightness)),
        )
        sx = int(star["x"] * d.width / 800)
        sy = int(star["y"] * d.height / 480)
        if star["size"] > 2:
            d.draw_circle_sync(sx, sy, 2, star_color, True)
        else:
            d.draw_circle_sync(sx, sy, 1, star_color, True)


def _render_moon(d, glow_phase: float) -> None:
    """Render the moon with glow effect."""
    moon_x = d.width - d.scale_x(100)
    moon_y = d.scale_y(80)
    moon_r = d.scale_x(35)
    glow_intensity = 0.5 + 0.08 * math.sin(glow_phase)
    for i in range(4, 0, -1):
        glow_r = moon_r + i * 8
        d.draw_circle_sync(moon_x, moon_y, glow_r, Color(200, 220, 255), True)
    d.draw_circle_sync(moon_x, moon_y, moon_r, Color(240, 245, 255), True)
    d.draw_circle_sync(moon_x - 8, moon_y - 5, 6, Color(220, 225, 240), True)
    d.draw_circle_sync(moon_x + 10, moon_y + 8, 4, Color(225, 230, 245), True)


def _update_and_render_clouds(d, clouds: List[Dict], delta_time: float) -> None:
    """Update cloud positions and render them."""
    for cloud in clouds:
        cloud["x"] += cloud["speed"] * delta_time * 20
        if cloud["x"] > 800 + cloud["w"]:
            cloud["x"] = float(-cloud["w"] - random.randint(20, 100))
            cloud["y"] = random.randint(20, 120)
            cloud["w"] = random.randint(60, 140)
            cloud["speed"] = random.uniform(0.15, 0.35)
            cloud["opacity"] = random.uniform(0.4, 0.9)
        cloud["bob_offset"] += cloud["bob_speed"] * delta_time * 20
        bob_y = int(cloud["y"] + math.sin(cloud["bob_offset"]) * 2)
        scaled_x = int(cloud["x"] * d.width / 800)
        scaled_y = int(bob_y * d.height / 480)
        scaled_w = int(cloud["w"] * d.width / 800)
        draw_cloud_fancy(d, scaled_x, scaled_y, scaled_w, cloud["opacity"])


def _render_rain(d, rain_drops: List[Dict], delta_time: float, frame: int) -> None:
    """Render rain animation."""
    spawn_rate = max(1, int(3 - delta_time * 60))
    if len(rain_drops) < 100 and frame % spawn_rate == 0:
        for _ in range(2):
            rain_drops.append(
                {
                    "x": float(random.randint(0, d.width)),
                    "y": float(random.randint(-50, -10)),
                    "speed": random.uniform(18, 28),
                    "len": random.randint(15, 25),
                    "wind": random.uniform(2.0, 4.0),
                    "opacity": random.uniform(0.5, 1.0),
                }
            )
    new_drops = []
    for drop in rain_drops:
        drop["y"] += drop["speed"] * delta_time * 60
        drop["x"] += drop["wind"] * delta_time * 60
        if drop["y"] < d.height + 30:
            rain_color = Color(
                int(140 * drop["opacity"]),
                int(180 * drop["opacity"]),
                int(230 * drop["opacity"]),
            )
            d.draw_line_sync(
                int(drop["x"]),
                int(drop["y"]),
                int(drop["x"] + drop["wind"] * 0.5),
                int(drop["y"] + drop["len"]),
                rain_color,
                1,
            )
            new_drops.append(drop)
    rain_drops.clear()
    rain_drops.extend(new_drops)


def _render_snow(d, snow_flakes: List[Dict], delta_time: float, frame: int) -> None:
    """Render snow animation."""
    if len(snow_flakes) < 80 and frame % 2 == 0:
        snow_flakes.append(
            {
                "x": float(random.randint(0, d.width)),
                "y": float(random.randint(-30, -5)),
                "speed": random.uniform(1.5, 4.0),
                "wobble": random.uniform(0, 6.28),
                "wobble_speed": random.uniform(0.06, 0.12),
                "wobble_amount": random.uniform(1.0, 2.5),
                "size": random.randint(2, 5),
                "opacity": random.uniform(0.7, 1.0),
            }
        )
    new_flakes = []
    for flake in snow_flakes:
        flake["y"] += flake["speed"] * delta_time * 60
        flake["wobble"] += flake["wobble_speed"]
        flake["x"] += (
            math.sin(flake["wobble"]) * flake["wobble_amount"] * delta_time * 60
        )
        if flake["y"] < d.height + 10:
            snow_brightness = int(255 * flake["opacity"])
            d.draw_circle_sync(
                int(flake["x"]),
                int(flake["y"]),
                flake["size"],
                Color(snow_brightness, snow_brightness, snow_brightness),
                filled=True,
            )
            new_flakes.append(flake)
    snow_flakes.clear()
    snow_flakes.extend(new_flakes)


def _render_weather_card(
    d,
    cond: str,
    temp: Optional[int],
    loc: str,
    high_temp: Optional[int],
    low_temp: Optional[int],
    forecast: List[Dict],
    phase: float,
) -> None:
    """Render the main weather card and forecast panel."""
    total_width = d.width
    total_height = d.height

    card_w = min(d.scale_x(280), int(total_width * 0.38))
    card_h = min(d.scale_y(220), int(total_height * 0.55))
    card_x = d.scale_x(30)
    card_y = (total_height - card_h) // 2

    d.draw_rounded_rect_sync(
        card_x, card_y, card_w, card_h, d.scale_x(24), Color(15, 20, 35)
    )

    # Weather icon
    icon_size = d.scale_x(70)
    icon_x = card_x + d.scale_x(20)
    icon_y = card_y + d.scale_y(20)
    draw_weather_icon_fancy(d, cond, icon_x, icon_y, icon_size, phase)

    # Temperature
    if temp is not None:
        temp_str = f"{temp}°"
        if temp <= 32:
            temp_color = Color(100, 180, 255)
        elif temp <= 50:
            temp_color = Color(150, 200, 255)
        elif temp <= 70:
            temp_color = Color(255, 255, 255)
        elif temp <= 85:
            temp_color = Color(255, 200, 100)
        else:
            temp_color = Color(255, 120, 80)
    else:
        temp_str = "--°"
        temp_color = Color(180, 190, 210)

    temp_size = d.scale_font(72)
    temp_w, temp_h = d.get_text_size(temp_str, temp_size)
    temp_x = card_x + card_w - temp_w - d.scale_x(15)
    temp_y = card_y + d.scale_y(15)

    d.draw_text_sync(temp_str, temp_x + 2, temp_y + 2, Color(0, 0, 0), temp_size)
    d.draw_text_sync(temp_str, temp_x, temp_y, temp_color, temp_size)

    # High/Low temps
    if high_temp is not None and low_temp is not None:
        hl_y = card_y + d.scale_y(90)
        hl_size = d.scale_font(18)

        high_str = f"↑{high_temp}°"
        d.draw_text_sync(
            high_str,
            card_x + card_w - d.scale_x(110),
            hl_y,
            Color(255, 150, 130),
            hl_size,
        )

        low_str = f"↓{low_temp}°"
        d.draw_text_sync(
            low_str,
            card_x + card_w - d.scale_x(55),
            hl_y,
            Color(130, 180, 255),
            hl_size,
        )

    # Condition text
    cond_display = cond.title() if cond else "Unknown"
    cond_size = d.scale_font(22)
    cond_w, cond_h = d.get_text_size(cond_display, cond_size)
    d.draw_text_sync(
        cond_display[:18],
        card_x + (card_w - cond_w) // 2,
        card_y + d.scale_y(120),
        Color(80, 200, 255),
        cond_size,
    )

    # Date and time
    now = datetime.now()
    time_str = now.strftime("%I:%M %p").lstrip("0")

    info_size = d.scale_font(13)
    loc_display = loc[:16] if loc else ""

    bottom_y = card_y + card_h - d.scale_y(20)

    if loc_display:
        d.draw_text_sync(
            loc_display,
            card_x + d.scale_x(12),
            bottom_y,
            Color(140, 155, 185),
            info_size,
        )

    time_w, _ = d.get_text_size(time_str, info_size)
    d.draw_text_sync(
        time_str,
        card_x + card_w - time_w - d.scale_x(12),
        bottom_y,
        Color(140, 155, 185),
        info_size,
    )

    # Forecast panel
    forecast_x = card_x + card_w + d.scale_x(20)
    forecast_y = card_y
    forecast_w = total_width - forecast_x - d.scale_x(25)
    forecast_h = card_h

    if forecast_w >= d.scale_x(200):
        _render_forecast_panel(
            d, forecast, forecast_x, forecast_y, forecast_w, forecast_h, phase
        )


def _render_forecast_panel(
    d,
    forecast: List[Dict],
    forecast_x: int,
    forecast_y: int,
    forecast_w: int,
    forecast_h: int,
    phase: float,
) -> None:
    """Render the 5-day forecast panel."""
    d.draw_rounded_rect_sync(
        forecast_x, forecast_y, forecast_w, forecast_h, d.scale_x(20), Color(18, 24, 42)
    )

    title_size = d.scale_font(15)
    title_str = "5-Day Forecast"
    title_w, _ = d.get_text_size(title_str, title_size)
    d.draw_text_sync(
        title_str,
        forecast_x + (forecast_w - title_w) // 2,
        forecast_y + d.scale_y(8),
        Color(160, 175, 200),
        title_size,
    )

    days_to_show = min(len(forecast), 5) if forecast else 0

    if days_to_show > 0:
        day_width = forecast_w // days_to_show
        content_start_y = forecast_y + d.scale_y(38)

        for i, day in enumerate(forecast[:days_to_show]):
            day_center_x = forecast_x + i * day_width + day_width // 2

            # Highlight today
            if i == 0:
                highlight_x = forecast_x + i * day_width + d.scale_x(4)
                highlight_w = day_width - d.scale_x(8)
                d.draw_rounded_rect_sync(
                    highlight_x,
                    content_start_y - d.scale_y(5),
                    highlight_w,
                    d.scale_y(125),
                    d.scale_x(12),
                    Color(40, 60, 100),
                )

            # Day name
            raw_day = day.get("day", "")
            if raw_day.lower() == "today":
                day_name = datetime.now().strftime("%a").upper()
            else:
                day_name = raw_day[:3].upper()
            day_name_size = d.scale_font(14)
            day_w, _ = d.get_text_size(day_name, day_name_size)
            day_color = Color(255, 220, 100) if i == 0 else Color(180, 195, 220)
            d.draw_text_sync(
                day_name,
                day_center_x - day_w // 2,
                content_start_y,
                day_color,
                day_name_size,
            )

            # Weather icon
            day_cond = day.get("condition", "clear").lower()
            icon_y = content_start_y + d.scale_y(25)
            draw_weather_icon_mini(
                d, day_cond, day_center_x, icon_y, d.scale_x(28), phase + i * 0.5
            )

            # Condition abbreviation
            cond_abbrev = day.get("condition", "")[:6]
            cond_size = d.scale_font(10)
            cond_w, _ = d.get_text_size(cond_abbrev, cond_size)
            d.draw_text_sync(
                cond_abbrev,
                day_center_x - cond_w // 2,
                icon_y + d.scale_y(18),
                Color(140, 155, 180),
                cond_size,
            )

            # High temp
            high = day.get("high")
            high_str = f"{high}°" if high is not None else "--"
            high_size = d.scale_font(18)
            high_w, _ = d.get_text_size(high_str, high_size)

            if high is not None:
                if high <= 32:
                    high_color = Color(100, 180, 255)
                elif high <= 60:
                    high_color = Color(200, 220, 255)
                elif high <= 80:
                    high_color = Color(255, 255, 255)
                else:
                    high_color = Color(255, 180, 120)
            else:
                high_color = Color(180, 190, 210)

            d.draw_text_sync(
                high_str,
                day_center_x - high_w // 2,
                content_start_y + d.scale_y(78),
                high_color,
                high_size,
            )

            # Low temp
            low = day.get("low")
            low_str = f"{low}°" if low is not None else "--"
            low_size = d.scale_font(14)
            low_w, _ = d.get_text_size(low_str, low_size)
            d.draw_text_sync(
                low_str,
                day_center_x - low_w // 2,
                content_start_y + d.scale_y(100),
                Color(120, 140, 170),
                low_size,
            )

            # Separator line
            if i < days_to_show - 1:
                sep_x = forecast_x + (i + 1) * day_width
                d.draw_line_sync(
                    sep_x,
                    content_start_y + d.scale_y(10),
                    sep_x,
                    forecast_y + forecast_h - d.scale_y(20),
                    Color(50, 60, 85),
                    1,
                )
    else:
        no_data_size = d.scale_font(16)
        no_data_str = "Loading forecast..."
        no_data_w, _ = d.get_text_size(no_data_str, no_data_size)
        d.draw_text_sync(
            no_data_str,
            forecast_x + (forecast_w - no_data_w) // 2,
            forecast_y + forecast_h // 2,
            Color(140, 150, 175),
            no_data_size,
        )
