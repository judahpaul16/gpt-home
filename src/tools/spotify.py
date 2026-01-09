"""
Spotify tool for GPT Home.
Controls Spotify playback via the backend's spotify-control endpoint.
Uses Client Credentials for search and MPRIS/D-Bus for local playback control.
"""

import aiohttp
from langchain_core.tools import tool

from .env_utils import get_host_ip


@tool
async def spotify_tool(command: str) -> str:
    """Control Spotify playback - play music, pause, skip, search for songs.

    Use this tool when users want to:
    - Play a specific song, artist, album, or playlist
    - Control playback (pause, resume, skip, previous)
    - Search for music
    - Adjust volume or enable shuffle/repeat

    Args:
        command: The Spotify command. Examples:
            - "play Shape of You by Ed Sheeran"
            - "play songs by Taylor Swift"
            - "play my liked songs"
            - "pause" or "stop"
            - "next" or "skip"
            - "previous"
            - "volume 50"
            - "shuffle on"
    Returns:
        Status message about what action was taken or an error message

    """

    # Trigger spotify animation on display
    try:
        from common import show_tool_animation

        await show_tool_animation("spotify", {"command": command})
    except Exception:
        pass
    command = command.strip()
    if not command:
        return "Please specify what you'd like to do with Spotify, like 'play some music' or 'pause'."

    try:
        ip = get_host_ip()
        url = f"http://{ip}/spotify-control"
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            try:
                response = await session.post(url, json={"text": command})
            except aiohttp.ServerTimeoutError:
                return (
                    "The Spotify request timed out. "
                    "The service might be busy - please try again."
                )
            if response.status == 200:
                data = await response.json()
                message = data.get("message", "Done.")
                return message
            elif response.status == 400:
                data = await response.json()
                error_msg = data.get("message", "Invalid command")
                return error_msg
            elif response.status == 404:
                return (
                    "I couldn't find that song or artist on Spotify. "
                    "Try being more specific or check the spelling."
                )
            elif response.status == 503:
                return (
                    "Spotify service is temporarily unavailable. "
                    "Please try again in a moment."
                )
            else:
                text = await response.text()
                return f"Spotify returned an error (status {response.status}): {text[:100]}"
    except aiohttp.ClientError as e:
        return f"Network error while contacting Spotify: {str(e)}"

    except Exception as e:
        return f"Something went wrong with Spotify: {str(e)}"
