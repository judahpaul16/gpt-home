from langchain_core.tools import tool
from typing import Literal
from .env_utils import get_env
import re


HUE_COLORS = {
    "red": 0,
    "green": 25500,
    "blue": 46920,
    "yellow": 12750,
    "purple": 56100,
    "orange": 6000,
    "pink": 56100,
    "white": 15330,
}


def _get_bridge():
    """Get Philips Hue bridge connection."""
    from phue import Bridge
    
    bridge_ip = get_env("PHILIPS_HUE_BRIDGE_IP")
    username = get_env("PHILIPS_HUE_USERNAME")
    
    if not bridge_ip or not username:
        return None
    
    bridge = Bridge(bridge_ip, username)
    bridge.connect()
    return bridge


@tool
def lights_tool(command: str) -> str:
    """Control Philips Hue smart lights.
    
    Args:
        command: Light command like "turn on lights", "turn off lights", 
                "dim lights to 50", "change lights to red", "set brightness to 80"
    
    Returns:
        Status message about the action taken
    """
    bridge = _get_bridge()
    
    if not bridge:
        return "Philips Hue is not configured. Please add your bridge IP and username in settings."
    
    command_lower = command.lower()
    
    on_off_match = re.search(r'(turn|switch|put).*(on|off)', command_lower)
    if on_off_match:
        is_on = "on" in on_off_match.group(0)
        bridge.set_group(0, "on", is_on)
        return f"Turning {'on' if is_on else 'off'} all lights."
    
    color_match = re.search(
        r'\b(red|green|blue|yellow|purple|orange|pink|white)\b', 
        command_lower
    )
    if color_match:
        color_name = color_match.group(1)
        hue_value = HUE_COLORS.get(color_name, HUE_COLORS["white"])
        bridge.set_group(0, "on", True)
        bridge.set_group(0, "hue", hue_value)
        return f"Changing lights to {color_name}."
    
    brightness_match = re.search(r'(\d{1,3})', command_lower)
    if brightness_match and any(word in command_lower for word in ["dim", "bright", "brightness"]):
        brightness = int(brightness_match.group(1))
        brightness = max(0, min(254, int(brightness * 254 / 100)))
        bridge.set_group(0, "on", True)
        bridge.set_group(0, "bri", brightness)
        return f"Setting brightness to {brightness_match.group(1)}%."
    
    return "I didn't understand that light command. Try 'turn on lights', 'set lights to blue', or 'dim lights to 50'."
