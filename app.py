import speech_recognition as sr
import traceback
import requests
import asyncio
import json
import os
from functions import *

async def main():
    while True:
        try:
            text = await loop.run_in_executor(None, listen_speech)
            print(f"Heard: {text}")
            asyncio.create_task(updateLCD(f"Heard: {text}", display))
            speak(text)
            # response = query_openai(text)
            # speak(response)
        except sr.UnknownValueError:
            print("Could not understand audio.")
            asyncio.create_task(updateLCD("Could not understand audio.", display))
        except sr.RequestError as e:
            print(f"Could not request results; {e}")
            asyncio.create_task(updateLCD(f"Could not request results; {e}", display))
        except Exception as e:
            print(f"An error occurred: {traceback.format_exc()}")
            asyncio.create_task(updateLCD(f"An error occurred: {e}", display))

async def updateLCD(text, display):
    display.fill(0)
    ip_address = (
        subprocess.check_output(["hostname", "-I"])
        .decode("utf-8")
        .split(" ")[0]
    )
    display.text("IP: " + str(ip_address), 0, 0, 1)
    
    if text == 'Listening' or text == 'Interpreting':
        while text == 'Listening' or text == 'Interpreting':
            for i in range(4):
                display.fill(0)
                display.text("IP: " + str(ip_address), 0, 0, 1)
                display.text(text + '.' * i, 0, 20, 1)
                display.show()
                await asyncio.sleep(0.5)
    else:
        # ... (Your existing text display logic)
        display.show()
        await asyncio.sleep(5)

# Initialize LCD
display = initLCD()

# Initialize recognizer
r = sr.Recognizer()

loop = asyncio.get_event_loop()
loop.run_until_complete(main())