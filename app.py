import speech_recognition as sr
import traceback
import requests
import json
import os
from functions import *

# Initialize LCD
display = initLCD()

# Initialize recognizer
r = sr.Recognizer()

# OpenAI API URL
api_url = "https://api.openai.com/v1/engines/davinci-codex/completions"

# Function to listen to and recognize speech
def listen_speech():
    with sr.Microphone() as source:
        print("Listening...")
        updateLCD("Listening", display)
        audio = r.listen(source)
        del source  # Explicitly delete the source object to release the microphone
        return r.recognize_google(audio)

# Function to query OpenAI and get a text response
def query_openai(text):
    headers = {
        "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
        "Content-Type": "application/json"
    }
    payload = json.dumps({
        "prompt": text,
        "max_tokens": 50
    })
    response = requests.post(api_url, headers=headers, data=payload)
    if response: return json.loads(response.text).get('choices')[0].get('text').strip()
    else: return "No response from OpenAI"

# Listen and send query to OpenAI
while True:
    try:
        text = listen_speech()
        print(f"Heard: {text}")
        updateLCD(f"Heard: {text}", display)
        speak("Heard: " + text)
        # response = query_openai(text)
        # speak(response)
    except sr.UnknownValueError:
        print("Could not understand audio.")
        updateLCD("Could not understand audio.", display)
    except sr.RequestError as e:
        print(f"Could not request results; {e}")
        updateLCD(f"Could not request results; {e}", display)
    except Exception as e:
        print(f"An error occurred: {traceback.format_exc()}")
        updateLCD(f"An error occurred: {e}", display)