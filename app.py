import traceback
import asyncio
from functions import *

async def main():
    while True:
        try:
            state_task = asyncio.create_task(display_state("Listening", display))
            text = await listen_speech(loop, display, state_task)
            print(f"Heard: {text}")
            await updateLCD(f"Heard: {text}", display)
        except sr.UnknownValueError:
            print("Could not understand audio.")
            state_task.cancel()
            await updateLCD("Could not understand audio.", display)
        except sr.RequestError as e:
            print(f"Could not request results; {e}")
            state_task.cancel()
            await updateLCD(f"Could not request results; {e}", display)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"An error occurred: {traceback.format_exc()}")
            state_task.cancel()
            await updateLCD(f"An error occurred: {e}", display)

# Initialize LCD
display = initLCD()

loop = asyncio.get_event_loop()
loop.run_until_complete(main())
