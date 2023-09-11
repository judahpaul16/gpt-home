import traceback
import asyncio
from functions import *

async def main():
    while True:
        try:
            state_task = asyncio.create_task(display_state("Listening", display))
            text = await listen_speech(loop, display, state_task)
            heard_message = f"Heard: {text}"
            response_message = await query_openai(text, display)
            
            heard_task = asyncio.gather(speak(heard_message), updateLCD(heard_message, display))
            response_task = asyncio.gather(speak(response_message), updateLCD(response_message, display))
            
            await heard_task
            log_event(heard_message)
            await response_task
            log_event(response_message)
        except sr.UnknownValueError:
            error_message = "Sorry, I did not understand that"
            await handle_error(error_message, state_task, display)
        except sr.RequestError as e:
            error_message = f"Could not request results; {e}"
            await handle_error(error_message, state_task, display)
        except Exception as e:
            error_message = f"Something Went Wrong: {e}"
            await handle_error(error_message, state_task, display)

async def handle_error(message, state_task, display):
    state_task.cancel()
    await updateLCD(message, display, error=True)
    log_event(f"Error: {message}")

# Initialize LCD
display = initLCD()

loop = asyncio.get_event_loop()
loop.run_until_complete(main())
loop.close()
