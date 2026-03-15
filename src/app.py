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
    """Check for voice activity using AudioCapture's already-open stream.

    Reads buffered audio from the mic capture thread instead of opening a new
    sr.Microphone — avoids the stop/start cycle that causes WM8960 speaker pops.
    """
    import audioop
    import math

    try:
        from src.audio_capture import get_mic_audio

        settings = load_settings()
        vad_threshold_db = settings.get("vadThresholdDb", -50.0)

        audio_data, sample_rate, sample_width = get_mic_audio(0.5)
        if not audio_data:
            return False, -100.0, vad_threshold_db

        rms = audioop.rms(audio_data, sample_width)
        max_val = (1 << (8 * sample_width - 1)) - 1
        db_level = 20 * math.log10(rms / max_val + 1e-10) if rms > 0 else -100.0

        if get_audio_activity_detector:
            detector = get_audio_activity_detector()
            detector.configure(vad_threshold_db=vad_threshold_db)

            vad_sample_rate = 16000
            vad_audio = audio_data
            if sample_rate != vad_sample_rate:
                vad_audio, _ = audioop.ratecv(
                    audio_data, sample_width, 1, sample_rate, vad_sample_rate, None
                )

            has_voice = detector.detect_voice(
                vad_audio, sample_width=sample_width, sample_rate=vad_sample_rate
            )
            return has_voice, db_level, vad_threshold_db
        else:
            return db_level > vad_threshold_db, db_level, vad_threshold_db

    except Exception as e:
        if not getattr(_check_audio_level_sync, "_last_error_logged", None) == str(e):
            logger.error("Audio level check error: %s", e)
            _check_audio_level_sync._last_error_logged = str(e)
        return False, -100.0, -50.0


async def check_audio_level_above_threshold() -> bool:
    """Quick check if voice is detected using WebRTC VAD."""
    loop = asyncio.get_running_loop()
    has_voice, db, threshold = await loop.run_in_executor(None, _check_audio_level_sync)

    if has_voice:
        logger.info("Voice detected: %.1f dB (VAD triggered)", db)

    return has_voice


async def idle_loop():
    global _idle_mode_active

    _idle_mode_active = True
    logger.info("Entering idle mode")

    from src.display.auxiliary import (
        check_screensaver_all,
        restore_all_headers,
    )

    await restore_all_headers()

    try:
        while _idle_mode_active:
            has_audio = await check_audio_level_above_threshold()

            if has_audio:
                logger.info("Audio detected, exiting idle mode")
                register_all_display_activity()

                dm = get_display_manager()
                if dm and dm.is_available:
                    await dm.register_activity_async()

                _idle_mode_active = False
                await restore_all_headers()
                return True

            settings = load_settings()
            await check_screensaver_all(settings)
            await asyncio.sleep(_IDLE_CHECK_INTERVAL)

    except asyncio.CancelledError:
        _idle_mode_active = False
        await restore_all_headers()
        raise
    except Exception as e:
        logger.error("Error in idle loop: %s", e, exc_info=True)
        _idle_mode_active = False
        await restore_all_headers()
        return True

    return False


async def main():
    global _consecutive_silence_count, _idle_mode_active

    from src.display.auxiliary import restore_all_headers

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

                should_listen = await idle_loop()
                _consecutive_silence_count = 0

                if not should_listen:
                    continue

                await restore_all_headers()

            stop_event = asyncio.Event()
            state_task = asyncio.create_task(
                display_state("Listening", stop_event)
            )

            text = None
            try:
                text = await listen(state_task, stop_event)
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
                register_all_display_activity()

                clean_text = text.lower().translate(
                    str.maketrans("", "", string.punctuation)
                )
                logger.debug(f"[app] clean_text: {clean_text!r}, keyword: {keyword!r}")

                if keyword in clean_text:
                    actual_text = clean_text.split(keyword, 1)[1].strip()
                    logger.info("Keyword found, actual_text: %r", actual_text)
                    await duck_volume()
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
                        await speak_with_display(heard_message)

                    response_message = await query_task
                    logger.info("action_router returned: %r", response_message)
                    logger.success(response_message)

                    await speak_with_display(response_message)

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
            await handle_error(error_message, state_task)
        except Exception as e:
            error_message = f"Something Went Wrong: {e}"
            await handle_error(error_message, state_task)


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


async def _init_settings_from_db():
    pool = await get_db_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT value FROM app_settings WHERE key = 'settings'"
        )
        row = await cur.fetchone()

    if row:
        from src.common import load_settings, set_settings_cache
        db_settings = json.loads(row[0])
        file_settings = load_settings()
        merged = {**file_settings, **db_settings}
        for key in merged:
            if isinstance(file_settings.get(key), dict) and isinstance(db_settings.get(key), dict):
                merged[key] = {**file_settings[key], **db_settings[key]}
        set_settings_cache(merged)
        logger.debug("Settings loaded from database")
    else:
        from src.common import load_settings, set_settings_cache
        defaults = load_settings()
        set_settings_cache(defaults)
        async with pool.connection() as conn:
            await conn.execute(
                "INSERT INTO app_settings (key, value, updated_at) VALUES ('settings', %s, NOW())",
                (json.dumps(defaults),)
            )
            await conn.commit()
        logger.info("Settings seeded into database from defaults")


async def startup():
    await _init_tables()
    await _init_settings_from_db()

    await initialize_system()

    try:
        from src.waveform import WaveformSource, get_waveform_mediator

        mediator = get_waveform_mediator()
        if get_audio_activity_detector:
            mediator.set_audio_detector(get_audio_activity_detector())

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
    if not api_key:
        from src.display.auxiliary import get_all_auxiliary, show_message_all

        if get_all_auxiliary():
            import subprocess

            try:
                result = subprocess.run(
                    ["nsenter", "-t", "1", "-n", "hostname", "-I"],
                    capture_output=True, text=True, timeout=5,
                )
                ip = result.stdout.strip().split()[0] if result.returncode == 0 else ""
            except Exception:
                ip = ""
            url = f"{ip}/settings" if ip else "gpt-home.local/settings"
            await show_message_all(["Missing API Key", "To update it, visit:", url])

    await main()
