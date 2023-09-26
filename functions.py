from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from dotenv import load_dotenv
from dotenv.main import set_key
import speech_recognition as sr
from asyncio import create_task
from dotenv import load_dotenv
from board import SCL, SDA
from phue import Bridge
import adafruit_ssd1306
import subprocess
import traceback
import datetime
import textwrap
import requests
import logging
import asyncio
import pyttsx3
import aiohttp
import base64
import string
import struct
import openai
import busio
import json
import time
import os
import re

# Load .env file
load_dotenv(dotenv_path='gpt-web/.env')

# Add a new 'SUCCESS' logging level
logging.SUCCESS = 25  # Between INFO and WARNING
logging.addLevelName(logging.SUCCESS, "SUCCESS")

def success(self, message, *args, **kws):
    if self.isEnabledFor(logging.SUCCESS):
        self._log(logging.SUCCESS, message, args, **kws)

logging.Logger.success = success

logging.basicConfig(filename='events.log', level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize the speech recognition engine
r = sr.Recognizer()
openai.api_key = os.environ['OPENAI_API_KEY']
executor = ThreadPoolExecutor()

# Initialize the text-to-speech engine
engine = pyttsx3.init()
# Set properties
engine.setProperty('rate', 145)
engine.setProperty('volume', 1.0)
# Direct audio to specific hardware
engine.setProperty('alsa_device', 'hw:Headphones,0')
speak_lock = asyncio.Lock()
display_lock = asyncio.Lock()

HOSTNAME = os.environ['HOSTNAME']

def network_connected():
    return os.system("ping -c 1 google.com") == 0

# Manually draw a degree symbol °
def degree_symbol(display, x, y, radius, color):
    for i in range(x-radius, x+radius+1):
        for j in range(y-radius, y+radius+1):
            if (i-x)**2 + (j-y)**2 <= radius**2:
                display.pixel(i, j, color)
                # clear center of circle
                if (i-x)**2 + (j-y)**2 <= (radius-1)**2:
                    display.pixel(i, j, 0)

async def calculate_delay(message):
    base_delay = 0.02
    extra_delay = 0.0
    
    # Patterns to look for
    patterns = [r": ", r"\. ", r"\? ", r"! ", r"\.{2,}", r", ", r"\n"]
    
    for pattern in patterns:
        extra_delay += (len(re.findall(pattern, message)) * 0.001)  # Add 0.001 seconds for each match

    return base_delay + extra_delay

def initLCD():
    # Create the I2C interface.
    i2c = busio.I2C(SCL, SDA)
    # Create the SSD1306 OLED class.
    # The first two parameters are the pixel width and pixel height. Change these
    # to the right size for your display
    display = adafruit_ssd1306.SSD1306_I2C(128, 32, i2c)
    # Alternatively, you can change the I2C address of the device with an addr parameter:
    # display = adafruit_ssd1306.SSD1306_I2C(128, 32, i2c, addr=0x31)
    # Set the display rotation to 180 degrees.
    display.rotation = 2
    # Clear the display. Always call show after changing pixels to make the display
    # update visible
    display.fill(0)
    # Display IP address
    ip_address = subprocess.check_output(["hostname", "-I"]).decode("utf-8").split(" ")[0]
    display.text(f"{ip_address}", 0, 0, 1)
    # Display CPU temperature in Celsius (e.g., 39°)
    cpu_temp = int(float(subprocess.check_output(["vcgencmd", "measure_temp"]).decode("utf-8").split("=")[1].split("'")[0]))
    temp_text_x = 100
    display.text(f"{cpu_temp}", temp_text_x, 0, 1)
    # degree symbol
    degree_x = 100 + len(f"{cpu_temp}") * 7 # Assuming each character is 7 pixels wide
    degree_y = 2
    degree_symbol(display, degree_x, degree_y, 2, 1)
    c_x = degree_x + 7 # Assuming each character is 7 pixels wide
    display.text("C", c_x, 0, 1)

    # Show the updated display with the text.
    display.show()
    return display

async def initialize_system():
    display = initLCD()
    stop_event_init = asyncio.Event()
    state_task = asyncio.create_task(display_state("Connecting", display, stop_event_init))
    while not network_connected():
        await asyncio.sleep(1)
        message = "Network not connected. Retrying..."
        logger.info(message)
    stop_event_init.set()  # Signal to stop the 'Connecting' display
    state_task.cancel()  # Cancel the display task
    display = initLCD()  # Reinitialize the display
    return display

def load_settings():
    settings_path = "settings.json"
    with open(settings_path, "r") as f:
        settings = json.load(f)
        return settings

async def updateLCD(text, display, stop_event=None, delay=0.02):
    async with display_lock:
        if stop_event is None:
            stop_event = asyncio.Event()

        async def display_text(delay):
            i = 0
            while not (stop_event and stop_event.is_set()) and i < line_count:
                if line_count > 2:
                    await display_lines(i, min(i + 2, line_count), delay)
                    i += 2
                else:
                    await display_lines(0, line_count, delay)
                    break  # Exit the loop if less than or equal to 2 lines
                await asyncio.sleep(0.02)  # Delay between pages

        async def display_lines(start, end, delay):
            display.fill_rect(0, 10, 128, 22, 0)
            # type out the text
            for i, line_index in enumerate(range(start, end)):
                for j, char in enumerate(lines[line_index]):
                    if stop_event.is_set():
                        break
                    try:
                        display.text(char, j * 6, 10 + i * 10, 1)
                    except struct.error as e:
                        logger.error(f"Struct Error: {e}, skipping character {char}")
                        continue  # Skip the current character and continue with the next
                    display.show()
                    await asyncio.sleep(delay)

        # Clear the display
        display.fill(0)
        # Display IP address
        ip_address = subprocess.check_output(["hostname", "-I"]).decode("utf-8").split(" ")[0]
        display.text(f"{ip_address}", 0, 0, 1)
        # Display CPU temperature in Celsius (e.g., 39°)
        cpu_temp = int(float(subprocess.check_output(["vcgencmd", "measure_temp"]).decode("utf-8").split("=")[1].split("'")[0]))
        temp_text_x = 100
        display.text(f"{cpu_temp}", temp_text_x, 0, 1)
        # degree symbol
        degree_x = 100 + len(f"{cpu_temp}") * 7 # Assuming each character is 7 pixels wide
        degree_y = 2
        degree_symbol(display, degree_x, degree_y, 2, 1)
        c_x = degree_x + 7 # Assuming each character is 7 pixels wide
        display.text("C", c_x, 0, 1)
        # Show the updated display with the text.
        display.show()
        # Line wrap the text
        lines = textwrap.fill(text, 21).split('\n')
        line_count = len(lines)
        display_task = asyncio.create_task(display_text(delay))

async def listen(display, state_task, stop_event):
    loop = asyncio.get_running_loop()

    def recognize_audio(loop, state_task, stop_event):
        try:
            with sr.Microphone() as source:
                if source.stream is None:
                    raise Exception("Microphone not initialized.")
                
                listening = False  # Initialize variable for feedback
                
                try:
                    audio = r.listen(source, timeout=2, phrase_time_limit=15)
                    text = r.recognize_google(audio)
                    
                    if text:  # If text is found, break the loop
                        state_task.cancel()
                        return text
                        
                except sr.WaitTimeoutError:
                    if listening:
                        logger.info("Still listening but timed out, waiting for phrase...")
                    else:
                        logger.info("Timed out, waiting for phrase to start...")
                        listening = True
                        
                except sr.UnknownValueError:
                    logger.info("Could not understand audio, waiting for a new phrase...")
                    listening = False
                        
        except sr.WaitTimeoutError:
            if source and source.stream:
                source.stream.close()
            raise asyncio.TimeoutError("Listening timed out.")

    text = await loop.run_in_executor(executor, recognize_audio, loop, state_task, stop_event)
    return text

async def display_state(state, display, stop_event):
    async with display_lock:
        # if state 'Connecting', display the 'No Network' and CPU temperature
        if state == "Connecting":
            display.text("No Network", 0, 0, 1)
            # Display CPU temperature in Celsius (e.g., 39°)
            cpu_temp = int(float(subprocess.check_output(["vcgencmd", "measure_temp"]).decode("utf-8").split("=")[1].split("'")[0]))
            temp_text_x = 100
            display.text(f"{cpu_temp}", temp_text_x, 0, 1)
            # degree symbol
            degree_x = 100 + len(f"{cpu_temp}") * 7 # Assuming each character is 7 pixels wide
            degree_y = 2
            degree_symbol(display, degree_x, degree_y, 2, 1)
            c_x = degree_x + 7 # Assuming each character is 7 pixels wide
            display.text("C", c_x, 0, 1)
            # Show the updated display with the text.
            display.show()
        while not stop_event.is_set():
            for i in range(4):
                if stop_event.is_set():
                    break
                display.fill_rect(0, 10, 128, 22, 0)
                display.text(f"{state}" + '.' * i, 0, 20, 1)
                display.show()
                await asyncio.sleep(0.5)

async def speak(text, stop_event=asyncio.Event()):
    async with speak_lock:
        loop = asyncio.get_running_loop()
        def _speak():
            engine.say(text)
            engine.runAndWait()
        await loop.run_in_executor(executor, _speak)
        stop_event.set()

async def spotify_action(text: str):
    client_id = os.getenv('SPOTIFY_CLIENT_ID')
    client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
    if client_id and client_secret:
        try:
            async with aiohttp.ClientSession() as session:
                ip = subprocess.run(["hostname", "-I"], capture_output=True).stdout.decode().strip()
                response = await session.post(f"http://{ip}/spotify-control", json={"text": text})
                if response.status == 200:
                    return await response.text()
                else:
                    logger.warning(f"Received a {response.status} status code.")
                    return f"Received a {response.status} status code."
        except Exception as e:
            logger.error(f"Error: {traceback.format_exc()}")
            raise Exception(f"Something went wrong: {e}")
    raise Exception("No client id or client secret found. Please provide the necessary credentials for Spotify in the web interface.")

# Open Weather Helper Functions
async def coords_from_city(city, api_key):
    async with aiohttp.ClientSession() as session:
        response = await session.get(f"http://api.openweathermap.org/geo/1.0/direct?q={city}&appid={api_key}")
        if response.status == 200:
            json_response = await response.json()
            coords = {
                "lat": json_response[0].get('lat'),
                "lon": json_response[0].get('lon')
            }
            return coords
    
async def city_from_ip():
    async with aiohttp.ClientSession() as session:
        response = await session.get(f"https://ipinfo.io/json")
        if response.status == 200:
            json_response = await response.json()
            city = json_response.get('city')
            return city

async def open_weather_action(text: str):
    try:
        api_key = os.getenv('OPEN_WEATHER_API_KEY')
        if api_key:
            async with aiohttp.ClientSession() as session:
                if re.search(r'(weather|temperature).*\sin\s', text, re.IGNORECASE):
                    city_match = re.search(r'in\s([\w\s]+)', text, re.IGNORECASE)
                    if city_match:
                        city = city_match.group(1).strip()

                    # Current weather
                    if not re.search(r'(forecast|future)', text, re.IGNORECASE):
                        coords = await coords_from_city(city, api_key)
                        response = await session.get(f"https://api.openweathermap.org/data/3.0/onecall?lat={coords.get('lat')}&lon={coords.get('lon')}&appid={api_key}&units=imperial")
                        if response.status == 200:
                            json_response = await response.json()
                            logger.debug(json_response)
                            weather = json_response.get('current').get('weather')[0].get('main')
                            temp = json_response.get('current').get('temp')
                            return f"It is currently {round(float(temp))} degrees and {weather.lower()} in {city}."
                        else:
                            raise Exception(f"Received a {response.status} status code. {response.content.decode()}")

                    # Weather forecast
                    else:
                        coords = await coords_from_city(city, api_key)
                        tomorrow = datetime.now() + timedelta(days=1)
                        response = await session.get(f"https://api.openweathermap.org/data/3.0/onecall?lat={coords.get('lat')}&lon={coords.get('lon')}&appid={api_key}&units=imperial")
                        if response.status == 200:
                            json_response = await response.json()
                            # next few days
                            forecast = []
                            for day in json_response.get('daily'):
                                forecast.append({
                                    'weather': day.get('weather')[0].get('main'),
                                    'temp': day.get('temp').get('day'),
                                    'date': datetime.fromtimestamp(day.get('dt')).strftime('%A')
                                })
                            # tomorrow
                            tomorrow_forecast = list(filter(lambda x: x.get('date') == tomorrow.strftime('%A'), forecast))[0]
                            speech_responses = []
                            speech_responses.append(f"Tomorrow, it will be {tomorrow_forecast.get('temp')}°F and {tomorrow_forecast.get('weather')} in {city}.")
                            for day in forecast:
                                if day.get('date') != tomorrow.strftime('%A'):
                                    speech_responses.append(f"On {day.get('date')}, it will be {round(float(day.get('temp')))} degrees and {day.get('weather').lower()} in {city}.")
                            return ' '.join(speech_responses)
                else:
                    # General weather based on IP address location
                    city = await city_from_ip()
                    coords = await coords_from_city(city, api_key)
                    response = await session.get(f"http://api.openweathermap.org/data/3.0/onecall?lat={coords.get('lat')}&lon={coords.get('lon')}&appid={api_key}&units=imperial")
                    if response.status == 200:
                        json_response = await response.json()
                        logger.debug(json_response)
                        weather = json_response.get('current').get('weather')[0].get('main')
                        temp = json_response.get('current').get('temp')
                        return f"It is currently {round(float(temp))} degrees and {weather.lower()} in your location."
                    else:
                        content = await response.content.read()
                        raise Exception(f"Received a {response.status} status code. {content.decode()}")
                    
            raise Exception("I'm sorry, I don't know how to handle that request.")

        raise Exception("No Open Weather API key found. Please enter your API key for Open Weather in the web interface or try reconnecting the service.")

    except Exception as e:
        if '404' in str(e):
            return f"Weather information for {city} is not available."
        else:
            logger.error(f"Error: {traceback.format_exc()}")
            return f"Something went wrong. {e}"

async def philips_hue_action(text: str):
    bridge_ip = os.getenv('PHILIPS_HUE_BRIDGE_IP')
    username = os.getenv('PHILIPS_HUE_USERNAME')
    
    if bridge_ip and username:
        try:
            b = Bridge(bridge_ip, username)
            b.connect()

            # Turn on or off all lights
            on_off_pattern = r'(\b(turn|shut|cut|put)\s)?.*(on|off)\b'
            match = re.search(on_off_pattern, text, re.IGNORECASE)
            if match:
                if 'on' in match.group(0):
                    b.set_group(0, 'on', True)
                    return "Turning on all lights."
                else:
                    b.set_group(0, 'on', False)
                    return "Turning off all lights."

            # Change light color
            color_pattern = r'\b(red|green|blue|yellow|purple|orange|pink|white|black)\b'
            match = re.search(color_pattern, text, re.IGNORECASE)
            if match:
                # convert color to hue value
                color = {
                    'red': 0,
                    'green': 25500,
                    'blue': 46920,
                    'yellow': 12750,
                    'purple': 56100,
                    'orange': 6000,
                    'pink': 56100,  # Closest to purple for hue
                    'white': 15330,  # Closest to a neutral white
                }.get(match.group(1).lower())
                b.set_group(0, 'on', True)
                b.set_group(0, 'hue', color)
                return f"Changing lights {match.group(1)}."

            # Change light brightness
            brightness_pattern = r'(\b(dim|brighten)\b)?.*?\s.*?to\s(\d{1,3})\b'
            match = re.search(brightness_pattern, text, re.IGNORECASE)
            if match:
                brightness = int(match.group(3))
                b.set_group(0, 'on', True)
                b.set_group(0, 'bri', brightness)
                return f"Setting brightness to {brightness}."

            raise Exception("I'm sorry, I don't know how to handle that request.")
        except Exception as e:
            logger.error(f"Error: {traceback.format_exc()}")
            return f"Something went wrong: {e}"
    
    raise Exception("No philips hue bridge IP found. Please enter your bridge IP for Phillips Hue in the web interface or try reconnecting the service.")

async def query_openai(text, display, retries=3):
    # Load settings from settings.json
    settings = load_settings()
    max_tokens = settings.get("max_tokens")
    temperature = settings.get("temperature")

    for i in range(retries):
        try:
            response = openai.ChatCompletion.create(
                model=settings.get("model"),
                messages=[
                    {"role": "system", "content": f"You are a helpful assistant. {settings.get('custom_instructions')}"},
                    {"role": "user", "content": f"Human: {text}\nAI:"}
                ],
                max_tokens=max_tokens,
                temperature=temperature
            )
            response_content = response['choices'][0]['message']['content'].strip()
            if response_content:  # Check if the response is not empty
                message = f"Response: {response_content}"
                return message
            else:
                logger.warning(f"Retry {i+1}: Received empty response from OpenAI.")
        except Exception as e:
            logger.error(f"Error on try {i+1}: {e}")
            if i == retries - 1:  # If this was the last retry
                error_message = f"Something went wrong after {retries} retries: {e}"
                handle_error(error_message, None, display)
        await asyncio.sleep(0.5)  # Wait before retrying

async def action_router(text: str, display):
    # For Spotify actions
    if re.search(r'\b(play|resume|next song|go back|pause|stop)(\s.*)?(\bon\b\sSpotify)?\b', text, re.IGNORECASE):
        return await spotify_action(text)
        
    # For Open Weather actions
    elif re.search(r'\b(weather|forecast|temperature)\b.*\b(in|for|at)?\b(\w+)?', text, re.IGNORECASE) or \
        re.search(r'\b(is|will)\sit\b.*\b(hot|cold|rain(ing|y)?|sun(ny|ning)?|cloud(y|ing)?|wind(y|ing)?|storm(y|ing)?|snow(ing)?)\b', text, re.IGNORECASE):
        return await open_weather_action(text)

    # For Philips Hue actions
    elif re.search(r'\b(turn)?\b(\son|\soff)?.*\slight(s)?(\son|\soff)?\b', text, re.IGNORECASE):
        return await philips_hue_action(text)
        
    # If no pattern matches, query OpenAI
    else:
        return await query_openai(text, display)

async def handle_error(message, state_task, display):
    if state_task: 
        state_task.cancel()
    delay = await calculate_delay(message)
    stop_event = asyncio.Event()
    lcd_task = asyncio.create_task(updateLCD(message, display, stop_event=stop_event, delay=delay))
    speak_task = asyncio.create_task(speak(message, stop_event))
    await speak_task
    lcd_task.cancel()
    logger.critical(f"An error occurred: {message}\n{traceback.format_exc()}")