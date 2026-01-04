from langchain_core.tools import tool
from .env_utils import get_env
import aiohttp
import subprocess


@tool
async def spotify_tool(command: str) -> str:
    """Control Spotify playback.
    
    Args:
        command: Spotify command like "play music", "next song", "pause", 
                "play [artist/song]", "play my playlist"
    
    Returns:
        Status message about the action taken
    """
    client_id = get_env("SPOTIFY_CLIENT_ID")
    client_secret = get_env("SPOTIFY_CLIENT_SECRET")
    
    if not client_id or not client_secret:
        return "Spotify is not configured. Please add your Spotify credentials in settings."
    
    try:
        ip = subprocess.run(
            ["hostname", "-I"], 
            capture_output=True, 
            text=True
        ).stdout.split()[0]
        
        async with aiohttp.ClientSession() as session:
            response = await session.post(
                f"http://{ip}/spotify-control",
                json={"text": command}
            )
            
            if response.status == 200:
                data = await response.json()
                return data.get("message", "Spotify command executed.")
            else:
                text = await response.text()
                return f"Spotify request failed: {text}"
                
    except Exception as e:
        return f"Error controlling Spotify: {str(e)}"
