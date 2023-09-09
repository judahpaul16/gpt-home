import traceback
import asyncio
from functions import *

async def main():
    while True:
        try:
            state_task = asyncio.create_task(display_state("Listening", display))
            text = await listen_speech(loop, display)
            state_task.cancel()
            print(f"Heard: {text}")
            await updateLCD(f"Heard: {text}", display)
        except sr.UnknownValueError:
            print("Could not understand audio.")
            asyncio.create_task(updateLCD("Could not understand audio.", display))
            state_task.cancel()
        except sr.RequestError as e:
            print(f"Could not request results; {e}")
            asyncio.create_task(updateLCD(f"Could not request results; {e}", display))
            state_task.cancel()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"An error occurred: {traceback.format_exc()}")
            asyncio.create_task(updateLCD(f"An error occurred: {e}", display))
            state_task.cancel()

# Initialize LCD
display = initLCD()

loop = asyncio.get_event_loop()
loop.run_until_complete(main())