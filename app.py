import speech_recognition as sr
import pyttsx3
import requests
import json
import os

from functions import *

# Initialize LCD
initLCD()

# Initialize TTS engine
engine = pyttsx3.init()

# Initialize recognizer
r = sr.Recognizer()

# OpenAI API URL
api_url = "https://api.openai.com/v1/engines/davinci-codex/completions"

# Function to listen to and recognize speech
def listen_speech():
    with sr.Microphone() as source:
        print("Listening...")
        audio = r.listen(source)
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
    return json.loads(response.text).get('choices')[0].get('text').strip()

# Listen and send query to OpenAI
while True:
    try:
        text = listen_speech()
        print(f"Received: {text}")
        response = query_openai(text)
        engine.say(response)
        engine.runAndWait()
    except sr.UnknownValueError:
        print("Could not understand audio.")
    except sr.RequestError as e:
        print(f"Could not request results; {e}")
    except Exception as e:
        print(f"An error occurred: {e}")
