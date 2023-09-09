import traceback
import asyncio
from functions import *

async def main():
    while True:
        try:
            state_task = asyncio.create_task(display_state("Listening", display))
            text = await listen_speech(loop, display, state_task)
            message = f"Heard: {text}"
            print(message)
            log_event(message)
            await updateLCD(message, display)
        except sr.UnknownValueError:
            message = "Could not understand audio"
            print(message)
            log_event(message)
            state_task.cancel()
            await updateLCD(message, display)
        except sr.RequestError as e:
            message = f"Could not request results; {e}"
            print(message)
            log_event(message)
            state_task.cancel()
            await updateLCD(message, display)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            message = f"An error occurred: {e}"
            tracebackMessage = f"An error occurred: {traceback.format_exc()}"
            print(tracebackMessage)
            log_event(tracebackMessage)
            state_task.cancel()
            await updateLCD(message, display)

# Initialize LCD
display = initLCD()

loop = asyncio.get_event_loop()
loop.run_until_complete(main())
