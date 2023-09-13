from concurrent.futures import ThreadPoolExecutor
import speech_recognition as sr
from asyncio import create_task
from board import SCL, SDA
import adafruit_ssd1306
import subprocess
import traceback
import textwrap
import logging
import asyncio
import pyttsx3
import struct
import openai
import busio
import time
import os

logging.basicConfig(filename='events.log', level=logging.DEBUG)

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

display = None
display_lock = asyncio.Lock()

# Manually draw a degree symbol °
def degree_symbol(display, x, y, radius, color):
    for i in range(x-radius, x+radius+1):
        for j in range(y-radius, y+radius+1):
            if (i-x)**2 + (j-y)**2 <= radius**2:
                display.pixel(i, j, color)
                # clear center of circle
                if (i-x)**2 + (j-y)**2 <= (radius-1)**2:
                    display.pixel(i, j, 0)

async def calculate_delay(message, rate):
    words = len(message.split())
    time_to_speak = (words / rate) * 60  # in seconds
    total_words = message.count(" ") + 1
    return (time_to_speak / total_words ) - 0.3

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
    global display  # Declare it global
    async with display_lock:  # Acquire lock
        display = initLCD()
        stop_event_init = asyncio.Event()
        state_task = asyncio.create_task(display_state("Initializing", display, stop_event_init))
        while not network_connected():
            await asyncio.sleep(1)
            message = "Network not connected. Retrying..."
            log_event(f"Error: {message}")
        stop_event_init.set()  # Signal to stop the 'Initializing' display
        state_task.cancel()  # Cancel the display task
        display = initLCD()  # Reinitialize the display
        return display

async def updateLCD(text, stop_event=None, delay=0.02):
    global display  # Declare it global
    async with display_lock:  # Acquire lock
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
                        log_event(f"Struct Error: {e}, skipping character {char}")
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

async def listen(loop, display, state_task):
    def recognize_audio():
        try:
            with sr.Microphone() as source:
                if source.stream is None:
                    raise Exception("Microphone not initialized.")
                audio = r.listen(source, timeout=10.0)
                return r.recognize_google(audio)
        except sr.WaitTimeoutError:
            if source and source.stream:
                source.stream.close()
            raise asyncio.TimeoutError("Listening timed out.")
        except OSError as e:
            if "No Default Input Device Available" in str(e):
                subprocess.run(["sudo", "systemctl", "restart", "gpt-home"])
                raise Exception("Restarting gpt-home due to no default input device")
    
    text = await loop.run_in_executor(executor, recognize_audio)
    return text

async def display_state(state, stop_event):
    global display, display_lock
    async with display_lock:
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

async def query_openai(text, display, retries=3):
    stop_event = asyncio.Event()
    for i in range(retries):
        try:
            response = openai.Completion.create(
                engine="davinci",
                prompt=f"Q: {text}\nA: (But add a hint of snark and sarcasm)",
                temperature=0.9,
                max_tokens=150,
                top_p=1,
                frequency_penalty=0.0,
                presence_penalty=0.6,
                stop=["\n"]
            )
            if response.choices[0].text.strip():  # Check if the response is not empty
                message = f"Response: {response.choices[0].text.strip()}"
                return message
            else:
                log_event(f"Retry {i+1}: Received empty response from OpenAI.")
        except Exception as e:
            log_event(f"Error on try {i+1}: {e}")
            if i == retries - 1:  # If this was the last retry
                error_message = f"Something went wrong after {retries} retries: {e}"
                stop_event = asyncio.Event()
                await speak(error_message, stop_event)
                log_event(f"Error: {traceback.format_exc()}")
        await asyncio.sleep(0.5)  # Wait before retrying
    raise Exception("Something went wrong after {retries} retries.")

def network_connected():
    return os.system("ping -c 1 google.com") == 0

def log_event(text):
    logging.info(text)

async def handle_error(message, state_task, display):
    if state_task: state_task.cancel()
    delay = await calculate_delay(message, engine.getProperty('rate'))
    stop_event = asyncio.Event()
    lcd_task = asyncio.create_task(updateLCD(message, display, stop_event=stop_event, delay=delay))
    speak_task = asyncio.create_task(speak(message, stop_event, delay=delay))
    await speak_task
    lcd_task.cancel()
    log_event(f"Error: {traceback.format_exc()}")
