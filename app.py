from functions import *
import contextlib

async def main():
    state_task = None
    stop_event = asyncio.Event()

    async def manage_task(task):
        nonlocal state_task
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log_event(f"Task error: {e}")
        finally:
            if task is state_task:
                state_task = None

    while True:
        if state_task is None:
            stop_event.clear()
            state_task = asyncio.create_task(display_state("Listening", display, stop_event))
            asyncio.create_task(manage_task(state_task))

        try:
            text = await listen(loop, display, state_task)
            if not text:
                continue

            keyword = "computer"
            if keyword not in text:
                continue

            split_text = text.split(keyword, 1)
            actual_text = split_text[1].strip()

            if not actual_text:
                continue

            stop_event.set()
            state_task.cancel()

            # Reset state_task and stop_event
            state_task = None
            stop_event = asyncio.Event()

            query_task = asyncio.create_task(query_openai(actual_text, display))
            heard_message = f"Heard: \"{actual_text}\""
            response_message = await query_task
            stop_event_heard = asyncio.Event()
            stop_event_response = asyncio.Event()

            delay_heard = await calculate_delay(heard_message)
            delay_response = await calculate_delay(response_message)

            await asyncio.gather(
                speak(heard_message, stop_event_heard),
                updateLCD(heard_message, display, stop_event=stop_event_heard, delay=delay_heard)
            )
            log_event(heard_message)

            await asyncio.gather(
                speak(response_message, stop_event_response),
                updateLCD(response_message, display, stop_event=stop_event_response, delay=delay_response)
            )
            log_event(response_message)

        except sr.UnknownValueError:
            await handle_error("Sorry, I did not understand that", state_task, display)

        except sr.RequestError as e:
            await handle_error(f"Could not request results; {e}", state_task, display)

        except asyncio.TimeoutError:
            log_event("Listening timed out")

        except Exception as e:
            await handle_error(f"Something Went Wrong: {e}", state_task, display)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    display = loop.run_until_complete(initialize_system())
    loop.run_until_complete(main())
