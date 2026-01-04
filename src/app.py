from common import *

async def main():
    state_task = None

    async def safe_task(coro):
        """Execute a coroutine safely, logging any errors."""
        try:
            return await coro
        except asyncio.CancelledError:
            raise  # Let cancellation propagate
        except Exception as e:
            logger.error(f"Task failed: {e}")
            return None

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
                try:
                    await state_task
                except asyncio.CancelledError:
                    pass

            # Check if keyword is in text and respond
            if text:
                clean_text = text.lower().translate(str.maketrans('', '', string.punctuation))
                if keyword in clean_text:
                    enable_heard = settings.get("sayHeard", "true") == "true"
                    actual_text = clean_text.split(keyword, 1)[1].strip()
                    if actual_text:
                        heard_message = f"Heard: \"{actual_text}\""
                        logger.success(heard_message)

                        # Create a task for OpenAI query, don't await it yet
                        query_task = asyncio.create_task(action_router(actual_text))

                        # Speak and display "Heard" message (synchronized)
                        if enable_heard:
                            await speak_with_display(heard_message, display)

                        response_message = await query_task

                        logger.success(response_message)
                        
                        # Speak and display response (synchronized)
                        await speak_with_display(response_message, display)
                        
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

display = None  # Global display reference

async def startup():
    """Initialize system and run main loop."""
    global display
    display = await initialize_system()

    # Read API key from environment variable (set via .env file)
    api_key = os.getenv("LITELLM_API_KEY")

    if not api_key and display:
        display.fill(0)
        ip_address = subprocess.check_output(["hostname", "-I"]).decode("utf-8").split(" ")[0].strip()
        display.text("Missing API Key", 0, 0, 1)
        display.text("To update it, visit:", 0, 10, 1)
        if ip_address:
            display.text(f"{ip_address}/settings", 0, 20, 1)
        else:
            display.text("gpt-home.local/settings", 0, 20, 1)
        display.show()

    await main()


if __name__ == "__main__":
    # Import routes at module level after defining display
    from routes import *
    
    try:
        asyncio.run(startup())
    except KeyboardInterrupt:
        logger.info("Assistant stopped by user")
