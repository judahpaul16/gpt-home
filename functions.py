from concurrent.futures import ThreadPoolExecutor
from vosk import Model, KaldiRecognizer
import speech_recognition as sr
from board import SCL, SDA
import adafruit_ssd1306
import subprocess
import textwrap
import asyncio
import busio
import openai
import json
import time
import os
import logging

# Initialize Vosk language model
model = Model("vosk")

logging.basicConfig(filename='events.log', level=logging.DEBUG)

r = sr.Recognizer()
openai_api_key = os.getenv("OPENAI_API_KEY")
executor = ThreadPoolExecutor()

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
    display.show()

    # Display IP address
    ip_address = (
        subprocess.check_output(["hostname", "-I"])
        .decode("utf-8")
        .split(" ")[0]
    )
    display.text("IP: " + str(ip_address), 0, 0, 1)

    # Show the updated display with the text.
    display.show()
    return display

async def updateLCD(text, display):
    display.fill_rect(0, 10, 128, 22, 0)
    ip_address = subprocess.check_output(["hostname", "-I"]).decode("utf-8").split(" ")[0]
    display.text("IP: " + str(ip_address), 0, 0, 1)
    display.show()

    wrapped_text = textwrap.fill(text, 21)
    lines = wrapped_text.split('\n')

    if len(lines) > 2:
        # scroll text
        start_time = time.time()
        while time.time() - start_time < 15:
            for i in range(0, len(lines) - 1):
                display.fill_rect(0, 10, 128, 22, 0)
                display.text(lines[i], 0, 10, 1)
                display.text(lines[i+1], 0, 20, 1)
                display.show()
                await asyncio.sleep(3)
    elif len(lines) == 2:
        # two lines
        display.text(lines[0], 0, 10, 1)
        display.text(lines[1], 0, 20, 1)
        display.show()
        await asyncio.sleep(6)
    else:
        # one line
        display.text(lines[0], 0, 10, 1)
        display.show()
        await asyncio.sleep(6)

async def listen_speech(loop, display, state_task):
    def recognize_audio():
        rec = KaldiRecognizer(model, 16000)  # Initialize recognizer with Vosk
        with sr.Microphone() as source:
            audio = r.listen(source)
            audio_data = audio.get_wav_data()
            if rec.AcceptWaveform(audio_data):
                text = json.loads(rec.Result())['text']  # Parse JSON result
                return text
            else:
                return "Sorry, I did not understand that."

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

def speak(text):
    os.system(f"espeak '{text}'")

def query_openai(text):
    response = openai.Completion.create(
        engine="davinci",
        prompt=text,
        temperature=0.9,
        max_tokens=150,
        top_p=1,
        frequency_penalty=0.0,
        presence_penalty=0.6,
        stop=["\n", " Human:", " AI:"],
        api_key=openai_api_key
    )
    return response.choices[0].text

def log_event(text):
    logging.info(text)