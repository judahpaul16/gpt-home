from langchain_core.tools import tool
from typing import Optional, Tuple
from datetime import datetime, timedelta
from .env_utils import get_env
from common import logger
import aiohttp
import re

# Cache for IP-based location (avoid repeated lookups)
_location_cache: dict = {}

WEATHER_CODES = {
    "0": {"day": {"description": "Sunny"}, "night": {"description": "Clear"}},
    "1": {"day": {"description": "Mainly Sunny"}, "night": {"description": "Mainly Clear"}},
    "2": {"day": {"description": "Partly Cloudy"}, "night": {"description": "Partly Cloudy"}},
    "3": {"day": {"description": "Cloudy"}, "night": {"description": "Cloudy"}},
    "45": {"day": {"description": "Foggy"}, "night": {"description": "Foggy"}},
    "48": {"day": {"description": "Rime Fog"}, "night": {"description": "Rime Fog"}},
    "51": {"day": {"description": "Light Drizzle"}, "night": {"description": "Light Drizzle"}},
    "53": {"day": {"description": "Drizzle"}, "night": {"description": "Drizzle"}},
    "55": {"day": {"description": "Heavy Drizzle"}, "night": {"description": "Heavy Drizzle"}},
    "61": {"day": {"description": "Light Rain"}, "night": {"description": "Light Rain"}},
    "63": {"day": {"description": "Rain"}, "night": {"description": "Rain"}},
    "65": {"day": {"description": "Heavy Rain"}, "night": {"description": "Heavy Rain"}},
    "71": {"day": {"description": "Light Snow"}, "night": {"description": "Light Snow"}},
    "73": {"day": {"description": "Snow"}, "night": {"description": "Snow"}},
    "75": {"day": {"description": "Heavy Snow"}, "night": {"description": "Heavy Snow"}},
    "80": {"day": {"description": "Light Showers"}, "night": {"description": "Light Showers"}},
    "81": {"day": {"description": "Showers"}, "night": {"description": "Showers"}},
    "82": {"day": {"description": "Heavy Showers"}, "night": {"description": "Heavy Showers"}},
    "95": {"day": {"description": "Thunderstorm"}, "night": {"description": "Thunderstorm"}},
}


async def _get_coords_from_city(city: str, api_key: Optional[str] = None) -> Optional[dict]:
    """Get coordinates from city name."""
    async with aiohttp.ClientSession() as session:
        if api_key:
            response = await session.get(
                f"http://api.openweathermap.org/geo/1.0/direct?q={city}&appid={api_key}"
            )
            if response.status == 200:
                data = await response.json()
                if data:
                    return {"lat": data[0]["lat"], "lon": data[0]["lon"]}
        
        response = await session.get(
            f"https://nominatim.openstreetmap.org/search?q={city}&format=json",
            headers={"User-Agent": "GPT-Home/1.0"}
        )
        if response.status == 200:
            data = await response.json()
            if data:
                return {"lat": float(data[0]["lat"]), "lon": float(data[0]["lon"])}
    
    return None


async def _get_city_from_ip() -> Optional[str]:
    """Get city from IP address using multiple fallback services."""
    global _location_cache
    
    # Check cache first (valid for 1 hour)
    if "city" in _location_cache:
        cache_time = _location_cache.get("timestamp", datetime.min)
        if datetime.now() - cache_time < timedelta(hours=1):
            logger.debug(f"Using cached location: {_location_cache['city']}")
            return _location_cache["city"]
    
    # Also check settings for a default location
    default_location = get_env("DEFAULT_LOCATION")
    if default_location:
        logger.debug(f"Using DEFAULT_LOCATION from env: {default_location}")
        return default_location
    
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
        # Try multiple IP geolocation services
        services = [
            ("https://ipapi.co/json/", lambda d: d.get("city")),
            ("https://ipinfo.io/json", lambda d: d.get("city")),
            ("https://ip-api.com/json/", lambda d: d.get("city")),
            ("https://ipwho.is/", lambda d: d.get("city")),
        ]
        
        for url, extract_city in services:
            try:
                response = await session.get(url)
                if response.status == 200:
                    data = await response.json()
                    city = extract_city(data)
                    if city:
                        # Cache the result
                        _location_cache["city"] = city
                        _location_cache["timestamp"] = datetime.now()
                        logger.info(f"Detected location from IP: {city}")
                        return city
            except Exception as e:
                logger.debug(f"IP geolocation failed for {url}: {e}")
                continue
    
    logger.warning("All IP geolocation services failed")
    return None


async def _get_weather_data(lat: float, lon: float, api_key: Optional[str] = None) -> dict:
    """Fetch weather data from API."""
    async with aiohttp.ClientSession() as session:
        if api_key:
            response = await session.get(
                f"https://api.openweathermap.org/data/3.0/onecall?"
                f"lat={lat}&lon={lon}&appid={api_key}&units=imperial"
            )
            if response.status == 200:
                return await response.json()
        
        response = await session.get(
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}&current_weather=true&temperature_unit=fahrenheit"
        )
        if response.status == 200:
            return await response.json()
    
    return {}


@tool
async def weather_tool(query: str) -> str:
    """Get current weather or forecast for a location.
    
    Args:
        query: Weather query like "weather in New York" or "what's the temperature"
    
    Returns:
        Weather information string
    """
    api_key = get_env("OPEN_WEATHER_API_KEY")
    
    # Try to extract city from query
    city_match = re.search(r'(?:in|for|at)\s+([\w\s,]+?)(?:\?|$|today|tomorrow|this|next)', query, re.IGNORECASE)
    city = city_match.group(1).strip().rstrip(',') if city_match else None
    
    # If no city specified, try IP geolocation
    if not city:
        city = await _get_city_from_ip()
        if not city:
            return ("I couldn't determine your location automatically. "
                    "You can set DEFAULT_LOCATION in your .env file, or ask like "
                    "'What's the weather in New York?'")
        logger.info(f"Using IP-detected location: {city}")
    
    coords = await _get_coords_from_city(city, api_key)
    if not coords:
        return f"I couldn't find weather data for {city}."
    
    data = await _get_weather_data(coords["lat"], coords["lon"], api_key)
    
    if not data:
        return f"I couldn't retrieve weather data for {city}."
    
    if "current" in data:
        weather = data["current"]["weather"][0]["main"]
        temp = round(data["current"]["temp"])
        return f"It's currently {temp}°F and {weather.lower()} in {city}."
    elif "current_weather" in data:
        weather_code = str(data["current_weather"].get("weathercode", "0"))
        temp = round(data["current_weather"]["temperature"])
        is_day = datetime.now().hour < 18
        weather_info = WEATHER_CODES.get(weather_code, WEATHER_CODES["0"])
        description = weather_info["day" if is_day else "night"]["description"]
        return f"It's currently {temp}°F and {description.lower()} in {city}."
    
    return f"Weather data for {city} is not available in the expected format."
