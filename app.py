from functions import *
import asyncio

async def main():
    state_task = None
    stop_event = asyncio.Event()
    while True:
        if state_task is None:
            stop_event.clear()
            state_task = asyncio.create_task(display_state("Listening", display, stop_event))
        
        try:
            keyword = "computer"
            text = await listen(loop, display, state_task)
            split_text = text.split(keyword)
            
            if keyword in text and len(split_text) > 1 and len(split_text[1].strip()) > 0:
                stop_event.set()
                state_task.cancel()
                state_task = None
                
                try:
                    actual_text = split_text[1].strip()
                    heard_message = f"Heard: {actual_text}"
                    response_message = await query_openai(actual_text, display)

                    stop_event_heard = asyncio.Event()
                    stop_event_response = asyncio.Event()

                    heard_task_speak = asyncio.create_task(speak(heard_message, stop_event_heard))
                    heard_task_lcd = asyncio.create_task(updateLCD(heard_message, display, stop_event=stop_event_heard))
                    
                    await asyncio.gather(heard_task_speak, heard_task_lcd)
                    log_event(heard_message)

                    response_task_speak = asyncio.create_task(speak(response_message, stop_event_response))
                    response_task_lcd = asyncio.create_task(updateLCD(response_message, display, stop_event=stop_event_response))
                    
                    await asyncio.gather(response_task_speak, response_task_lcd)
                    log_event(response_message)
                
                except sr.UnknownValueError:
                    error_message = "Sorry, I did not understand that"
                    await handle_error(error_message, state_task, display)
        
        except sr.UnknownValueError:
            pass
        except sr.RequestError as e:
            error_message = f"Could not request results; {e}"
            await handle_error(error_message, state_task, display)
        except Exception as e:
            error_message = f"Something Went Wrong: {e}"
            await handle_error(error_message, state_task, display)

async def initialize_system():
    display = initLCD()
    state_task = asyncio.create_task(display_state("Initializing", display))
    while not network_connected():
        await asyncio.sleep(1)
        message = "Network not connected"
        log_event(f"Error: {message}")
        await updateLCD(message, display, error=True)
        stop_event = asyncio.Event()
        await speak(message, stop_event)
        if network_connected():
            break
    return display

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    display = loop.run_until_complete(initialize_system())
    loop.run_until_complete(main())
    loop.close()
