import warnings

# Suppress Pydantic V2 config warnings before any imports
warnings.filterwarnings("ignore", message="Valid config keys have changed in V2")
# Suppress Pydantic serialization warnings from LiteLLM
warnings.filterwarnings("ignore", message="Pydantic serializer warnings")
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")
# Suppress LangChain deprecation warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module="langchain")

import asyncio
import audioop
import json
import logging
import math
import os
import re
import string
import struct
import subprocess
import tempfile
import textwrap
import threading
import time
import traceback
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from ctypes import CFUNCTYPE, c_char_p, c_int, cdll
from datetime import datetime, timedelta
from pathlib import Path
from threading import Timer

import aiohttp
import busio
import caldav
import litellm
import pyttsx3
import requests
import speech_recognition as sr
from dotenv import load_dotenv
from phue import Bridge


def _configure_alsa_for_pyaudio():
    """Configure ALSA before PyAudio/speech_recognition is imported.

    PortAudio can crash with assertion failures during Pa_Initialize() if
    no valid default input device is configured. This ensures /etc/asound.conf
    has an asymmetric config with a valid capture device.
    """
    try:
        asound_path = "/etc/asound.conf"

        # Check if asound.conf exists and already has capture configured
        if os.path.exists(asound_path):
            with open(asound_path, "r") as f:
                content = f.read()
            if "capture.pcm" in content:
                return

        # Find microphone card
        result = subprocess.run(
            ["arecord", "-l"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0 or "card" not in result.stdout.lower():
            return

        mic_priorities = [("usb", 100), ("microphone", 90), ("mic", 80), ("audio", 70)]
        best_card = None
        best_priority = -1

        for line in result.stdout.lower().split("\n"):
            if "card" not in line:
                continue
            card_match = re.search(r"card\s+(\d+):", line)
            if card_match:
                card_num = card_match.group(1)
                for keyword, priority in mic_priorities:
                    if keyword in line and priority > best_priority:
                        best_card = card_num
                        best_priority = priority
                        break

        if not best_card:
            first_match = re.search(r"card\s+(\d+):", result.stdout.lower())
            if first_match:
                best_card = first_match.group(1)

        if not best_card:
            return

        # Get playback card from existing config or default to 0
        playback_card = "0"
        if os.path.exists(asound_path):
            with open(asound_path, "r") as f:
                content = f.read()
            card_match = re.search(r"card\s+(\w+)", content)
            if card_match:
                playback_card = card_match.group(1)

        asound_config = f"""pcm.!default {{
    type asym
    playback.pcm {{
        type plug
        slave.pcm "hw:{playback_card},0"
    }}
    capture.pcm {{
        type plug
        slave.pcm "hw:{best_card},0"
    }}
}}
ctl.!default {{
    type hw
    card {playback_card}
}}
"""
        with open(asound_path, "w") as f:
            f.write(asound_config)
        print(
            f"[AUDIO] Configured asound.conf: playback=card {playback_card}, capture=card {best_card}",
            flush=True,
        )
    except Exception as e:
        print(f"[AUDIO] Failed to configure ALSA: {e}", flush=True)


_configure_alsa_for_pyaudio()


# Suppress ALSA error messages (from StackOverflow)
# These are harmless debug messages that clutter logs
def _py_error_handler(filename, line, function, err, fmt):
    pass


_ERROR_HANDLER_FUNC = CFUNCTYPE(None, c_char_p, c_int, c_char_p, c_int, c_char_p)
_c_error_handler = _ERROR_HANDLER_FUNC(_py_error_handler)

try:
    _asound = cdll.LoadLibrary("libasound.so.2")
    _asound.snd_lib_error_set_handler(_c_error_handler)
except OSError:
    pass  # libasound not available

# Suppress JACK error messages
_JACK_ERROR_HANDLER_FUNC = CFUNCTYPE(None, c_char_p)


def _py_jack_error_handler(msg):
    pass


_jack_error_handler = _JACK_ERROR_HANDLER_FUNC(_py_jack_error_handler)

try:
    _jack = cdll.LoadLibrary("libjack.so.0")
    _jack.jack_set_error_function(_jack_error_handler)
    _jack.jack_set_info_function(_jack_error_handler)
except OSError:
    pass  # libjack not available

# Suppress pygame welcome message
import os

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"


# Set SDL audio environment variables from asound.conf so pygame uses the correct device
# This must happen before pygame/mixer is imported
def _init_audio_env():
    """Read asound.conf and set SDL environment variables for pygame.

    The asound.conf may have separate playback and capture cards (asym config).
    We need to specifically extract the PLAYBACK device for audio output.

    For HDMI devices, the config uses named devices like "hdmi:CARD=vc4hdmi0,DEV=0"
    which handle IEC958 format conversion automatically.
    """
    try:
        asound_path = Path("/etc/asound.conf")
        if asound_path.exists():
            import re

            content = asound_path.read_text()

            # First check for named HDMI device (hdmi:CARD=xxx,DEV=0)
            # This is used for Raspberry Pi HDMI audio which requires IEC958 format
            hdmi_match = re.search(
                r'playback\.pcm\s*\{[^}]*slave\.pcm\s*"(hdmi:CARD=\w+,DEV=\d+)"',
                content,
                re.DOTALL,
            )

            if hdmi_match:
                # Use the full HDMI device name
                audiodev = hdmi_match.group(1)
                os.environ["AUDIODEV"] = audiodev
                os.environ["SDL_AUDIODRIVER"] = "alsa"
                print(
                    f"[AUDIO] Configured HDMI audio output: AUDIODEV={audiodev}",
                    flush=True,
                )
                return

            # Try to find playback.pcm card (for asym configs with separate I/O)
            # Match patterns like: playback.pcm { ... slave.pcm "hw:2,0" ... }
            playback_match = re.search(
                r'playback\.pcm\s*\{[^}]*slave\.pcm\s*"(?:plug)?hw:(\d+)',
                content,
                re.DOTALL,
            )

            if playback_match:
                card = playback_match.group(1)
            else:
                # Fallback: look for ctl.!default card (main control device)
                ctl_match = re.search(
                    r"ctl\.!default\s*\{[^}]*card\s+(\d+)", content, re.DOTALL
                )
                if ctl_match:
                    card = ctl_match.group(1)
                else:
                    # Last resort: first card mentioned
                    match = re.search(r"card\s+(\w+)", content)
                    card = match.group(1) if match else None

            if card:
                # Use plughw instead of hw for better compatibility
                # plughw handles format conversion automatically
                os.environ["AUDIODEV"] = f"plughw:{card},0"
                os.environ["SDL_AUDIODRIVER"] = "alsa"
                print(
                    f"[AUDIO] Configured audio output: card={card}, AUDIODEV=plughw:{card},0",
                    flush=True,
                )
            else:
                print("[AUDIO] No playback card found in asound.conf", flush=True)
        else:
            print("[AUDIO] /etc/asound.conf not found, using defaults", flush=True)
    except Exception as e:
        print(f"[AUDIO] Error reading asound.conf: {e}", flush=True)


_init_audio_env()

# TTS
import time
from io import BytesIO

from gtts import gTTS
from pygame import mixer

SOURCE_DIR = Path(__file__).parent
ROOT_DIR = SOURCE_DIR.parent
log_file_path = Path("/app/logs/events.log")

# LiteLLM TTS/STT compatible providers (by API key prefix/pattern)
LITELLM_TTS_PROVIDERS = {
    "sk-": "openai",  # OpenAI
    "sk-ant-": None,  # Anthropic - no TTS
    "AIza": "gemini",  # Google/Gemini
    "gsk_": "groq",  # Groq - STT only
}


def get_litellm_provider():
    """Detect provider from API key for TTS/STT support."""
    api_key = os.getenv("LITELLM_API_KEY", "")
    if not api_key:
        return None

    # Check specific patterns (order matters - more specific first)
    if api_key.startswith("sk-ant-"):
        return None  # Anthropic has no TTS/STT
    if api_key.startswith("sk-"):
        return "openai"
    if api_key.startswith("AIza"):
        return "gemini"
    if api_key.startswith("gsk_"):
        return "groq"

    return None


def litellm_tts_available():
    """Check if LiteLLM TTS is available for current provider."""
    provider = get_litellm_provider()
    return provider in ["openai", "gemini"]


def litellm_stt_available():
    """Check if LiteLLM STT is available for current provider."""
    provider = get_litellm_provider()
    return provider in ["openai", "groq", "gemini"]


# Load .env files - main .env for API keys, frontend/.env for other config
load_dotenv(dotenv_path=ROOT_DIR / ".env")
load_dotenv(dotenv_path=SOURCE_DIR / "frontend" / ".env", override=False)

# Add a new 'SUCCESS' logging level
logging.SUCCESS = 25  # Between INFO and WARNING
logging.addLevelName(logging.SUCCESS, "SUCCESS")


def success(self, message, *args, **kws):
    if self.isEnabledFor(logging.SUCCESS):
        self._log(logging.SUCCESS, message, args, **kws)


logging.Logger.success = success


# Custom handler that flushes after every write (for real-time SSE)
class FlushingFileHandler(logging.FileHandler):
    def emit(self, record):
        super().emit(record)
        self.flush()


# Configure logging with immediate flush for SSE real-time updates
handler = FlushingFileHandler(log_file_path)
handler.setLevel(logging.DEBUG)
handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
logging.root.addHandler(handler)
logging.root.setLevel(logging.DEBUG)

logger = logging.getLogger(__name__)

# Suppress noisy third-party loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("langsmith").setLevel(logging.WARNING)
logging.getLogger("LiteLLM").setLevel(logging.ERROR)
logging.getLogger("LiteLLM Proxy").setLevel(logging.ERROR)
logging.getLogger("litellm").setLevel(logging.ERROR)

try:
    from board import SCL, SDA
except Exception:
    logger.debug(
        "Board not detected. Skipping... \n    Reason: {e}\n{traceback.format_exc()}"
    )
try:
    import adafruit_ssd1306
except Exception as e:
    logger.debug(
        f"Failed to import adafruit_ssd1306. Skipping...\n    Reason: {e}\n{traceback.format_exc()}"
    )

executor = ThreadPoolExecutor()

# Display manager reference - set by app.py after initialization
import sys

_display_manager = None

sys.modules["common"] = sys.modules[__name__]
if "src.common" in sys.modules:
    sys.modules["src.common"] = sys.modules[__name__]


def set_display_manager(manager):
    """Set the display manager reference for direct calls instead of HTTP."""
    global _display_manager
    _display_manager = manager


def get_display_manager():
    """Get the display manager reference."""
    return _display_manager


async def show_tool_animation(tool_name: str, context: dict = None):
    """Show a tool animation on the display manager.

    This should be called by tools when they start executing to show
    a contextual animation on SMART display mode.

    Args:
        tool_name: Name of the tool (e.g., "weather", "timer", "spotify", "lights")
        context: Optional context dict with tool-specific data like:
            - weather: {"requested_location": "New York"}
            - timer: {"duration": 300, "name": "Timer"}
            - spotify: {"track": "...", "artist": "..."}
            - lights: {"action": "on"}
    """
    print(f"[TOOL_ANIMATION] Tool: {tool_name}, Context: {context}", flush=True)
    dm = get_display_manager()
    if dm and dm.is_available:
        await dm.show_tool_animation(tool_name, context or {}, "")


def show_tool_animation_sync(tool_name: str, context: dict = None):
    """Synchronous wrapper for show_tool_animation.

    Use this from synchronous tool code.
    """
    import asyncio

    print(f"[TOOL_ANIMATION_SYNC] Tool: {tool_name}, Context: {context}", flush=True)
    dm = get_display_manager()
    if dm and dm.is_available:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    dm.show_tool_animation(tool_name, context or {}, ""), loop
                )
            else:
                loop.run_until_complete(
                    dm.show_tool_animation(tool_name, context or {}, "")
                )
        except Exception:
            pass


# Initialize the speech recognition engine
r = sr.Recognizer()

_cached_mic_index = None
_mic_index_checked = False
_cached_alsa_card = None


def _find_alsa_microphone_card():
    """Find the best ALSA card number for microphone input.

    Returns the ALSA card number (not PyAudio index).
    """
    try:
        result = subprocess.run(
            ["arecord", "-l"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode != 0:
            return None

        mic_priorities = [
            ("usb", 100),
            ("microphone", 90),
            ("mic", 80),
            ("audio", 70),
        ]

        best_card = None
        best_priority = -1

        for line in result.stdout.lower().split("\n"):
            if "card" not in line:
                continue

            try:
                card_match = re.search(r"card\s+(\d+):", line)
                if not card_match:
                    continue
                card_num = int(card_match.group(1))

                for keyword, priority in mic_priorities:
                    if keyword in line and priority > best_priority:
                        best_card = card_num
                        best_priority = priority
                        break
            except (ValueError, AttributeError):
                continue

        if best_card is None and result.stdout.strip():
            try:
                first_card = re.search(r"card\s+(\d+):", result.stdout.lower())
                if first_card:
                    best_card = int(first_card.group(1))
            except (ValueError, AttributeError):
                pass

        return best_card

    except Exception:
        return None


def _find_pyaudio_index_for_alsa_card(alsa_card: int):
    """Convert ALSA card number to PyAudio device index.

    PyAudio device indices are different from ALSA card numbers.
    This function enumerates PyAudio devices and finds the one
    corresponding to the given ALSA card.

    Args:
        alsa_card: ALSA card number from arecord -l

    Returns:
        PyAudio device index or None if not found
    """
    import pyaudio

    try:
        p = pyaudio.PyAudio()
        device_count = p.get_device_count()

        print(f"[STT] PyAudio device count: {device_count}", flush=True)

        # First pass: look for exact hw:N match in device name
        for i in range(device_count):
            try:
                info = p.get_device_info_by_index(i)
                name = info.get("name", "")
                max_input = info.get("maxInputChannels", 0)
                sample_rate = info.get("defaultSampleRate", 0)

                if max_input > 0:
                    print(
                        f"[STT]   Input device {i}: {name} (inputs={max_input}, rate={sample_rate})",
                        flush=True,
                    )

                    # Match patterns like "hw:1,0" or "(hw:1,0)" in device name
                    if f"hw:{alsa_card}," in name or f"hw:{alsa_card})" in name:
                        p.terminate()
                        return i

                    # Also match plughw
                    if f"plughw:{alsa_card}," in name or f"plughw:{alsa_card})" in name:
                        p.terminate()
                        return i
            except Exception:
                continue

        # Second pass: match by device name keywords (USB, mic, etc.)
        # This is a fallback if the hw:N pattern doesn't match
        mic_priorities = [
            ("usb", 100),
            ("microphone", 90),
            ("mic", 80),
            ("audio", 70),
        ]

        best_idx = None
        best_priority = -1

        for i in range(device_count):
            try:
                info = p.get_device_info_by_index(i)
                name = info.get("name", "").lower()
                max_input = info.get("maxInputChannels", 0)

                if max_input > 0:
                    # Skip monitor/loopback devices
                    if "monitor" in name or "loopback" in name:
                        continue

                    for keyword, priority in mic_priorities:
                        if keyword in name and priority > best_priority:
                            best_idx = i
                            best_priority = priority
                            break
            except Exception:
                continue

        p.terminate()
        return best_idx

    except Exception as e:
        print(f"[STT] Error enumerating PyAudio devices: {e}", flush=True)
        return None


def _find_microphone_device_index():
    """Find the best available microphone device index for speech recognition.

    Returns the PyAudio device index or None if no suitable device is found.
    Result is cached to avoid repeated device enumeration.

    IMPORTANT: This returns a PyAudio device index, NOT an ALSA card number.
    PyAudio indices are different from ALSA card numbers and must be used
    with sr.Microphone(device_index=...).
    """
    global _cached_mic_index, _mic_index_checked, _cached_alsa_card

    if _mic_index_checked:
        return _cached_mic_index

    _mic_index_checked = True

    # First find the ALSA card
    _cached_alsa_card = _find_alsa_microphone_card()

    if _cached_alsa_card is None:
        logger.warning("No ALSA microphone card found")
        return None

    logger.debug(f"Found microphone device via ALSA: card {_cached_alsa_card}")

    # Convert ALSA card to PyAudio index
    _cached_mic_index = _find_pyaudio_index_for_alsa_card(_cached_alsa_card)

    if _cached_mic_index is not None:
        logger.debug(
            f"Mapped ALSA card {_cached_alsa_card} to PyAudio index {_cached_mic_index}"
        )
    else:
        logger.warning(
            f"Could not find PyAudio index for ALSA card {_cached_alsa_card}"
        )

    return _cached_mic_index


# Configure speech recognizer with fixed energy threshold
r.energy_threshold = 50  # Low fixed threshold - let VAD handle speech detection
r.dynamic_energy_threshold = (
    False  # Disabled - was adjusting upward and rejecting speech
)
r.phrase_threshold = 0.3  # Minimum seconds of speech to consider a phrase


def _load_speech_timing_settings():
    """Load speech recognition timing settings from settings.json."""
    try:
        with open(SOURCE_DIR / "settings.json", "r") as f:
            settings = json.load(f)
        r.pause_threshold = settings.get("pauseThreshold", 1.2)
        r.non_speaking_duration = settings.get("nonSpeakingDuration", 0.8)
    except Exception:
        r.pause_threshold = 1.2
        r.non_speaking_duration = 0.8


_load_speech_timing_settings()


def get_phrase_time_limit():
    """Get phrase time limit from settings."""
    try:
        with open(SOURCE_DIR / "settings.json", "r") as f:
            settings = json.load(f)
        return settings.get("phraseTimeLimit", 30)
    except Exception:
        return 30


def reload_speech_timing_settings():
    """Reload speech timing settings from settings.json. Call after settings change."""
    _load_speech_timing_settings()


def calibrate_ambient_noise(duration: float = 1.0):
    """Calibrate the recognizer for ambient noise levels.

    Call this periodically or when the environment changes to improve
    speech detection accuracy and reduce false positives.
    """
    try:
        mic_index = _find_microphone_device_index()
        with sr.Microphone(device_index=mic_index) as source:
            logger.debug(f"Calibrating ambient noise for {duration}s...")
            r.adjust_for_ambient_noise(source, duration=duration)
            logger.debug(
                f"Ambient noise calibration complete. Energy threshold: {r.energy_threshold}"
            )
    except Exception as e:
        logger.warning(f"Ambient noise calibration failed: {e}")


def audio_has_speech(
    audio_data: sr.AudioData,
    threshold_db: float = -35.0,
    min_duration: float = 1.0,
) -> bool:
    """Check if audio contains speech. Rejects short/quiet audio to prevent Whisper hallucinations."""
    try:
        raw_data = audio_data.get_raw_data()
        duration = len(raw_data) / (audio_data.sample_rate * audio_data.sample_width)

        if duration < min_duration:
            print(
                f"[VAD] Audio too short: {duration:.2f}s < {min_duration}s, rejecting",
                flush=True,
            )
            return False

        from src.audio_activity import get_audio_activity_detector

        detector = get_audio_activity_detector()
        detector.configure(vad_threshold_db=threshold_db)
        metrics = detector.analyze_audio_data(audio_data)

        has_speech = metrics.db_level > threshold_db

        max_val = (1 << (8 * audio_data.sample_width - 1)) - 1
        peak_val = audioop.max(raw_data, audio_data.sample_width)
        peak_ratio = peak_val / max_val
        if peak_ratio < 0.005:
            print(f"[VAD] Peak too low: {peak_ratio:.3f}, rejecting", flush=True)
            has_speech = False

        print(
            f"[VAD] dB={metrics.db_level:.1f}, threshold={threshold_db}, "
            f"duration={duration:.2f}s, peak={peak_ratio:.3f}, has_speech={has_speech}",
            flush=True,
        )
        return has_speech

    except Exception as e:
        logger.warning(f"VAD check failed: {e}, assuming speech present")
        return True


litellm.api_key = os.getenv("LITELLM_API_KEY", "")

# Initialize the text-to-speech engine
engine = pyttsx3.init()
# Set properties
engine.setProperty("rate", 145)
engine.setProperty("volume", 1.0)
# Direct audio to specific hardware
engine.setProperty("alsa_device", "hw:Headphones,0")
speak_lock = asyncio.Lock()
display_lock = asyncio.Lock()

# I2C display screensaver state
_i2c_display_screensaver_active = False
_i2c_display_last_activity_time = time.time()
_i2c_display_screensaver_task = None
_i2c_display_screensaver_render_task = None
_i2c_display_ref = None


def draw_i2c_header(display):
    """Draw the IP address and CPU temperature header on the I2C display.

    This should be called whenever the display needs to restore its header
    (after screensaver, after listening waveform, etc.).
    """
    if display is None:
        return

    ip_to_show = ""
    try:
        result = subprocess.run(
            ["nsenter", "-t", "1", "-n", "hostname", "-I"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            ip_to_show = result.stdout.strip().split()[0]
    except Exception:
        pass

    if not ip_to_show:
        try:
            with open("/run/gpt-home/host-ip", "r") as f:
                ip_to_show = f.read().strip()
        except Exception:
            pass

    if ip_to_show:
        display.text(f"{ip_to_show}", 0, 0, 1)

    try:
        cpu_temp = int(
            float(
                subprocess.check_output(["vcgencmd", "measure_temp"])
                .decode("utf-8")
                .split("=")[1]
                .split("'")[0]
            )
        )
        temp_text_x = 100
        display.text(f"{cpu_temp}", temp_text_x, 0, 1)
        degree_x = 100 + len(f"{cpu_temp}") * 7
        degree_y = 2
        degree_symbol(display, degree_x, degree_y, 2, 1)
        c_x = degree_x + 7
        display.text("C", c_x, 0, 1)
    except Exception:
        pass


def i2c_display_register_activity():
    """Register activity on I2C display to reset screensaver timer and wake display."""
    global \
        _i2c_display_last_activity_time, \
        _i2c_display_screensaver_active, \
        _i2c_display_screensaver_render_task
    _i2c_display_last_activity_time = time.time()
    if _i2c_display_screensaver_active:
        _i2c_display_screensaver_active = False
        if (
            _i2c_display_screensaver_render_task
            and not _i2c_display_screensaver_render_task.done()
        ):
            _i2c_display_screensaver_render_task.cancel()
        _i2c_display_screensaver_render_task = None
        if _i2c_display_ref is not None:
            _i2c_display_ref.fill(0)
            draw_i2c_header(_i2c_display_ref)
            _i2c_display_ref.show()


def register_all_display_activity():
    """Register activity on both I2C display and full display manager."""
    i2c_display_register_activity()
    dm = get_display_manager()
    if dm and dm.is_available:
        dm.register_activity()


async def i2c_display_check_screensaver(display):
    """Check if I2C display screensaver should activate."""
    global _i2c_display_screensaver_active, _i2c_display_screensaver_render_task

    if display is None:
        return

    settings = load_settings()
    if not settings.get("screensaver_enabled", True):
        return

    if _i2c_display_screensaver_active:
        return

    timeout = float(settings.get("screensaver_timeout", 300))
    elapsed = time.time() - _i2c_display_last_activity_time

    if elapsed >= timeout:
        _i2c_display_screensaver_active = True
        logger.info(
            f"I2C display screensaver activated after {elapsed:.0f}s of inactivity"
        )
        _i2c_display_screensaver_render_task = asyncio.create_task(
            _i2c_display_screensaver_animation(display)
        )


async def _i2c_display_screensaver_animation(display):
    """Animated screensaver for I2C OLED - moving dots to prevent burn-in."""
    import random

    dots = []
    for _ in range(5):
        dots.append(
            {
                "x": random.randint(0, 127),
                "y": random.randint(0, 31),
                "vx": random.choice([-1, 1]) * random.uniform(0.5, 1.5),
                "vy": random.choice([-1, 1]) * random.uniform(0.3, 0.8),
            }
        )

    try:
        while _i2c_display_screensaver_active:
            async with display_lock:
                display.fill(0)

                for dot in dots:
                    dot["x"] += dot["vx"]
                    dot["y"] += dot["vy"]

                    if dot["x"] <= 0 or dot["x"] >= 127:
                        dot["vx"] = -dot["vx"]
                        dot["x"] = max(0, min(127, dot["x"]))
                    if dot["y"] <= 0 or dot["y"] >= 31:
                        dot["vy"] = -dot["vy"]
                        dot["y"] = max(0, min(31, dot["y"]))

                    x, y = int(dot["x"]), int(dot["y"])
                    display.pixel(x, y, 1)
                    if x > 0:
                        display.pixel(x - 1, y, 1)
                    if x < 127:
                        display.pixel(x + 1, y, 1)
                    if y > 0:
                        display.pixel(x, y - 1, 1)
                    if y < 31:
                        display.pixel(x, y + 1, 1)

                display.show()

            await asyncio.sleep(0.05)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"I2C screensaver animation error: {e}")
    finally:
        async with display_lock:
            display.fill(0)
            draw_i2c_header(display)
            display.show()


async def i2c_display_restore_header(display):
    """Restore the I2C display header after screensaver or other full-screen state."""
    if display is None:
        return
    async with display_lock:
        display.fill(0)
        draw_i2c_header(display)
        display.show()


async def i2c_display_screensaver_monitor(display):
    """Background task to monitor I2C display inactivity and activate screensaver."""
    global _i2c_display_screensaver_task
    try:
        while True:
            await asyncio.sleep(10)  # Check every 10 seconds
            await i2c_display_check_screensaver(display)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"I2C display screensaver monitor error: {e}")


def start_i2c_display_screensaver_monitor(display):
    """Start the I2C display screensaver monitor task."""
    global _i2c_display_screensaver_task
    if _i2c_display_screensaver_task is None or _i2c_display_screensaver_task.done():
        _i2c_display_screensaver_task = asyncio.create_task(
            i2c_display_screensaver_monitor(display)
        )
        logger.debug("I2C display screensaver monitor started")


def is_i2c_display_screensaver_active():
    """Check if I2C display screensaver is currently active."""
    return _i2c_display_screensaver_active


# Public alias for _find_microphone_device_index (for use in app.py)
def find_microphone_device_index():
    """Find the best available microphone device index for speech recognition.

    Public wrapper for _find_microphone_device_index.
    Returns PyAudio device index (not ALSA card number).
    """
    return _find_microphone_device_index()


def reset_microphone_cache():
    """Reset the cached microphone device index.

    Call this when audio devices may have changed (e.g., USB device plugged in).
    """
    global _cached_mic_index, _mic_index_checked, _cached_alsa_card
    _cached_mic_index = None
    _mic_index_checked = False
    _cached_alsa_card = None


def network_connected():
    try:
        response = requests.get("http://www.google.com", timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False


async def load_integration_statuses() -> dict[str, bool]:
    from backend import get_db_pool

    pool = await get_db_pool()
    async with pool.connection() as conn:
        cur = await conn.execute("SELECT name, fields::text FROM integrations")
        rows = await cur.fetchall()

    data = {}
    for name, fields_text in rows or []:
        try:
            data[name.lower()] = json.loads(fields_text)
        except Exception:
            data[name.lower()] = {}

    def has_keys(d: dict, keys: list[str]) -> bool:
        return all(bool(d.get(k, "").strip()) for k in keys)

    return {
        "spotify": has_keys(data.get("spotify", {}), ["CLIENT ID", "CLIENT SECRET"]),
        "openweather": has_keys(data.get("openweather", {}), ["API KEY"]),
        "philipshue": has_keys(
            data.get("philipshue", {}), ["BRIDGE IP ADDRESS", "USERNAME"]
        ),
        "caldav": has_keys(data.get("caldav", {}), ["URL", "USERNAME", "PASSWORD"]),
    }


# Manually draw a degree symbol °
def degree_symbol(display, x, y, radius, color):
    for i in range(x - radius, x + radius + 1):
        for j in range(y - radius, y + radius + 1):
            if (i - x) ** 2 + (j - y) ** 2 <= radius**2:
                display.pixel(i, j, color)
                # clear center of circle
                if (i - x) ** 2 + (j - y) ** 2 <= (radius - 1) ** 2:
                    display.pixel(i, j, 0)


async def calculate_delay(message):
    """Legacy delay calculation - kept for backward compatibility."""
    base_delay = 0.02
    extra_delay = 0.0

    # Patterns to look for
    patterns = [r": ", r"\. ", r"\? ", r"! ", r"\.{2,}", r", ", r"\n"]

    for pattern in patterns:
        extra_delay += (
            len(re.findall(pattern, message)) * 0.001
        )  # Add 0.001 seconds for each match

    return base_delay + extra_delay


def estimate_word_duration(word, base_wpm=150):
    """
    Estimate how long a word takes to speak based on syllables and punctuation.
    Returns duration in seconds.
    """
    # Count syllables (rough estimate based on vowel groups)
    vowels = "aeiouyAEIOUY"
    syllables = 0
    prev_vowel = False
    for char in word:
        is_vowel = char in vowels
        if is_vowel and not prev_vowel:
            syllables += 1
        prev_vowel = is_vowel
    syllables = max(1, syllables)  # At least 1 syllable

    # Base duration: average word is ~0.4s at 150 WPM
    base_duration = (syllables / 2.5) * (60 / base_wpm)

    # Add pause for punctuation
    if word.endswith((".", "!", "?")):
        base_duration += 0.3  # Sentence-ending pause
    elif word.endswith((",", ";", ":")):
        base_duration += 0.15  # Clause pause

    return base_duration


def init_i2c_display():
    """Initialize the I2C display (SSD1306).

    Returns the display object or None if initialization fails.
    """
    try:
        import os

        i2c = busio.I2C(SCL, SDA)
        display = adafruit_ssd1306.SSD1306_I2C(128, 32, i2c)
        display.rotation = 2
        display.fill(0)
        draw_i2c_header(display)
        display.show()
        logger.debug("I2C display initialized successfully")
        return display
    except Exception as e:
        logger.debug(f"I2C display init failed: {e}")
        return None


async def initialize_system():
    """Initialize the system including I2C display and network connection."""
    global _i2c_display_ref
    display = init_i2c_display()
    stop_event_init = asyncio.Event()
    state_task = asyncio.create_task(
        display_state("Connecting", display, stop_event_init)
    )
    while not network_connected():
        await asyncio.sleep(1)
        message = "Network not connected. Retrying..."
        logger.info(message)
    stop_event_init.set()  # Signal to stop the 'Connecting' display
    state_task.cancel()  # Cancel the display task
    display = init_i2c_display()  # Reinitialize the display

    # Store reference and start screensaver monitor
    if display is not None:
        _i2c_display_ref = display
        start_i2c_display_screensaver_monitor(display)

    return display


def load_settings():
    settings_path = SOURCE_DIR / "settings.json"
    with open(settings_path, "r") as f:
        settings = json.load(f)
        return settings


def save_settings(settings: dict):
    """Save settings to settings.json file."""
    settings_path = SOURCE_DIR / "settings.json"
    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2)


async def update_i2c_display(
    text, display, stop_event=None, delay=0.02, word_sync_event=None
):
    """
    Update I2C display with text.

    Args:
        text: Text to display
        display: I2C display object (SSD1306)
        stop_event: Event to signal when to stop
        delay: Delay between characters (legacy, used when word_sync_event is None)
        word_sync_event: asyncio.Event that gets set each time a word should be displayed
    """
    if display is None:
        return

    async with display_lock:
        if stop_event is None:
            stop_event = asyncio.Event()

        async def display_text_legacy(delay):
            """Legacy character-by-character display with fixed delay."""
            i = 0
            while not (stop_event and stop_event.is_set()) and i < line_count:
                if line_count > 2:
                    await display_lines_legacy(i, min(i + 2, line_count), delay)
                    i += 2
                else:
                    await display_lines_legacy(0, line_count, delay)
                    break
                await asyncio.sleep(0.02)

        async def display_lines_legacy(start, end, delay):
            display.fill_rect(0, 10, 128, 22, 0)
            for i, line_index in enumerate(range(start, end)):
                for j, char in enumerate(lines[line_index]):
                    if stop_event.is_set():
                        break
                    try:
                        display.text(char, j * 6, 10 + i * 10, 1)
                    except struct.error as e:
                        logger.error(f"Struct Error: {e}, skipping character {char}")
                        continue
                    display.show()
                    await asyncio.sleep(delay)

        def init_display_header():
            """Initialize display with IP and temp header."""
            display.fill(0)
            draw_i2c_header(display)
            display.show()

        init_display_header()
        lines = textwrap.fill(text, 21).split("\n")
        line_count = len(lines)
        await display_text_legacy(delay)


_waveform_values = deque([0.0] * 32, maxlen=32)
_waveform_send_lock = threading.Lock()
_last_waveform_send = 0.0
_streaming_waveform_active = False


def _send_waveform_to_backend(values: list, has_voice: bool = False):
    """Send waveform amplitude values to the display manager.

    Args:
        values: List of 32 amplitude values
        has_voice: Whether voice was detected (from WebRTC VAD)
    """
    global _last_waveform_send
    now = time.time()
    if now - _last_waveform_send < 0.033:
        return
    _last_waveform_send = now
    dm = get_display_manager()
    if dm and dm.is_available:
        dm.set_waveform_values(values, has_voice=has_voice)


def _update_waveform_from_chunk(audio_chunk: sr.AudioData):
    """Update waveform visualization from a single audio chunk in real-time."""
    global _waveform_values
    try:
        from src.audio_activity import get_audio_activity_detector

        detector = get_audio_activity_detector()
        values_list = detector.update_waveform(audio_chunk)

        with _waveform_send_lock:
            for i, val in enumerate(values_list):
                _waveform_values[i] = val

        max_amp = max(values_list) if values_list else 0.0
        _send_waveform_to_backend(values_list, has_voice=max_amp > 0.02)
    except Exception as e:
        print(f"[WAVEFORM] chunk update error: {e}", flush=True)


def _notify_waveform_start_sync():
    """Start waveform display (synchronous)."""
    dm = get_display_manager()
    if dm and dm.is_available:
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    dm.start_waveform(source="microphone"), loop
                )
            else:
                loop.run_until_complete(dm.start_waveform(source="microphone"))
        except Exception:
            pass


def _notify_waveform_stop_sync():
    """Stop waveform display (synchronous)."""
    dm = get_display_manager()
    if dm and dm.is_available:
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(dm.stop_waveform(), loop)
            else:
                loop.run_until_complete(dm.stop_waveform())
        except Exception:
            pass


def _clear_waveform_values():
    """Reset waveform values to zero."""
    global _waveform_values
    try:
        from src.audio_activity import get_audio_activity_detector

        detector = get_audio_activity_detector()
        detector.clear_waveform()
    except Exception:
        pass
    with _waveform_send_lock:
        for i in range(32):
            _waveform_values[i] = 0.0
    _send_waveform_to_backend([0.0] * 32)


def _listen_with_streaming_waveform(source, timeout=3, phrase_time_limit=15):
    """Listen for audio with real-time waveform streaming."""
    global _streaming_waveform_active

    _streaming_waveform_active = True
    register_all_display_activity()
    _notify_waveform_start_sync()
    _clear_waveform_values()

    settings = load_settings()
    silence_seconds = settings.get("pauseThreshold", 1.2)

    WAITING, SPEAKING = 0, 1
    state = WAITING

    speech_frames = []
    pre_speech_buffer = []
    pre_speech_buffer_size = 10
    chunk_count = 0
    silence_chunks = 0
    speech_chunks = 0
    chunks_per_second = 30
    silence_chunks_needed = int(silence_seconds * chunks_per_second)
    min_baseline_chunks = 10
    min_speech_chunks = 45

    baseline_samples = []
    baseline_rms = 100
    speech_threshold = 200
    silence_threshold = 100

    try:
        print(f"[LISTEN] Starting (silence={silence_seconds}s)", flush=True)

        for audio_chunk in r.listen(
            source,
            timeout=timeout,
            phrase_time_limit=phrase_time_limit,
            stream=True,
        ):
            raw_data = audio_chunk.get_raw_data()
            _update_waveform_from_chunk(audio_chunk)
            chunk_count += 1

            try:
                rms = audioop.rms(raw_data, audio_chunk.sample_width)
            except Exception:
                rms = 0

            if state == WAITING:
                pre_speech_buffer.append(raw_data)
                if len(pre_speech_buffer) > pre_speech_buffer_size:
                    pre_speech_buffer.pop(0)

                baseline_samples.append(rms)
                if len(baseline_samples) >= min_baseline_chunks:
                    baseline_rms = sum(baseline_samples) / len(baseline_samples)
                    speech_threshold = max(baseline_rms * 2.5, baseline_rms + 100, 200)
                    silence_threshold = max(baseline_rms * 1.3, baseline_rms + 30)

                if (
                    len(baseline_samples) >= min_baseline_chunks
                    and rms > speech_threshold
                ):
                    state = SPEAKING
                    silence_chunks = 0
                    speech_chunks = 0
                    speech_frames.extend(pre_speech_buffer)
                    print(
                        f"[LISTEN] Speech at chunk {chunk_count}, rms={rms}, thresh={speech_threshold:.0f}, baseline={baseline_rms:.0f}",
                        flush=True,
                    )
                    register_all_display_activity()

            elif state == SPEAKING:
                speech_frames.append(raw_data)
                speech_chunks += 1
                if rms < silence_threshold:
                    silence_chunks += 1
                    if (
                        speech_chunks >= min_speech_chunks
                        and silence_chunks >= silence_chunks_needed
                    ):
                        print(
                            f"[LISTEN] Silence at chunk {chunk_count}, speech_chunks={speech_chunks}",
                            flush=True,
                        )
                        break
                else:
                    silence_chunks = 0
                    register_all_display_activity()

        if not speech_frames:
            return None

        combined_raw = b"".join(speech_frames)
        duration = len(combined_raw) / (source.SAMPLE_RATE * source.SAMPLE_WIDTH)
        combined_rms = audioop.rms(combined_raw, source.SAMPLE_WIDTH)
        print(f"[LISTEN] Done: {duration:.2f}s, rms={combined_rms}", flush=True)

        return sr.AudioData(combined_raw, source.SAMPLE_RATE, source.SAMPLE_WIDTH)

    except sr.WaitTimeoutError:
        print("[LISTEN] Timeout", flush=True)
        raise
    finally:
        _streaming_waveform_active = False
        _clear_waveform_values()
        _notify_waveform_stop_sync()


async def listen(display, state_task, stop_event):
    """Listen for voice input and return recognized text.

    Uses streaming audio capture to show real-time waveform visualization
    while recording, then performs speech recognition on the complete audio.
    """

    settings = load_settings()
    stt_engine = settings.get("sttEngine", "google")
    stt_language = settings.get("sttLanguage", "en")
    vad_threshold_db = settings.get("vadThresholdDb", -50.0)

    loop = asyncio.get_running_loop()

    def recognize_audio_litellm():
        """Use LiteLLM for STT with real-time streaming waveform visualization."""
        try:
            import audioop
            import wave

            from litellm import transcription

            provider = get_litellm_provider()
            print(f"[STT] Using LiteLLM provider: {provider}", flush=True)

            if provider == "openai":
                model = "openai/whisper-1"
            elif provider == "groq":
                model = "groq/whisper-large-v3"
            elif provider == "gemini":
                model = "gemini/gemini-1.5-flash"
            else:
                raise ValueError(f"No STT support for provider: {provider}")

            mic_index = _find_microphone_device_index()
            print(f"[STT] Using microphone index: {mic_index}", flush=True)

            import pyaudio

            pa = pyaudio.PyAudio()
            print(f"[STT] PyAudio device count: {pa.get_device_count()}", flush=True)
            for i in range(pa.get_device_count()):
                try:
                    info = pa.get_device_info_by_index(i)
                    if info.get("maxInputChannels", 0) > 0:
                        print(
                            f"[STT]   Input device {i}: {info.get('name')} "
                            f"(inputs={info.get('maxInputChannels')}, rate={info.get('defaultSampleRate')})",
                            flush=True,
                        )
                except Exception:
                    pass
            pa.terminate()

            with sr.Microphone(device_index=mic_index) as source:
                print(
                    f"[STT] Mic details: rate={source.SAMPLE_RATE}Hz, width={source.SAMPLE_WIDTH}, chunk={source.CHUNK}",
                    flush=True,
                )
                if source.stream is None:
                    raise RuntimeError("Microphone not initialized.")
                print(
                    f"[STT] Using fixed energy_threshold={r.energy_threshold:.0f}, starting listen...",
                    flush=True,
                )

                audio = _listen_with_streaming_waveform(
                    source, timeout=3, phrase_time_limit=get_phrase_time_limit()
                )

            if audio is None:
                print("[STT] No audio captured", flush=True)
                return None

            if not audio_has_speech(audio, threshold_db=vad_threshold_db):
                print(
                    f"[STT] Audio rejected by VAD (threshold: {vad_threshold_db} dB)",
                    flush=True,
                )
                return None
            print("[STT] Audio passed VAD check", flush=True)

            register_all_display_activity()

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name

            raw_data = audio.get_raw_data()
            sample_rate = audio.sample_rate
            sample_width = audio.sample_width
            audio_duration_sec = len(raw_data) / (sample_rate * sample_width)
            print(
                f"[STT] Audio: {audio_duration_sec:.2f}s, {sample_rate}Hz, width={sample_width}",
                flush=True,
            )

            target_rate = 16000
            if sample_rate != target_rate:
                raw_data, _ = audioop.ratecv(
                    raw_data, sample_width, 1, sample_rate, target_rate, None
                )
                sample_rate = target_rate
                print(f"[STT] Resampled to {target_rate}Hz", flush=True)

            with wave.open("/tmp/debug_stt.wav", "wb") as debug_wav:
                debug_wav.setnchannels(1)
                debug_wav.setsampwidth(sample_width)
                debug_wav.setframerate(sample_rate)
                debug_wav.writeframes(raw_data)
            print("[STT] Debug audio saved to /tmp/debug_stt.wav", flush=True)

            with wave.open(tmp_path, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(sample_width)
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(raw_data)

            try:
                settings = load_settings()
                keyword = settings.get("keyword", "computer")
                print(
                    f"[STT] Sending audio to {model} for transcription...", flush=True
                )
                with open(tmp_path, "rb") as audio_file:
                    response = transcription(
                        model=model,
                        file=audio_file,
                        language=stt_language,
                        prompt=f"Voice assistant wake word: {keyword}.",
                    )
                    text = response.text if hasattr(response, "text") else str(response)
                    print(f"[STT] Transcription result: {text}", flush=True)

                    # Detect and reject Whisper hallucinations (repeated phrases)
                    if text:
                        text_lower = text.lower().strip()
                        words = text_lower.split()

                        # Check for exact repetition (e.g., "computer set a timer computer set a timer")
                        if len(words) >= 4:
                            half = len(words) // 2
                            first_half = " ".join(words[:half])
                            second_half = " ".join(words[half : half * 2])
                            if first_half == second_half:
                                print(
                                    f"[STT] Detected hallucination (repeated phrase), rejecting",
                                    flush=True,
                                )
                                return None

                        # Check for repeated short phrases that indicate hallucination
                        if text_lower.count(keyword) > 2:
                            print(
                                f"[STT] Detected hallucination (keyword repeated {text_lower.count(keyword)} times), rejecting",
                                flush=True,
                            )
                            return None

                    return text if text else None
            finally:
                os.unlink(tmp_path)

        except sr.WaitTimeoutError:
            print("[STT] Listen timeout - no speech detected", flush=True)
            return None
        except sr.UnknownValueError:
            print("[STT] Could not understand audio", flush=True)
            return None
        except Exception as e:
            print(f"[STT] LiteLLM STT failed: {e}, falling back to Google", flush=True)
            return None

    def recognize_audio_google():
        """Fallback to Google speech recognition with real-time streaming waveform."""
        try:
            mic_index = _find_microphone_device_index()
            print(f"[STT-GOOGLE] Using microphone index: {mic_index}", flush=True)
            with sr.Microphone(device_index=mic_index) as source:
                if source.stream is None:
                    raise RuntimeError("Microphone not initialized.")
                print(
                    f"[STT-GOOGLE] Using fixed energy_threshold={r.energy_threshold:.0f}, starting listen...",
                    flush=True,
                )

                audio = _listen_with_streaming_waveform(
                    source, timeout=3, phrase_time_limit=get_phrase_time_limit()
                )

            if audio is None:
                print("[STT-GOOGLE] No audio captured", flush=True)
                return None

            if not audio_has_speech(audio, threshold_db=vad_threshold_db):
                print(
                    f"[STT-GOOGLE] Audio rejected by VAD (threshold: {vad_threshold_db} dB)",
                    flush=True,
                )
                return None
            print("[STT-GOOGLE] Audio passed VAD check", flush=True)

            register_all_display_activity()

            print("[STT-GOOGLE] Sending to Google for transcription...", flush=True)
            text = r.recognize_google(audio)
            print(f"[STT-GOOGLE] Transcription result: {text}", flush=True)
            return text if text else None

        except sr.WaitTimeoutError:
            print("[STT-GOOGLE] Listen timeout - no speech detected", flush=True)
            return None
        except sr.UnknownValueError:
            print("[STT-GOOGLE] Could not understand audio", flush=True)
            return None

    text = None
    if stt_engine == "litellm" and litellm_stt_available():
        text = await loop.run_in_executor(executor, recognize_audio_litellm)

    if text is None:
        text = await loop.run_in_executor(executor, recognize_audio_google)

    if text:
        state_task.cancel()
    return text


async def _notify_backend_user_listening(start: bool):
    """Start/stop waveform display for user listening."""
    dm = get_display_manager()
    if dm and dm.is_available:
        if start:
            await dm.start_waveform(source="microphone")
        else:
            await dm.stop_waveform()


async def display_state(state, display, stop_event):
    if display is None:
        return

    # Register activity when display state changes (wakes screensaver)
    i2c_display_register_activity()

    if state == "Connecting":
        async with display_lock:
            display.text("No Network", 0, 0, 1)
            cpu_temp = int(
                float(
                    subprocess.check_output(["vcgencmd", "measure_temp"])
                    .decode("utf-8")
                    .split("=")[1]
                    .split("'")[0]
                )
            )
            temp_text_x = 100
            display.text(f"{cpu_temp}", temp_text_x, 0, 1)
            degree_x = 100 + len(f"{cpu_temp}") * 7
            degree_y = 2
            degree_symbol(display, degree_x, degree_y, 2, 1)
            c_x = degree_x + 7
            display.text("C", c_x, 0, 1)
            display.show()

    elif state == "Listening":
        await _notify_backend_user_listening(True)
        try:
            await _display_listening_waveform(display, stop_event)
        finally:
            await _notify_backend_user_listening(False)
    else:
        while not stop_event.is_set():
            for i in range(4):
                if stop_event.is_set():
                    break
                async with display_lock:
                    display.fill_rect(0, 10, 128, 22, 0)
                    display.text(f"{state}" + "." * i, 0, 20, 1)
                    display.show()
                await asyncio.sleep(0.5)


async def _display_listening_waveform(display, stop_event):
    """Display real-time waveform bars on I2C display while listening."""
    global _waveform_values

    try:
        from src.audio_activity import get_audio_activity_detector

        detector = get_audio_activity_detector()
    except Exception:
        detector = None

    bar_count = 16
    bar_width = 6
    bar_spacing = 2
    total_width = bar_count * (bar_width + bar_spacing) - bar_spacing
    start_x = (128 - total_width) // 2
    base_y = 31
    max_bar_height = 18
    min_bar_height = 2

    smoothed = [0.0] * bar_count

    # Restore header before starting waveform display
    async with display_lock:
        display.fill(0)
        draw_i2c_header(display)
        display.show()

    try:
        while not stop_event.is_set():
            with _waveform_send_lock:
                waveform_snapshot = list(_waveform_values)

            current_max = max(waveform_snapshot) if waveform_snapshot else 0.0

            if current_max > 0.02:
                register_all_display_activity()

            async with display_lock:
                display.fill_rect(0, 10, 128, 22, 0)
                display.text("Listening", 34, 10, 1)

                # Use a reasonable scale for normalization
                max_val = max(0.08, current_max)

                for i in range(bar_count):
                    idx1 = i * 2
                    idx2 = i * 2 + 1
                    raw_val = (waveform_snapshot[idx1] + waveform_snapshot[idx2]) / 2.0
                    val = min(1.0, (raw_val / max_val) * 1.2)

                    if detector:
                        smoothed[i] = (
                            detector.smooth_amplitude(val)
                            if i == 0
                            else (
                                smoothed[i] * 0.3 + val * 0.7
                                if val > smoothed[i]
                                else smoothed[i] * 0.7 + val * 0.3
                            )
                        )
                    else:
                        smoothed[i] = (
                            smoothed[i] * 0.3 + val * 0.7
                            if val > smoothed[i]
                            else smoothed[i] * 0.7 + val * 0.3
                        )

                    # Always show bars - minimum height ensures visibility
                    bar_height = max(min_bar_height, int(smoothed[i] * max_bar_height))
                    x = start_x + i * (bar_width + bar_spacing)
                    y = base_y - bar_height

                    display.fill_rect(x, y, bar_width, bar_height, 1)

                display.show()

            await asyncio.sleep(0.033)
    finally:
        pass


async def speak(text, stop_event=asyncio.Event(), word_callback=None):
    """
    Speak text using configured TTS engine.

    Args:
        text: Text to speak
        stop_event: Event to signal when speech completes
        word_callback: Optional async callback called with (word_index, word) as speech progresses
    """
    settings = load_settings()
    speech_engine = settings.get("ttsEngine", "gtts")
    tts_voice = settings.get("ttsVoice", "alloy")
    words = text.split()

    async with speak_lock:
        loop = asyncio.get_running_loop()

        # Queue for word progress updates from TTS thread
        word_queue = asyncio.Queue() if word_callback else None

        def _speak_litellm():
            """Use LiteLLM for TTS with provider auto-detection."""
            try:
                print("[TTS] Starting LiteLLM TTS...", flush=True)
                from litellm import speech

                provider = get_litellm_provider()
                print(f"[TTS] Provider: {provider}", flush=True)

                # Select model based on provider
                if provider == "openai":
                    model = "openai/tts-1"
                    voice = (
                        tts_voice
                        if tts_voice
                        in ["alloy", "echo", "fable", "onyx", "nova", "shimmer"]
                        else "alloy"
                    )
                elif provider == "gemini":
                    model = "gemini/gemini-2.5-flash-preview-tts"
                    voice = (
                        tts_voice if tts_voice.startswith("en-") else "en-US-Standard-A"
                    )
                else:
                    raise ValueError(f"No TTS support for provider: {provider}")

                # Generate speech
                print(
                    f"[TTS] Generating speech with {model}, voice={voice}...",
                    flush=True,
                )
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                    response = speech(model=model, voice=voice, input=text)
                    response.stream_to_file(tmp.name)

                    # Get audio duration for word timing
                    try:
                        from mutagen.mp3 import MP3

                        audio_info = MP3(tmp.name)
                        total_duration = audio_info.info.length
                    except Exception:
                        total_duration = len(words) * 0.4

                    # Play audio - use 'default' device which routes through asound.conf
                    # asound.conf handles HDMI IEC958 conversion automatically
                    audio_device = "default"
                    print(f"[TTS] Playing audio on device: {audio_device}", flush=True)
                    audio_proc = subprocess.Popen(
                        f"ffmpeg -i {tmp.name} -f wav -acodec pcm_s16le -ar 44100 - 2>/dev/null | aplay -D {audio_device}",
                        shell=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )

                    # Track word timing while audio plays
                    start_time = time.time()
                    word_idx = 0
                    word_duration = total_duration / len(words) if words else 0

                    while audio_proc.poll() is None:
                        elapsed = time.time() - start_time

                        if word_queue and words:
                            expected_word = (
                                int(elapsed / word_duration) if word_duration > 0 else 0
                            )
                            while word_idx <= expected_word and word_idx < len(words):
                                asyncio.run_coroutine_threadsafe(
                                    word_queue.put((word_idx, words[word_idx])), loop
                                )
                                word_idx += 1

                        time.sleep(0.025)

                    # Signal remaining words
                    if word_queue and words:
                        while word_idx < len(words):
                            asyncio.run_coroutine_threadsafe(
                                word_queue.put((word_idx, words[word_idx])), loop
                            )
                            word_idx += 1

                    # Check for audio errors
                    _, stderr = audio_proc.communicate()
                    if stderr:
                        stderr_text = stderr.decode("utf-8", errors="ignore").strip()
                        if stderr_text:
                            print(f"[TTS] Audio stderr: {stderr_text}", flush=True)

                    print(
                        f"[TTS] Audio playback finished (exit code: {audio_proc.returncode})",
                        flush=True,
                    )
                    os.unlink(tmp.name)

                print(f"[TTS] LiteLLM TTS completed with {model}", flush=True)
            except Exception as e:
                logger.warning(f"LiteLLM TTS failed: {e}, falling back to pyttsx3")
                _speak_pyttsx3()

        def _speak_pyttsx3():
            """Use pyttsx3 with word callbacks."""
            current_word = [0]  # Mutable container for closure

            def on_word(name, location, length):
                if word_queue and current_word[0] < len(words):
                    asyncio.run_coroutine_threadsafe(
                        word_queue.put((current_word[0], words[current_word[0]])), loop
                    )
                    current_word[0] += 1

            if word_queue:
                engine.connect("started-word", on_word)

            engine.say(text)
            engine.runAndWait()

            # Signal any remaining words
            if word_queue:
                while current_word[0] < len(words):
                    asyncio.run_coroutine_threadsafe(
                        word_queue.put((current_word[0], words[current_word[0]])), loop
                    )
                    current_word[0] += 1

        def _speak_gtts():
            """Use gTTS with estimated word timing."""
            mp3_fp = BytesIO()
            tts = gTTS(text, lang="en")
            tts.write_to_fp(mp3_fp)
            try:
                mixer.quit()  # Ensure clean state
            except Exception:
                pass
            # Initialize mixer with explicit parameters to avoid SDL conflicts
            mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
            mp3_fp.seek(0)
            mixer.music.load(mp3_fp, "mp3")
            mixer.music.play()

            # Simulate word timing (~150 WPM)
            if word_queue and words:
                for i, word in enumerate(words):
                    duration = estimate_word_duration(word)
                    asyncio.run_coroutine_threadsafe(word_queue.put((i, word)), loop)
                    time.sleep(duration)

            while mixer.music.get_busy():
                time.sleep(0.1)
            mixer.quit()

        def _speak():
            if speech_engine == "litellm" and litellm_tts_available():
                _speak_litellm()
            elif speech_engine == "gtts":
                _speak_gtts()
            else:
                _speak_pyttsx3()

        # Start word callback processor
        async def process_word_updates():
            if not word_queue:
                return
            try:
                while True:
                    try:
                        word_idx, word = await asyncio.wait_for(
                            word_queue.get(), timeout=0.1
                        )
                        if word_callback:
                            await word_callback(word_idx, word)
                    except asyncio.TimeoutError:
                        continue
            except asyncio.CancelledError:
                pass

        # Run TTS and word processor concurrently
        if word_callback:
            processor_task = asyncio.create_task(process_word_updates())
            await loop.run_in_executor(executor, _speak)
            processor_task.cancel()
            try:
                await processor_task
            except asyncio.CancelledError:
                pass
        else:
            await loop.run_in_executor(executor, _speak)

        stop_event.set()


async def speak_with_display(text, display, display_manager=None):
    """
    Speak text with synchronized display updates.
    Words appear on screen as they are spoken.

    Args:
        text: Text to speak
        display: I2C display object (can be None)
        display_manager: Optional DisplayManager for framebuffer display
    """
    register_all_display_activity()

    # Get the display manager if not provided
    dm = display_manager or get_display_manager()

    if display is None and dm is None:
        stop_event = asyncio.Event()
        await speak(text, stop_event)
        return

    words = text.split()
    current_display_text = []

    async def on_word(word_idx, word):
        """Callback invoked as each word is spoken."""
        nonlocal current_display_text
        current_display_text.append(word)

        # Update I2C display
        if display is not None:
            display_text = " ".join(current_display_text)

            async with display_lock:
                # Clear text area (keep header)
                display.fill_rect(0, 10, 128, 22, 0)

                # Word-wrap and show recent text that fits on screen
                lines = textwrap.fill(display_text, 21).split("\n")

                # Show last 2 lines (most recent)
                visible_lines = lines[-2:] if len(lines) > 2 else lines

                for i, line in enumerate(visible_lines):
                    try:
                        display.text(line, 0, 10 + i * 10, 1)
                    except struct.error:
                        pass
                display.show()

        # Update full display (if available and not showing tool animation)
        if dm and dm.is_available and not dm._has_tool_animation:
            try:
                await dm.stream_response_word(word)
            except Exception:
                pass

    # Initialize I2C display header
    if display is not None:
        async with display_lock:
            display.fill(0)
            draw_i2c_header(display)
            display.show()

    stop_event = asyncio.Event()
    await speak(text, stop_event, word_callback=on_word)

    # Clear streaming text on full display after TTS completes
    if dm and dm.is_available:
        try:
            await dm.clear_streaming()
        except Exception:
            pass


async def handle_error(message, state_task, display):
    if state_task:
        state_task.cancel()
    stop_event = asyncio.Event()
    await speak_with_display(message, display)
    logger.critical(f"An error occurred: {message}\n{traceback.format_exc()}")
