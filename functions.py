from concurrent.futures import ThreadPoolExecutor
import speech_recognition as sr
from board import SCL, SDA
import adafruit_ssd1306
import subprocess
import asyncio
import busio
import openai
import os

global r
r = sr.Recognizer()

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

    if len(text) > 42:
        done = False
        while not done:
            for i in range(0, len(text) - 21, 21):
                display.fill_rect(0, 10, 128, 22, 0)
                display.text(text[i:i+21], 0, 10, 1)
                display.text(text[i+21:i+42], 0, 20, 1)
                display.show()
                await asyncio.sleep(2) # wait 2 seconds
            done = asyncio.sleep(20).result()
    elif len(text) > 21:
        display.text(text[:21], 0, 10, 1)
        display.text(text[21:], 0, 20, 1)
        await asyncio.sleep(5) # wait 5 seconds
    else:
        display.text(text, 0, 10, 1)
    display.show()
    await asyncio.sleep(5) # wait 5 seconds

async def listen_speech(loop, display, state_task):
    global r
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

def speak(text):
    os.system(f"espeak '{text}'")

def query_openai(text):
    openai.api_key = os.getenv("OPENAI_API_KEY")
    response = openai.Completion.create(
        engine="davinci",
        prompt=text,
        temperature=0.9,
        max_tokens=150,
        top_p=1,
        frequency_penalty=0.0,
        presence_penalty=0.6,
        stop=["\n", " Human:", " AI:"]
    )
    return response.choices[0].text