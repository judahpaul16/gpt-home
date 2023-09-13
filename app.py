from functions import *

async def main():
    state_task = None
    stop_event = asyncio.Event()
    while True:
        if state_task is None:
            stop_event.clear()
            state_task = asyncio.create_task(display_state("Listening", display, stop_event))
        try:
            keyword = "computer"
            try:
                text = await listen(loop, display, state_task)
            except asyncio.TimeoutError:
                log_event("Listening timed out.")
                raise Exception("Sorry didn't catch that.")
            if text:
                split_text = text.split(keyword)
                if keyword in text and len(split_text) > 1 and len(split_text[1].strip()) > 0:
                    stop_event.set()
                    state_task.cancel()
                    state_task = None
                    
                    try:
                        actual_text = split_text[1].strip()
                        heard_message = f"Heard: \"{actual_text}\""
                        response_message = await query_openai(actual_text, display)

                        stop_event_heard = asyncio.Event()
                        stop_event_response = asyncio.Event()

                        # Calculate time to speak and display
                        delay_heard = await calculate_delay(heard_message)
                        delay_response = await calculate_delay(response_message)

                        await asyncio.gather(
                            speak(heard_message, stop_event_heard),
                            updateLCD(heard_message, display, stop_event=stop_event_heard, delay=delay_heard)
                        )
                        log_event(heard_message)

                        response_task_speak = asyncio.create_task(speak(response_message, stop_event_response))
                        response_task_lcd = asyncio.create_task(updateLCD(response_message, display, stop_event=stop_event_response, delay=delay_response))
                        
                        await asyncio.gather(response_task_speak, response_task_lcd)
                        log_event(response_message)
                    
                    except sr.UnknownValueError:
                        error_message = "Sorry, I did not understand that"
                        await handle_error(error_message, state_task, display)
            else:
                continue  # Skip to the next iteration
        except sr.UnknownValueError:
            pass
        except sr.RequestError as e:
            error_message = f"Could not request results; {e}"
            await handle_error(error_message, state_task, display)
        except Exception as e:
            error_message = f"Something Went Wrong: {e}"
            await handle_error(error_message, state_task, display)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    init_done_event = asyncio.Event()  # Create an event to signal when initialization is done

    async def wrapped_initialize_system():
        display = await initialize_system()
        init_done_event.set()  # Signal that initialization is done
        return display

    display = loop.run_until_complete(wrapped_initialize_system())

    async def wrapped_main():
        await init_done_event.wait()  # Wait for the event to be set
        await main()

    loop.run_until_complete(wrapped_main())
    loop.close()
