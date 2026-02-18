import asyncio
import re
from datetime import datetime
from typing import Any, Dict, Optional, Tuple


def parse_tool_context(
    user_query: str, response: str
) -> Tuple[Optional[str], Dict[str, Any]]:
    query_lower = user_query.lower()

    if any(
        w in query_lower
        for w in [
            "weather",
            "temperature",
            "forecast",
            "rain",
            "snow",
            "sunny",
            "cloudy",
        ]
    ):
        return "weather", _parse_weather_context(response)

    if any(w in query_lower for w in ["alarm", "wake me", "reminder", "remind me"]):
        return "alarm", _parse_alarm_context(user_query, response)

    if (
        any(w in query_lower for w in ["timer", "countdown", "minutes", "seconds"])
        and "set" in query_lower
    ):
        return "timer", _parse_timer_context(user_query, response)

    if any(
        w in query_lower
        for w in [
            "spotify",
            "play",
            "music",
            "song",
            "artist",
            "album",
            "playlist",
            "pause",
            "skip",
            "next",
        ]
    ):
        return "spotify", _parse_spotify_context(response)

    if any(w in query_lower for w in ["light", "lamp", "bulb", "hue", "brightness"]):
        return "lights", _parse_lights_context(user_query, response)

    if any(
        w in query_lower
        for w in ["calendar", "event", "meeting", "appointment", "schedule"]
    ):
        return "calendar", _parse_calendar_context(response)

    if any(
        w in query_lower
        for w in ["todo", "task", "to-do", "to do", "checklist", "list"]
    ):
        return "todo", _parse_todo_context(response)

    return None, {"message": response}


def _parse_weather_context(response: str) -> Dict[str, Any]:
    context = {"temperature": "--", "condition": "", "location": "", "forecast": []}

    temp_match = re.search(r"(\d+)\s*°?\s*[FfCc]", response)
    if temp_match:
        context["temperature"] = temp_match.group(1)

    conditions = [
        "sunny",
        "cloudy",
        "rain",
        "snow",
        "clear",
        "fog",
        "storm",
        "drizzle",
        "overcast",
        "partly cloudy",
    ]
    for cond in conditions:
        if cond in response.lower():
            context["condition"] = cond.title()
            break

    location_match = re.search(r"in\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)", response)
    if location_match:
        context["location"] = location_match.group(1)

    return context


def _parse_alarm_context(query: str, response: str) -> Dict[str, Any]:
    context = {"time": "", "action": "set"}

    time_match = re.search(r"(\d{1,2}:\d{2}(?:\s*[AaPp][Mm])?)", response)
    if time_match:
        context["time"] = time_match.group(1)

    if any(w in response.lower() for w in ["cancelled", "deleted", "removed"]):
        context["action"] = "cancelled"
    elif "snoozed" in response.lower():
        context["action"] = "snoozed"

    return context


def _parse_timer_context(query: str, response: str) -> Dict[str, Any]:
    context = {"duration": 0, "remaining": 0}

    mins_match = re.search(r"(\d+)\s*(?:minute|min)", query.lower())
    if mins_match:
        context["duration"] = int(mins_match.group(1)) * 60
        context["remaining"] = context["duration"]

    secs_match = re.search(r"(\d+)\s*(?:second|sec)", query.lower())
    if secs_match:
        context["duration"] += int(secs_match.group(1))
        context["remaining"] = context["duration"]

    return context


def _parse_spotify_context(response: str) -> Dict[str, Any]:
    """Parse Spotify context from response text.

    Note: album_art_url is typically not in the text response, so we leave it
    empty here. The _music_animation will fetch real data from the Spotify API.
    """
    context = {
        "track": "",
        "artist": "",
        "album": "",
        "album_art_url": "",  # Will be fetched from Spotify API by _music_animation
        "progress": 0,
        "duration": 0,
        "is_playing": True,
    }

    if "paused" in response.lower():
        context["is_playing"] = False

    # Try to extract track name from quoted text
    track_match = re.search(r"['\"]([^'\"]+)['\"]", response)
    if track_match:
        context["track"] = track_match.group(1)

    # Try to extract artist name
    by_match = re.search(r"by\s+([^'\"\.]+?)(?:\.|,|$)", response)
    if by_match:
        context["artist"] = by_match.group(1).strip()

    # Try alternative patterns for "Playing X by Y" format
    if not context["track"]:
        playing_match = re.search(r"[Pp]laying\s+(.+?)\s+by\s+", response)
        if playing_match:
            context["track"] = playing_match.group(1).strip()

    return context


def _parse_lights_context(query: str, response: str) -> Dict[str, Any]:
    context = {"lights": [], "action": "on", "color": "", "brightness": 100}

    if any(w in query.lower() for w in ["off", "turn off"]):
        context["action"] = "off"

    colors = [
        "red",
        "green",
        "blue",
        "yellow",
        "orange",
        "purple",
        "white",
        "cyan",
        "pink",
        "warm",
        "cool",
    ]
    for color in colors:
        if color in query.lower():
            context["color"] = color
            break

    brightness_match = re.search(r"(\d+)\s*%?", query)
    if brightness_match and "brightness" in query.lower():
        context["brightness"] = int(brightness_match.group(1))

    return context


def _parse_calendar_context(response: str) -> Dict[str, Any]:
    context = {"events": [], "action": "list"}

    if "created" in response.lower() or "added" in response.lower():
        context["action"] = "create"
    elif "deleted" in response.lower() or "removed" in response.lower():
        context["action"] = "delete"

    return context


def _parse_todo_context(response: str) -> Dict[str, Any]:
    context = {"items": [], "action": "list"}

    if "added" in response.lower() or "created" in response.lower():
        context["action"] = "add"
    elif "completed" in response.lower() or "done" in response.lower():
        context["action"] = "complete"
    elif "deleted" in response.lower() or "removed" in response.lower():
        context["action"] = "delete"

    return context


async def show_tool_display(user_query: str, response: str, display_manager) -> None:
    """Show tool-specific animation on the display.

    Note: User message is already shown by app.py before this is called,
    so we don't need to show it again here.
    """
    if not display_manager or not display_manager.is_available:
        return

    from .base import DisplayMode

    if display_manager.mode != DisplayMode.SMART:
        return

    tool_name, context = parse_tool_context(user_query, response)

    if tool_name:
        # Only show tool animation - user message is already displayed by app.py
        await display_manager.show_tool_animation(tool_name, context, None)
    # If no tool was detected, app.py will call show_response_display instead


async def show_response_display(response: str, display_manager) -> None:
    if not display_manager or not display_manager.is_available:
        return

    from .base import DisplayMode

    if display_manager.mode != DisplayMode.SMART:
        return

    await display_manager.show_response_animation(response)
