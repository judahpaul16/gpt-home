import traceback
import asyncio
from functions import *

async def main():
    while True:
        try:
            ellipses_task = asyncio.create_task(animate_ellipses(display))
            text = await listen_speech(loop, display)
            ellipses_task.cancel()
            print(f"Heard: {text}")
            await updateLCD(f"Heard: {text}", display)
            # speak(text)
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


# Initialize LCD
display = initLCD()

loop = asyncio.get_event_loop()
loop.run_until_complete(main())