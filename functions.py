from concurrent.futures import ThreadPoolExecutor
import speech_recognition as sr
from asyncio import create_task
from dotenv import load_dotenv
from board import SCL, SDA
from phue import Bridge
import adafruit_ssd1306
import subprocess
import traceback
import textwrap
import logging
import asyncio
import pyttsx3
import aiohttp
import string
import struct
import openai
import busio
import json
import time
import os
import re

HOSTNAME = os.environ['HOSTNAME']

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

async def speak(text, stop_event):
    async with speak_lock:
        loop = asyncio.get_running_loop()
        def _speak():
            engine.say(text)
            engine.runAndWait()
        await loop.run_in_executor(executor, _speak)
        stop_event.set()

async def get_device_id(device_name='ubuntu', headers=None):
    async with aiohttp.ClientSession() as session:
        async with session.get("https://api.spotify.com/v1/me/player/devices", headers=headers) as r:
            devices_data = await r.text()
            devices_json = json.loads(devices_data)
            for device in devices_json['devices']:
                if device['name'] == device_name:
                    return device['id']
    return None

async def spotify_action(text: str):
    access_token = os.getenv('SPOTIFY_ACCESS_TOKEN')
    headers = {"Authorization": f"Bearer {access_token}"}

    raspberry_pi_device_id = await get_device_id(HOSTNAME, headers)

    if raspberry_pi_device_id is None:
        return "Device 'ubuntu' not found."

    if access_token:
        try:
            async with aiohttp.ClientSession() as session:
                if "play" in text:
                    song = text.split("play", 1)[1].strip()
                    payload = {"device_id": raspberry_pi_device_id}  
                    if song:
                        if re.search(r'(a\s)?(song|track|music)?', song, re.IGNORECASE):
                            await session.put("https://api.spotify.com/v1/me/player/play", json=payload, headers=headers)
                        else:
                            payload["uris"] = [f"spotify:track:{song}"]
                            await session.put("https://api.spotify.com/v1/me/player/play", json=payload, headers=headers)
                            return f"Playing {song} on Spotify."
                    else:
                        await session.put("https://api.spotify.com/v1/me/player/play", json=payload, headers=headers)
                    return ""
                elif "next song" in text:
                    await session.post("https://api.spotify.com/v1/me/player/next", json={"device_id": raspberry_pi_device_id}, headers=headers)
                    return "Playing next song."
                elif "go back" in text:
                    await session.post("https://api.spotify.com/v1/me/player/previous", json={"device_id": raspberry_pi_device_id}, headers=headers)
                    return "Going back."
                elif "pause" in text or "stop" in text:
                    await session.put("https://api.spotify.com/v1/me/player/pause", json={"device_id": raspberry_pi_device_id}, headers=headers)
                    return ""
        except Exception as e:
            logger.error(f"Error: {traceback.format_exc()}")
            return f"Something went wrong: {e}"
    raise Exception("No access token found. Please enter your access token for Spotify in the web interface.")

async def google_calendar_action(text: str):
    access_token = os.getenv['GOOGLE_CALENDAR_ACCESS_TOKEN']
    headers = {"Authorization": f"Bearer {access_token}"}

    if access_token:
        try:
            async with aiohttp.ClientSession() as session:
                if re.search(r'(schedule|set).*meeting', text, re.IGNORECASE):
                    # Parse the meeting details from `text` or through some dialog
                    meeting_details = {...}  # Add meeting details here
                    await session.post("https://www.googleapis.com/calendar/v3/calendars/primary/events", json=meeting_details, headers=headers)
                    return "Scheduled a meeting."
                elif re.search(r'(delete|remove|cancel).*event', text, re.IGNORECASE):
                    # Parse the event ID from `text` or through some dialog
                    event_id = "YOUR_EVENT_ID"
                    await session.delete(f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}", headers=headers)
                    return "Deleted an event."
        except Exception as e:
            logger.error(f"Error: {traceback.format_exc()}")
            return f"Something went wrong: {e}"
    raise Exception("No access token found. Please enter your access token for Google Calendar in the web interface.")

async def philips_hue_action(text: str):
    bridge_ip = os.getenv['PHILIPS_HUE_BRIDGE_IP']
    username = os.getenv['PHILIPS_HUE_USERNAME']

    if bridge_ip and username:
        try:
            b = Bridge(bridge_ip, username)
            b.connect()
            # turn on or off all lights
            if re.search(r'(turn)?(\son|\soff)?.*\slight(s)?(\son|\soff)?', text, re.IGNORECASE):
                if "on" in text:
                    b.set_group(0, 'on', True)
                    return "Turning on all lights."
                elif "off" in text:
                    b.set_group(0, 'on', False)
                    return "Turning off all lights."
                else:
                    return "Turning on all lights."
            elif re.search(r'(change|set).*\slight(s)?(\sto)?.*', text, re.IGNORECASE):
                # Parse the light ID and color from `text` or through some dialog
                light_id = text.split("light", 1)[1].split(" ", 1)[0].strip()
                color = text.split("to", 1)[1].strip()
                b.set_light(light_id, 'on', True)
                b.set_light(light_id, 'hue', color)
                return "Changing light color."
            elif re.search(r'(dim|brighten).*\slight(s)?(\sto)?.*', text, re.IGNORECASE):
                # Parse the light ID and brightness from `text` or through some dialog
                light_id = text.split("light", 1)[1].split(" ", 1)[0].strip()
                brightness = text.split("to", 1)[1].strip()
                b.set_light(light_id, 'on', True)
                b.set_light(light_id, 'bri', brightness)
                return "Changing light brightness."

        except Exception as e:
            logger.error(f"Error: {traceback.format_exc()}")
            return f"Something went wrong: {e}"
    raise Exception("No bridge IP or username found. Please enter your bridge IP and username for Phillips Hue in the web interface.")

async def query_openai(text, display, retries=3):
    stop_event = asyncio.Event()

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
    if re.search(r'(play|resume|next song|go back|pause|stop)(\s.)*(\son\sSpotify)*', text, re.IGNORECASE):
        return await spotify_action(text)
        
    # For Google Calendar actions
    elif re.search(r'(schedule.*meeting|delete.*event)(\s.)*(\son)*', text, re.IGNORECASE):
        return await google_calendar_action(text)

    # For Philips Hue actions
    elif re.search(r'(turn)?(\son|\soff)?.*\slight(s)?(\son|\soff)?', text, re.IGNORECASE):
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