from .registry import ToolRegistry, get_all_tools
from .weather import weather_tool
from .spotify import spotify_tool
from .lights import lights_tool
from .calendar import calendar_tool
from .alarm import alarm_tool

__all__ = [
    "ToolRegistry",
    "get_all_tools",
    "weather_tool",
    "spotify_tool",
    "lights_tool",
    "calendar_tool",
    "alarm_tool",
]
