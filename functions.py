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
engine.setProperty('rate', 150)
engine.setProperty('volume', 1.0)
# Direct audio to specific hardware
engine.setProperty('alsa_device', 'hw:Headphones,0')
speak_lock = asyncio.Lock()

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
    display.text(f"IP: {ip_address}", 0, 0, 1)
    # Show the updated display with the text.
    display.show()
    return display

async def initialize_system():
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

async def updateLCD(text, display, error=False, stop_event=None):
    if stop_event is None:
        stop_event = asyncio.Event()

    async def display_lines(start, end):
        display.fill_rect(0, 10, 128, 22, 0)
        for i, line_index in enumerate(range(start, end)):
            display.text(lines[line_index], 0, 10 + i * 10, 1)
        display.show()

    async def loop_text():
        i = 0
        while not (stop_event and stop_event.is_set()):
            if line_count > 1:
                await display_lines(i, i + 2)
                i = (i + 1) % (line_count - 1)
            else:
                await display_lines(0, 1)
            await asyncio.sleep(2)

    # Clear the display
    display.fill(0)
    # Display IP address
    ip_address = subprocess.check_output(["hostname", "-I"]).decode("utf-8").split(" ")[0]
    display.text(f"IP: {ip_address}", 0, 0, 1)
    display.show()
    # Line wrap the text
    lines = textwrap.fill(text, 21).split('\n')
    line_count = len(lines)
    # Loop the text if it's more than 2 lines
    loop_task = asyncio.create_task(loop_text())

    # Wait for just the loop_task to finish if an error occurred
    if error: await asyncio.gather(loop_task)

async def listen(loop, display, state_task):
    def recognize_audio():
        with sr.Microphone() as source:
            audio = r.listen(source)
            return r.recognize_google(audio)
    text = await loop.run_in_executor(executor, recognize_audio)
    return text

async def display_state(state, display, stop_event):
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
    for i in range(retries):
        try:
            response = openai.Completion.create(
                engine="davinci",
                prompt=f"Q: {text}\nA: (But add a hint of snark and sarcasm)",
                temperature=0.9,
                max_tokens=64,
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
                return error_message
        await asyncio.sleep(2)  # Wait before retrying
    return "Response: No response from OpenAI after maximum retries."

def network_connected():
    return os.system("ping -c 1 google.com") == 0

def log_event(text):
    logging.info(text)

async def handle_error(message, state_task, display):
    state_task.cancel()
    stop_event = asyncio.Event()
    lcd_task = asyncio.create_task(updateLCD(message, display, error=True, stop_event=stop_event))
    speak_task = asyncio.create_task(speak(message, stop_event))
    await speak_task
    lcd_task.cancel()
    log_event(f"Error: {traceback.format_exc()}")
