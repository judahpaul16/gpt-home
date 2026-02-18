import logging

from common import *

from src.backend import get_db_pool
from src.routes import action_router

logger = logging.getLogger("app")

try:
    from src.audio_activity import get_audio_activity_detector
except ImportError:
    get_audio_activity_detector = None

_consecutive_silence_count = 0
_idle_mode_active = False
_SILENCE_THRESHOLD_FOR_IDLE = 4
_IDLE_CHECK_INTERVAL = 2.0


def detect_tool_from_query(query: str) -> tuple:
    """Detect tool type and context from user query for display animation."""
    import re

    query_lower = query.lower()

    if any(
        w in query_lower
        for w in ["weather", "temperature", "forecast", "rain", "sunny", "cloudy"]
    ):
        context = {}
        location_match = re.search(
            r"(?:in|for|at)\s+([a-zA-Z\s,]+?)(?:\?|$|today|tomorrow|this|next|weather)",
            query,
            re.IGNORECASE,
        )
        if location_match:
            context["requested_location"] = (
                location_match.group(1).strip().rstrip(",").title()
            )
        return "weather", context

    if any(w in query_lower for w in ["alarm", "wake me", "reminder", "remind me"]):
        return "alarm", {}

    if any(w in query_lower for w in ["timer", "countdown"]):
        context = {"name": "Timer"}
        duration_seconds = 0

        # Extract duration from query (e.g., "5 minutes", "30 seconds", "1 hour")
        time_patterns = [
            (r"(\d+)\s*(?:hour|hr)s?", 3600),
            (r"(\d+)\s*(?:minute|min)s?", 60),
            (r"(\d+)\s*(?:second|sec)s?", 1),
        ]

        for pattern, multiplier in time_patterns:
            match = re.search(pattern, query_lower)
            if match:
                duration_seconds += int(match.group(1)) * multiplier

        if duration_seconds > 0:
            context["duration"] = duration_seconds

        return "timer", context

    if any(
        w in query_lower
        for w in ["spotify", "play", "music", "song", "pause", "skip", "next"]
    ):
        return "spotify", {}

    if any(w in query_lower for w in ["light", "lamp", "bulb", "hue", "brightness"]):
        return "lights", {}

    if any(w in query_lower for w in ["calendar", "event", "meeting", "schedule"]):
        return "calendar", {}

    return None, {}


def _check_audio_level_sync() -> tuple:
    """Synchronous audio level check using WebRTC VAD for voice detection.

    Uses WebRTC VAD to detect actual human speech rather than just amplitude.
    This prevents ambient noise (fans, traffic, etc.) from waking the system.

    Returns:
        Tuple of (has_voice, db_level, threshold)
    """
    try:
        from src.audio_capture import start_mic_capture, stop_mic_capture

        stop_mic_capture()
    except Exception:
        pass

    try:
        settings = load_settings()
        vad_threshold_db = settings.get("vadThresholdDb", -50.0)

        if get_audio_activity_detector:
            detector = get_audio_activity_detector()
            detector.configure(vad_threshold_db=vad_threshold_db)
        else:
            detector = None

        mic_index = find_microphone_device_index()

        with sr.Microphone(device_index=mic_index) as source:
            if source.stream is None:
                return False, -100.0, vad_threshold_db

            sample_duration = 0.5
            sample_frames = int(source.SAMPLE_RATE * sample_duration)
            audio_data = source.stream.read(sample_frames)

            if not audio_data:
                return False, -100.0, vad_threshold_db

            if detector:
                import audioop
                import math

                rms = audioop.rms(audio_data, source.SAMPLE_WIDTH)
                max_val = (1 << (8 * source.SAMPLE_WIDTH - 1)) - 1
                db_level = 20 * math.log10(rms / max_val + 1e-10) if rms > 0 else -100.0

                # WebRTC VAD requires 16000 Hz sample rate
                # Resample audio if needed before VAD check
                vad_sample_rate = 16000
                vad_audio = audio_data
                if source.SAMPLE_RATE != vad_sample_rate:
                    vad_audio, _ = audioop.ratecv(
                        audio_data,
                        source.SAMPLE_WIDTH,
                        1,
                        source.SAMPLE_RATE,
                        vad_sample_rate,
                        None,
                    )

                has_voice = detector.detect_voice(
                    vad_audio,
                    sample_width=source.SAMPLE_WIDTH,
                    sample_rate=vad_sample_rate,
                )
                return has_voice, db_level, vad_threshold_db
            else:
                import audioop
                import math

                rms = audioop.rms(audio_data, source.SAMPLE_WIDTH)
                if rms > 0:
                    max_val = (1 << (8 * source.SAMPLE_WIDTH - 1)) - 1
                    db = 20 * math.log10(rms / max_val + 1e-10)
                else:
                    db = -100.0
                return db > vad_threshold_db, db, vad_threshold_db

    except Exception as e:
        logger.error("Audio level check error: %s", e)
        return False, -100.0, -50.0
    finally:
        try:
            from src.audio_capture import start_mic_capture

            start_mic_capture()
        except Exception:
            pass


async def check_audio_level_above_threshold() -> bool:
    """Quick check if voice is detected using WebRTC VAD."""
    loop = asyncio.get_running_loop()
    has_voice, db, threshold = await loop.run_in_executor(None, _check_audio_level_sync)

    if has_voice:
        logger.info("Voice detected: %.1f dB (VAD triggered)", db)

    return has_voice


async def restore_display_header(display):
    """Restore display with IP and CPU temp header."""
    if display is None:
        return

    async with display_lock:
        display.fill(0)
        draw_i2c_header(display)
        display.show()


async def idle_loop(display):
    """Run idle loop - periodically check for audio and manage screensaver."""
    global _idle_mode_active

    _idle_mode_active = True
    logger.info("Entering idle mode")

    await restore_display_header(display)

    try:
        while _idle_mode_active:
            has_audio = await check_audio_level_above_threshold()

            if has_audio:
                logger.info("Audio detected, exiting idle mode")

                i2c_display_register_activity()

                register_all_display_activity()

                # Proactively wake full display manager if available

                dm = get_display_manager()

                if dm and dm.is_available:
                    await dm.register_activity_async()

                _idle_mode_active = False

                await restore_display_header(display)

                return True

            await i2c_display_check_screensaver(display)
            await asyncio.sleep(_IDLE_CHECK_INTERVAL)

    except asyncio.CancelledError:
        _idle_mode_active = False
        await restore_display_header(display)
        raise
    except Exception as e:
        logger.error("Error in idle loop: %s", e, exc_info=True)
        _idle_mode_active = False
        await restore_display_header(display)
        return True

    return False


async def main():
    global _consecutive_silence_count, _idle_mode_active

    state_task = None

    while True:
        try:
            settings = load_settings()
            keyword = settings.get("keyword", "computer")

            if _consecutive_silence_count >= _SILENCE_THRESHOLD_FOR_IDLE:
                logger.debug(
                    "%d consecutive silent cycles, entering idle mode",
                    _consecutive_silence_count,
                )

                should_listen = await idle_loop(i2c_display)
                _consecutive_silence_count = 0

                if not should_listen:
                    continue

                await restore_display_header(i2c_display)

            stop_event = asyncio.Event()
            state_task = asyncio.create_task(
                display_state("Listening", i2c_display, stop_event)
            )

            try:
                text = await listen(i2c_display, state_task, stop_event)
                logger.debug(f"[app] listen() returned: {text!r}")
            except Exception as e:
                logger.error(f"Listening timed out: {traceback.format_exc()}")
                _consecutive_silence_count += 1

            stop_event.set()
            if state_task:
                state_task.cancel()
                try:
                    await state_task
                except asyncio.CancelledError:
                    pass

            if text:
                _consecutive_silence_count = 0
                i2c_display_register_activity()
                register_all_display_activity()

                clean_text = text.lower().translate(
                    str.maketrans("", "", string.punctuation)
                )
                logger.debug(f"[app] clean_text: {clean_text!r}, keyword: {keyword!r}")

                if keyword in clean_text:
                    actual_text = clean_text.split(keyword, 1)[1].strip()
                    logger.info("Keyword found, actual_text: %r", actual_text)
                else:
                    _consecutive_silence_count += 1
                    continue

                if actual_text:
                    say_heard = settings.get("sayHeard", True)
                    enable_heard = (
                        say_heard
                        if isinstance(say_heard, bool)
                        else str(say_heard).lower() == "true"
                    )
                    heard_message = f'Heard: "{actual_text}"'
                    logger.success(heard_message)

                    logger.info("Calling action_router with: %r", actual_text)
                    query_task = asyncio.create_task(action_router(actual_text))

                    if enable_heard:
                        await speak_with_display(heard_message, i2c_display)

                    response_message = await query_task
                    logger.info("action_router returned: %r", response_message)
                    logger.success(response_message)

                    await speak_with_display(response_message, i2c_display)

                    _consecutive_silence_count = 0
                    dm = get_display_manager()
                    if dm and dm.is_available and not dm.has_tool_animation:
                        await dm.resume_idle()
            else:
                _consecutive_silence_count += 1
                continue

        except sr.UnknownValueError:
            _consecutive_silence_count += 1
        except sr.RequestError as e:
            error_message = f"Could not request results; {e}"
            await handle_error(error_message, state_task, i2c_display)
        except Exception as e:
            error_message = f"Something Went Wrong: {e}"
            await handle_error(error_message, state_task, i2c_display)


i2c_display = None  # Global I2C display reference


def _get_host_ip() -> str:
    """Get host LAN IP address."""
    import subprocess

    try:
        result = subprocess.run(
            ["nsenter", "-t", "1", "-n", "hostname", "-I"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().split()[0]
    except Exception:
        pass

    return "gpt-home.local"


async def _init_tables():
    """Initialize database tables."""
    pool = await get_db_pool()
    async with pool.connection() as conn:
        await conn.execute("""
                    CREATE TABLE IF NOT EXISTS gallery_images (
                        id SERIAL PRIMARY KEY,
                        filename VARCHAR(255) UNIQUE NOT NULL,
                        data BYTEA NOT NULL,
                        mime_type VARCHAR(100) NOT NULL,
                        size INTEGER NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

        await conn.execute("""
                    CREATE TABLE IF NOT EXISTS app_settings (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

        await conn.execute("""
                    CREATE TABLE IF NOT EXISTS integrations (
                        id SERIAL PRIMARY KEY,
                        name TEXT UNIQUE NOT NULL,
                        fields JSONB NOT NULL DEFAULT '{}'::jsonb,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
        await conn.commit()


async def startup():
    """Initialize system and run main loop."""
    global i2c_display
    i2c_display = await initialize_system()

    await _init_tables()

    try:
        from src.waveform import WaveformSource, get_waveform_mediator

        mediator = get_waveform_mediator()
        if get_audio_activity_detector:
            mediator.set_audio_detector(get_audio_activity_detector())

        # Wire continuous mic capture to waveform mediator for always-on visualization
        from src.audio_capture import set_mic_callback, start_mic_capture

        def _continuous_mic_callback(values: list):
            mediator.update_from_values(values)

        set_mic_callback(_continuous_mic_callback)
        mediator.start(WaveformSource.MICROPHONE)
        start_mic_capture()
        logger.debug("Continuous mic capture started for waveform")
    except Exception as e:
        logger.error("Waveform mediator init failed: %s", e)

    api_key = os.getenv("LITELLM_API_KEY")

    if not api_key and i2c_display:
        i2c_display.fill(0)
        ip_address = _get_host_ip()
        i2c_display.text("Missing API Key", 0, 0, 1)
        i2c_display.text("To update it, visit:", 0, 10, 1)
        if ip_address:
            i2c_display.text(f"{ip_address}/settings", 0, 20, 1)
        else:
            i2c_display.text("gpt-home.local/settings", 0, 20, 1)
        i2c_display.show()

    await main()
