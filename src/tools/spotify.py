"""
Spotify tool for GPT Home.
Controls Spotify playback via the backend's spotify-control endpoint.
Uses Web API with hybrid authentication:
- Client Credentials for search (no user auth required)
"""

from typing import Optional

import aiohttp
from langchain_core.tools import tool

from .env_utils import get_host_ip


@tool
async def spotify_tool(
    command: str,
    search_type: Optional[str] = None,
    query: Optional[str] = None,
) -> str:
    """Control Spotify playback - play music, pause, skip, search for songs.

    Use this tool when users want to:
    - Play a specific song, artist, album, or playlist
    - Control playback (pause, resume, skip, previous)
    - Search for music
    - Adjust volume or enable shuffle/repeat

    IMPORTANT for search_type selection:
    - When user says "play the album X" or "play X album" -> use search_type="album"
    - When user mentions an album title (like "The Forever Story", "1989", "God Does Like Ugly") -> use search_type="album"
    - When user wants to hear a specific artist's music -> use search_type="artist"
    - When user asks for a specific song by name -> use search_type="track"
    - If unsure and it sounds like an album title (proper noun, multi-word), prefer search_type="album"

    Args:
        command: The action to perform. For playback control use:
            - "play" (with query and search_type for playing music)
            - "pause" or "stop"
            - "next" or "skip"
            - "previous"
            - "volume 50"
            - "shuffle on"
        search_type: Required when command is "play". Specifies what to search for:
            - "album" - Play ALL tracks from an album in order (use when user says "album" or mentions an album title)
            - "artist" - Play top tracks by an artist (e.g., "JID", "Taylor Swift")
            - "track" - Play a single specific song (e.g., "Surround Sound", "Shape of You")
            - "playlist" - Play a playlist
            - "show" - Play a podcast/show
        query: Required when command is "play". The search query:
            - For album: just the album name (e.g., "The Forever Story", "1989", "God Does Like Ugly")
            - For artist: just the artist name (e.g., "JID", "Kendrick Lamar")
            - For track: "song name" or "song name by artist" (e.g., "Surround Sound by JID")

    Returns:
        Status message about what action was taken or an error message

    Examples:
        - Play album: command="play", search_type="album", query="The Forever Story"
        - Play album: command="play", search_type="album", query="God Does Like Ugly"
        - Play artist: command="play", search_type="artist", query="JID"
        - Play song: command="play", search_type="track", query="Surround Sound by JID"
        - Pause: command="pause"
        - Skip: command="next"
    """

    # Trigger spotify animation on display
    try:
        from common import show_tool_animation

        await show_tool_animation("spotify", {"command": command})
    except Exception:
        pass

    command = command.strip().lower() if command else ""
    if not command:
        return "Please specify what you'd like to do with Spotify, like 'play some music' or 'pause'."

    try:
        ip = get_host_ip()
        url = f"http://{ip}/spotify-control"
        timeout = aiohttp.ClientTimeout(total=15)

        # Build request payload
        payload = {"command": command}
        if search_type:
            payload["search_type"] = search_type
        if query:
            payload["query"] = query

        async with aiohttp.ClientSession(timeout=timeout) as session:
            try:
                response = await session.post(url, json=payload)
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
            elif response.status == 401:
                data = await response.json()
                error_msg = data.get("message", "Authentication required")
                return (
                    f"{error_msg} "
                    "Please authenticate at your GPT Home web interface settings page, or ask an admin to visit /spotify-auth"
                )
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
