from common import *

async def main():
    state_task = None
    while True:
        try:
            # Load settings from settings.json
            settings = load_settings()
            keyword = settings.get("keyword")

            # Start displaying 'Listening'
            stop_event = asyncio.Event()
            state_task = asyncio.create_task(display_state("Listening", display, stop_event))

            try:
                text = await listen(display, state_task, stop_event)
            except Exception as e:
                logger.error(f"Listening timed out: {traceback.format_exc()}")
                continue

            # Stop displaying 'Listening'
            stop_event.set()
            if state_task:
                state_task.cancel()
            
            # Check if keyword is in text and respond
            if text:
                clean_text = text.lower().translate(str.maketrans('', '', string.punctuation))
                if keyword in clean_text:
                    actual_text = clean_text.split(keyword, 1)[1].strip()
                    if actual_text:
                        heard_message = f"Heard: \"{actual_text}\""
                        logger.success(heard_message)
                        stop_event_heard = asyncio.Event()
                        stop_event_response = asyncio.Event()

                        # Calculate time to speak and display
                        delay_heard = await calculate_delay(heard_message)

                        # Create a task for OpenAI query, don't await it yet
                        query_task = asyncio.create_task(action_router(actual_text, display))

                        await asyncio.gather(
                            speak(heard_message, stop_event_heard),
                            updateLCD(heard_message, display, stop_event=stop_event_heard, delay=delay_heard)
                        )

                        response_message = await query_task
                        
                        # Calculate time to speak and display
                        delay_response = await calculate_delay(response_message)

                        response_task_speak = asyncio.create_task(speak(response_message, stop_event_response))
                        response_task_lcd = asyncio.create_task(updateLCD(response_message, display, stop_event=stop_event_response, delay=delay_response))

                        logger.success(response_message)
                        await asyncio.gather(response_task_speak, response_task_lcd)
                        
                else:
                    continue  # Skip to the next iteration
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