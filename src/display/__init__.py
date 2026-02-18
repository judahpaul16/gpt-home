from .base import BaseDisplay, DisplayMode
from .detection import detect_displays
from .factory import DisplayFactory
from .manager import DisplayManager
from .multi import MirroredDisplay, MultiDisplayManager, get_multi_display_manager
from .palette import (
    Palette,
    ScrollingText,
    ease_in_out_sine,
    ease_out_cubic,
    ease_out_quad,
    lerp,
)
from .renderers import (
    draw_gradient_bg,
    draw_host_ip_overlay,
    render_waveform_bars,
    wrap_text,
)
from .spotify import spotify_now_playing_loop
from .weather import (
    draw_cloud,
    draw_cloud_fancy,
    draw_sun,
    draw_weather_gradient,
    draw_weather_icon,
    draw_weather_icon_fancy,
    draw_weather_icon_mini,
    get_weather_colors,
)

__all__ = [
    "DisplayManager",
    "BaseDisplay",
    "DisplayMode",
    "DisplayFactory",
    "detect_displays",
    "MultiDisplayManager",
    "MirroredDisplay",
    "get_multi_display_manager",
    # Palette utilities
    "Palette",
    "ScrollingText",
    "lerp",
    "ease_out_cubic",
    "ease_out_quad",
    "ease_in_out_sine",
    # Renderers
    "draw_gradient_bg",
    "draw_host_ip_overlay",
    "wrap_text",
    "render_waveform_bars",
    # Weather
    "draw_weather_gradient",
    "draw_cloud",
    "draw_cloud_fancy",
    "draw_sun",
    "draw_weather_icon",
    "draw_weather_icon_fancy",
    "draw_weather_icon_mini",
    "get_weather_colors",
    # Spotify
    "spotify_now_playing_loop",
]
