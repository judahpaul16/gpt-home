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

async def updateLCD(text, display, error=False):
    stop_event = asyncio.Event()

    async def display_lines(start, end):
        display.fill_rect(0, 10, 128, 22, 0)
        for i, line_index in enumerate(range(start, end)):
            display.text(lines[line_index], 0, 10 + i * 10, 1)
        display.show()

    async def loop_text():
        i = 0
        while not stop_event.is_set():
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

    stop_event.set()

async def listen_speech(loop, display, state_task):
    def recognize_audio():
        with sr.Microphone() as source:
            audio = r.listen(source)
            return r.recognize_google(audio)
    text = await loop.run_in_executor(executor, recognize_audio)
    state_task.cancel()
    return text

async def display_state(state, display):
    while True:
        for i in range(4):
            display.fill_rect(0, 10, 128, 22, 0)
            display.text(f"{state}" + '.' * i, 0, 20, 1)
            display.show()
            await asyncio.sleep(0.5)

async def speak(text):
    async with speak_lock:
        loop = asyncio.get_running_loop()
        def _speak():
            engine.say(text)
            engine.runAndWait()
        await loop.run_in_executor(executor, _speak)

async def query_openai(text, display):
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
        message = f"Response: {response.choices[0].text}"
        return message
    except Exception as e:
        error_message = f"Something went wrong: {e}"
        await speak(error_message)
        log_event(f"Error: {traceback.format_exc()}")
        return error_message

def network_connected():
    return os.system("ping -c 1 google.com") == 0

def log_event(text):
    logging.info(text)
    
async def handle_error(message, state_task, display):
    state_task.cancel()
    await updateLCD(message, display, error=True)
    log_event(f"Error: {message}")
