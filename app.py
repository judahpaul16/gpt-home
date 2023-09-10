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
            message = "Sorry, I did not understand that"
            print(message)
            log_event("Error: " + message)
            state_task.cancel()
            await updateLCD(message, display)
        except sr.RequestError as e:
            message = f"Could not request results; {e}"
            print(message)
            log_event("Error: " + message)
            state_task.cancel()
            await updateLCD(message, display)
        except asyncio.CancelledError:
            log_event("Async task was cancelled")
        except Exception as e:
            message = f"Something Went Wrong: {e}"
            tracebackMessage = f"Error: {traceback.format_exc()}"
            print(tracebackMessage)
            log_event(tracebackMessage)
            state_task.cancel()
            await updateLCD(message, display)

# Initialize LCD
display = initLCD()

loop = asyncio.get_event_loop()
loop.run_until_complete(main())
loop.close()
