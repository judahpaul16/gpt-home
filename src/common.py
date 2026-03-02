import warnings

# Suppress Pydantic V2 config warnings before any imports
warnings.filterwarnings("ignore", message="Valid config keys have changed in V2")
# Suppress Pydantic serialization warnings from LiteLLM
warnings.filterwarnings("ignore", message="Pydantic serializer warnings")
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")
# Suppress LangChain deprecation warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module="langchain")
warnings.filterwarnings("ignore", category=UserWarning, module="pkg_resources")

import asyncio
import audioop
import json
import logging
import math
import os
import queue
import re
import string
import struct
import subprocess
import sys
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
from typing import Optional

import aiohttp
import caldav
import litellm
import pyttsx3
import requests
import speech_recognition as sr
from dotenv import load_dotenv
from phue import Bridge

from src.audio_capture import MIC_PRIORITIES


_softvol_configured = False


def _configure_alsa_for_pyaudio():
    """Configure ALSA before PyAudio/speech_recognition is imported.

    PortAudio can crash with assertion failures during Pa_Initialize() if
    no valid default input device is configured. This ensures /etc/asound.conf
    has an asymmetric config with a valid capture device.
    """
    global _softvol_configured
    try:
        asound_path = "/etc/asound.conf"

        if os.path.exists(asound_path):
            with open(asound_path, "r") as f:
                content = f.read()
            if "capture.pcm" in content:
                configured_cards = set(re.findall(r'hw:(\d+)', content))
                if configured_cards:
                    available_cards = set()
                    for cmd in [["aplay", "-l"], ["arecord", "-l"]]:
                        try:
                            r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                            if r.returncode == 0:
                                for m in re.finditer(r'card\s+(\d+):', r.stdout):
                                    available_cards.add(m.group(1))
                        except Exception:
                            pass
                    if configured_cards.issubset(available_cards):
                        return
                    print(
                        f"[AUDIO] Configured cards {configured_cards} not all present "
                        f"(available: {available_cards}), reconfiguring",
                        flush=True,
                    )
                else:
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

        mic_priorities = MIC_PRIORITIES
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

        playback_card = "0"
        is_bcm2835 = False
        try:
            aplay_result = subprocess.run(
                ["aplay", "-l"], capture_output=True, text=True, timeout=5
            )
            if aplay_result.returncode == 0:
                best_play_card = None
                best_play_priority = -1
                for line in aplay_result.stdout.lower().split("\n"):
                    if "card" not in line:
                        continue
                    play_card_match = re.search(r"card\s+(\d+):", line)
                    if play_card_match:
                        card_num = play_card_match.group(1)
                        for keyword, priority in mic_priorities:
                            if keyword in line and priority > best_play_priority:
                                best_play_card = card_num
                                best_play_priority = priority
                                break
                if best_play_card:
                    playback_card = best_play_card
                for line in aplay_result.stdout.lower().split("\n"):
                    if f"card {playback_card}:" in line and "bcm2835" in line:
                        is_bcm2835 = True
                        break
        except Exception:
            pass

        has_playback_mixer = False
        has_capture_mixer = False
        volume_controls = ["PCM", "Master", "Speaker", "Headphone", "HDMI"]
        capture_controls = ["Capture", "Mic", "Input", "Digital"]
        for control in volume_controls:
            try:
                result = subprocess.run(
                    ["amixer", "-c", playback_card, "sget", control],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0 and re.search(r"\[\d+%\]", result.stdout):
                    has_playback_mixer = True
                    break
            except Exception:
                pass
        for control in capture_controls:
            try:
                result = subprocess.run(
                    ["amixer", "-c", best_card, "sget", control],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0 and re.search(r"\[\d+%\]", result.stdout):
                    has_capture_mixer = True
                    break
            except Exception:
                pass

        softvol_playback = ""
        softvol_capture = ""
        playback_pcm = '"dmixer"'
        capture_pcm = f'"hw:{best_card},0"'

        if not has_playback_mixer:
            softvol_playback = f"""
pcm.softvol_out {{
    type softvol
    slave.pcm "dmixer"
    control {{
        name "SoftMaster"
        card {playback_card}
    }}
    min_dB -51.0
    max_dB 0.0
}}
"""
            playback_pcm = '"softvol_out"'

        if not has_capture_mixer:
            softvol_capture = f"""
pcm.softvol_cap {{
    type softvol
    slave.pcm "hw:{best_card},0"
    control {{
        name "Capture"
        card {best_card}
    }}
    min_dB -20.0
    max_dB 40.0
}}
"""
            capture_pcm = '"softvol_cap"'
            _softvol_configured = True

        if is_bcm2835:
            asound_config = f"""{softvol_capture}
pcm.!default {{
    type asym
    playback.pcm {{
        type plug
        slave.pcm "hw:{playback_card},0"
    }}
    capture.pcm {{
        type plug
        slave.pcm {capture_pcm}
    }}
}}

ctl.!default {{
    type hw
    card {playback_card}
}}
"""
        else:
            asound_config = f"""pcm.dmixer {{
    type dmix
    ipc_key 1024
    ipc_perm 0666
    slave {{
        pcm "hw:{playback_card},0"
        rate 48000
        format S16_LE
        channels 2
        period_size 1024
        buffer_size 4096
    }}
}}
{softvol_playback}{softvol_capture}
pcm.!default {{
    type asym
    playback.pcm {{
        type plug
        slave.pcm {playback_pcm}
    }}
    capture.pcm {{
        type plug
        slave.pcm {capture_pcm}
    }}
}}

ctl.!default {{
    type hw
    card {playback_card}
}}
"""
        with open(asound_path, "w") as f:
            f.write(asound_config)
        shared_path = "/etc/alsa-shared/asound.conf"
        if os.path.isdir(os.path.dirname(shared_path)):
            with open(shared_path, "w") as f:
                f.write(asound_config)
        softvol_info = []
        if not has_playback_mixer:
            softvol_info.append("playback=softvol_out")
        if not has_capture_mixer:
            softvol_info.append("capture=softvol_cap")
        softvol_str = f" ({', '.join(softvol_info)})" if softvol_info else ""
        print(
            f"[AUDIO] Configured asound.conf: playback=card {playback_card}, capture=card {best_card}{softvol_str}",
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


_log_fmt = logging.Formatter("%(levelname)s:%(name)s:%(message)s")

handler = FlushingFileHandler(log_file_path)
handler.setLevel(logging.DEBUG)
handler.setFormatter(_log_fmt)
logging.root.addHandler(handler)

_stdout_handler = logging.StreamHandler(sys.stdout)
_stdout_handler.setLevel(logging.DEBUG)
_stdout_handler.setFormatter(_log_fmt)
logging.root.addHandler(_stdout_handler)

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
logging.getLogger("asyncio").setLevel(logging.ERROR)
logging.getLogger("PIL").setLevel(logging.WARNING)
logging.getLogger("matplotlib").setLevel(logging.WARNING)
logging.getLogger("uvicorn").setLevel(logging.INFO)
logging.getLogger("uvicorn.access").setLevel(logging.INFO)
logging.getLogger("spotipy").setLevel(logging.WARNING)

executor = ThreadPoolExecutor()

sys.modules["common"] = sys.modules[__name__]
if "src.common" in sys.modules:
    sys.modules["src.common"] = sys.modules[__name__]


def get_display_manager():
    """Get the display manager singleton instance.

    Returns the DisplayManager singleton if available and initialized,
    None otherwise. This is safe to call before initialization.
    """
    try:
        from src.display import DisplayManager

        instance = DisplayManager.get_instance()
        if instance._display_initialized:
            return instance
        return None
    except Exception:
        return None


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
    logger.debug("Tool animation: %s, context: %s", tool_name, context)
    dm = get_display_manager()
    if dm and dm.is_available:
        await dm.show_tool_animation(tool_name, context or {}, "")

    if tool_name == "weather":
        from src.display.auxiliary import show_weather_all
        location = (context or {}).get("requested_location")
        await show_weather_all(location)


def show_tool_animation_sync(tool_name: str, context: dict = None):
    """Synchronous wrapper for show_tool_animation.

    Use this from synchronous tool code.
    """
    import asyncio

    logger.debug("Tool animation (sync): %s, context: %s", tool_name, context)
    dm = get_display_manager()
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return

    async def _run():
        if dm and dm.is_available:
            await dm.show_tool_animation(tool_name, context or {}, "")
        if tool_name == "weather":
            from src.display.auxiliary import show_weather_all
            location = (context or {}).get("requested_location")
            await show_weather_all(location)

    try:
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(_run(), loop)
        else:
            loop.run_until_complete(_run())
    except Exception:
        pass


# Initialize the speech recognition engine
r = sr.Recognizer()

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

                for keyword, priority in MIC_PRIORITIES:
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

        # First pass: look for exact hw:N match in device name
        for i in range(device_count):
            try:
                info = p.get_device_info_by_index(i)
                name = info.get("name", "")
                max_input = info.get("maxInputChannels", 0)
                sample_rate = info.get("defaultSampleRate", 0)

                if max_input > 0:
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

                    for keyword, priority in MIC_PRIORITIES:
                        if keyword in name and priority > best_priority:
                            best_idx = i
                            best_priority = priority
                            break
            except Exception:
                continue

        p.terminate()
        return best_idx

    except Exception as e:
        logger.error("Error enumerating PyAudio devices: %s", e)
        return None


def _find_microphone_device_index():
    """Find the best available microphone device index for speech recognition.

    Always returns None so sr.Microphone uses the ALSA default device,
    which _configure_alsa_for_pyaudio() has set up with proper capture routing
    (through softvol_cap when the card lacks hardware capture mixer controls).
    """
    global _cached_alsa_card, _mic_index_checked

    if _mic_index_checked:
        return None

    _mic_index_checked = True

    _cached_alsa_card = _find_alsa_microphone_card()

    if _cached_alsa_card is None:
        logger.warning("No ALSA microphone card found")
    else:
        logger.debug("Found microphone on ALSA card %d, using ALSA default device", _cached_alsa_card)

    return None


# Configure speech recognizer with fixed energy threshold
r.energy_threshold = 50  # Low fixed threshold - let VAD handle speech detection
r.dynamic_energy_threshold = (
    False  # Disabled - was adjusting upward and rejecting speech
)
r.phrase_threshold = 0.3  # Minimum seconds of speech to consider a phrase


def _load_speech_timing_settings():
    try:
        settings = load_settings()
        r.pause_threshold = settings.get("pauseThreshold", 1.2)
        r.non_speaking_duration = settings.get("nonSpeakingDuration", 0.8)
    except Exception:
        r.pause_threshold = 1.2
        r.non_speaking_duration = 0.8


_load_speech_timing_settings()


def get_phrase_time_limit():
    try:
        return load_settings().get("phraseTimeLimit", 30)
    except Exception:
        return 30


def reload_speech_timing_settings():
    """Reload speech timing settings from settings.json. Call after settings change."""
    _load_speech_timing_settings()


class MicrophoneSource(sr.AudioSource):
    """Reads from the active AudioCapture stream via a queue.

    Unlike sr.Microphone, this never creates/destroys a PyAudio instance,
    so the WM8960 speaker amp doesn't pop from Pa_Terminate/Pa_Initialize.
    """

    def __init__(self):
        self.SAMPLE_RATE = 44100
        self.SAMPLE_WIDTH = 2
        self.CHUNK = 1024
        self.stream = None

    def __enter__(self):
        from src.audio_capture import get_mic_capture_info, start_mic_listen_feed

        self.SAMPLE_RATE, self.CHUNK = get_mic_capture_info()
        self._queue = queue.Queue(maxsize=200)
        start_mic_listen_feed(self._queue)
        self.stream = self._QueueStream(self._queue)
        return self

    def __exit__(self, *args):
        from src.audio_capture import stop_mic_listen_feed

        stop_mic_listen_feed()
        self.stream = None

    class _QueueStream:
        def __init__(self, q):
            self._queue = q

        def read(self, size):
            return self._queue.get(timeout=10)


def calibrate_ambient_noise(duration: float = 1.0):
    """Calibrate the recognizer for ambient noise levels.

    Call this periodically or when the environment changes to improve
    speech detection accuracy and reduce false positives.
    """
    try:
        with MicrophoneSource() as source:
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
    min_peak: float = 0.05,
) -> bool:
    """Check if audio contains speech. Rejects short/quiet audio to prevent Whisper hallucinations."""
    try:
        raw_data = audio_data.get_raw_data()
        duration = len(raw_data) / (audio_data.sample_rate * audio_data.sample_width)

        if duration < min_duration:
            logger.debug(
                "Audio too short: %.2fs < %.1fs, rejecting", duration, min_duration
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
        if peak_ratio < min_peak:
            logger.debug("Peak too low: %.3f < %.3f, rejecting", peak_ratio, min_peak)
            has_speech = False

        logger.debug(
            "VAD: dB=%.1f, threshold=%s, duration=%.2fs, peak=%.3f (min=%.3f), has_speech=%s",
            metrics.db_level,
            threshold_db,
            duration,
            peak_ratio,
            min_peak,
            has_speech,
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

def register_all_display_activity():
    from src.display.auxiliary import register_all_auxiliary_activity
    register_all_auxiliary_activity()
    dm = get_display_manager()
    if dm and dm.is_available:
        dm.register_activity()


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
    global _mic_index_checked, _cached_alsa_card
    _mic_index_checked = False
    _cached_alsa_card = None


def network_connected():
    try:
        response = requests.get("http://www.google.com", timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False


async def load_integration_statuses() -> dict[str, bool]:
    from src.backend import get_db_pool

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


async def initialize_system():
    from src.display.auxiliary import (
        display_state_all,
        init_auxiliary_displays,
        restore_all_headers,
        start_all_screensaver_monitors,
    )

    await init_auxiliary_displays()

    stop_event_init = asyncio.Event()
    state_tasks = await display_state_all("Connecting", stop_event_init)

    while not network_connected():
        await asyncio.sleep(1)
        logger.info("Network not connected. Retrying...")

    stop_event_init.set()
    for task in state_tasks:
        task.cancel()

    await restore_all_headers()
    start_all_screensaver_monitors()


_settings_cache: Optional[dict] = None


def load_settings() -> dict:
    if _settings_cache is not None:
        return _settings_cache.copy()
    settings_path = SOURCE_DIR / "settings.json"
    with open(settings_path, "r") as f:
        return json.load(f)


def save_settings(settings: dict):
    global _settings_cache
    _settings_cache = settings.copy()
    settings_path = SOURCE_DIR / "settings.json"
    try:
        with open(settings_path, "w") as f:
            json.dump(settings, f, indent=2)
    except Exception:
        pass


def set_settings_cache(settings: dict):
    global _settings_cache
    _settings_cache = settings.copy()


def _update_waveform_from_chunk(audio_chunk: sr.AudioData):
    try:
        from src.waveform import get_waveform_mediator

        mediator = get_waveform_mediator()
        mediator.update_from_audio_chunk(audio_chunk)
    except Exception as e:
        logger.error("Waveform chunk update error: %s", e)


def _notify_waveform_start_sync():
    try:
        from src.waveform import get_waveform_mediator

        mediator = get_waveform_mediator()
        # Mediator stays in LISTENING_MIC from startup; just clear values for fresh listen
        mediator.clear()
    except Exception as e:
        logger.error("Waveform mediator clear failed: %s", e)

    dm = get_display_manager()
    if dm and dm.is_available:
        dm.start_waveform_sync()


def _notify_waveform_stop_sync():
    try:
        from src.waveform import get_waveform_mediator

        mediator = get_waveform_mediator()
        # Don't transition to INACTIVE — just clear values, mediator stays LISTENING_MIC
        mediator.clear()
    except Exception:
        pass

    dm = get_display_manager()
    if dm and dm.is_available:
        dm.stop_waveform_sync()


def _clear_waveform_values():
    """Reset waveform values to zero."""
    try:
        from src.waveform import get_waveform_mediator

        mediator = get_waveform_mediator()
        mediator.clear()
    except Exception:
        pass


def _listen_with_streaming_waveform(source, timeout=3, phrase_time_limit=15):
    """Listen for audio and update waveform display."""
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
                    logger.debug(
                        "Speech at chunk %d, rms=%d, thresh=%.0f, baseline=%.0f",
                        chunk_count,
                        rms,
                        speech_threshold,
                        baseline_rms,
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
                        logger.debug(
                            "Silence at chunk %d, speech_chunks=%d",
                            chunk_count,
                            speech_chunks,
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
        logger.debug("Listen done: %.2fs, rms=%d", duration, combined_rms)

        return sr.AudioData(combined_raw, source.SAMPLE_RATE, source.SAMPLE_WIDTH)

    except sr.WaitTimeoutError:
        raise
    finally:
        _clear_waveform_values()
        _notify_waveform_stop_sync()


_original_spotify_volume: Optional[int] = None
_MUSIC_PLAYING_PEAK_THRESHOLD = 0.55


def _is_spotify_playing() -> bool:
    try:
        from src.backend import _spotify_playback_cache
        return bool(_spotify_playback_cache and _spotify_playback_cache.get("is_playing"))
    except Exception:
        return False


async def duck_volume() -> None:
    """Lower Spotify volume temporarily when wake word is detected."""
    global _original_spotify_volume
    try:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    "http://localhost:8000/api/spotify/playback",
                    timeout=aiohttp.ClientTimeout(total=2),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        is_playing = data.get("is_playing")
                        current_spotify_vol = data.get("volume")
                        logger.debug(
                            "Spotify check: is_playing=%s, volume=%s",
                            is_playing,
                            current_spotify_vol,
                        )
                        if is_playing:
                            if (
                                current_spotify_vol is not None
                                and current_spotify_vol > 20
                            ):
                                _original_spotify_volume = current_spotify_vol
                                ducked_spotify_vol = max(
                                    10, int(current_spotify_vol * 0.2)
                                )
                                async with session.post(
                                    "http://localhost:8000/spotify-control",
                                    json={"command": f"volume {ducked_spotify_vol}"},
                                    timeout=aiohttp.ClientTimeout(total=3),
                                ) as _:
                                    logger.debug(
                                        "Spotify volume ducked from %d%% to %d%%",
                                        current_spotify_vol,
                                        ducked_spotify_vol,
                                    )
            except Exception as e:
                logger.error("Failed to duck Spotify volume: %s", e)

    except Exception as e:
        logger.error("Failed to duck volume: %s", e)


async def restore_volume() -> None:
    """Restore Spotify volume after interaction completes."""
    global _original_spotify_volume
    try:
        import aiohttp

        if _original_spotify_volume is not None:
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.post(
                        "http://localhost:8000/spotify-control",
                        json={"command": f"volume {_original_spotify_volume}"},
                        timeout=aiohttp.ClientTimeout(total=3),
                    ) as _:
                        logger.debug(
                            "Spotify volume restored to %d%%", _original_spotify_volume
                        )
                    _original_spotify_volume = None
                except Exception as e:
                    logger.error("Failed to restore Spotify volume: %s", e)

    except Exception as e:
        logger.error("Failed to restore volume: %s", e)


async def listen(state_task, stop_event):
    """Listen for voice input and return recognized text.

    Uses streaming audio capture to show real-time waveform visualization
    while recording, then performs speech recognition on the complete audio.
    """

    settings = load_settings()
    stt_engine = settings.get("sttEngine", "google")
    stt_language = settings.get("sttLanguage", "en")
    vad_threshold_db = settings.get("vadThresholdDb", -50.0)

    loop = asyncio.get_running_loop()

    async def recognize_audio_litellm():
        """Use LiteLLM for STT with real-time streaming waveform visualization."""
        try:
            import audioop
            import wave

            from litellm import transcription

            provider = get_litellm_provider()

            if provider == "openai":
                model = "openai/whisper-1"
            elif provider == "groq":
                model = "groq/whisper-large-v3"
            elif provider == "gemini":
                model = "gemini/gemini-1.5-flash"
            else:
                raise ValueError(f"No STT support for provider: {provider}")

            def _do_listen():
                with MicrophoneSource() as source:
                    return _listen_with_streaming_waveform(
                        source, timeout=3, phrase_time_limit=get_phrase_time_limit()
                    )

            audio = await loop.run_in_executor(None, _do_listen)

            if audio is None:
                return None

            peak_min = _MUSIC_PLAYING_PEAK_THRESHOLD if _is_spotify_playing() else 0.05
            if not audio_has_speech(audio, threshold_db=vad_threshold_db, min_peak=peak_min):
                logger.debug(
                    "Audio rejected by VAD (threshold: %s dB, min_peak: %.3f)", vad_threshold_db, peak_min
                )
                return None

            register_all_display_activity()

            def _do_transcribe():
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    tmp_path = tmp.name

                raw_data = audio.get_raw_data()
                sample_rate_local = audio.sample_rate
                sample_width = audio.sample_width

                target_rate = 16000
                if sample_rate_local != target_rate:
                    raw_data, _ = audioop.ratecv(
                        raw_data, sample_width, 1, sample_rate_local, target_rate, None
                    )
                    sample_rate_local = target_rate

                with wave.open("/tmp/debug_stt.wav", "wb") as debug_wav:
                    debug_wav.setnchannels(1)
                    debug_wav.setsampwidth(sample_width)
                    debug_wav.setframerate(sample_rate_local)
                    debug_wav.writeframes(raw_data)

                with wave.open(tmp_path, "wb") as wav_file:
                    wav_file.setnchannels(1)
                    wav_file.setsampwidth(sample_width)
                    wav_file.setframerate(sample_rate_local)
                    wav_file.writeframes(raw_data)

                try:
                    stg = load_settings()
                    keyword = stg.get("keyword", "computer")
                    logger.debug(
                        "Sending audio to %s for transcription...",
                        model,
                    )
                    with open(tmp_path, "rb") as audio_file:
                        response = transcription(
                            model=model,
                            file=audio_file,
                            language=stt_language,
                            prompt=f"Voice assistant wake word: {keyword}.",
                        )
                        text = (
                            response.text
                            if hasattr(response, "text")
                            else str(response)
                        )
                        logger.debug("Transcription result: %s", text)

                        return text if text else None
                finally:
                    os.unlink(tmp_path)

            return await loop.run_in_executor(None, _do_transcribe)

        except sr.WaitTimeoutError:
            return None
        except sr.UnknownValueError:
            return None
        except Exception as e:
            logger.error("LiteLLM STT failed: %s, falling back to Google", e)
            return None

    async def recognize_audio_google():
        """Fallback to Google speech recognition with real-time streaming waveform."""
        try:
            def _do_listen():
                with MicrophoneSource() as source:
                    return _listen_with_streaming_waveform(
                        source, timeout=3, phrase_time_limit=get_phrase_time_limit()
                    )

            audio = await loop.run_in_executor(None, _do_listen)

            if audio is None:
                return None

            peak_min = _MUSIC_PLAYING_PEAK_THRESHOLD if _is_spotify_playing() else 0.05
            if not audio_has_speech(audio, threshold_db=vad_threshold_db, min_peak=peak_min):
                logger.debug(
                    "Google STT: audio rejected by VAD (threshold: %s dB, min_peak: %.3f)",
                    vad_threshold_db, peak_min,
                )
                return None

            register_all_display_activity()

            def _do_recognize():
                text = r.recognize_google(audio)
                logger.debug("Google transcription result: %s", text)
                return text if text else None

            return await loop.run_in_executor(None, _do_recognize)

        except sr.WaitTimeoutError:
            return None
        except sr.UnknownValueError:
            return None

    text = None
    if stt_engine == "litellm" and litellm_stt_available():
        text = await recognize_audio_litellm()

    if text is None:
        text = await recognize_audio_google()

    if text:
        state_task.cancel()

    await restore_volume()
    return text


async def _notify_backend_user_listening(start: bool):
    """Start/stop waveform display for user listening."""
    dm = get_display_manager()
    if dm and dm.is_available:
        if start:
            await dm.start_waveform(source="microphone")
        else:
            await dm.stop_waveform()


async def display_state(state, stop_event):
    register_all_display_activity()

    dm = get_display_manager()
    if dm and dm.is_available:
        if dm._screensaver_active:
            await dm.register_activity_async()
        else:
            dm.register_activity()

    from src.display.auxiliary import display_state_all

    if state == "Listening":
        await _notify_backend_user_listening(True)
        try:
            tasks = await display_state_all(state, stop_event)
            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            await _notify_backend_user_listening(False)
    else:
        tasks = await display_state_all(state, stop_event)
        await asyncio.gather(*tasks, return_exceptions=True)


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
                from litellm import speech

                provider = get_litellm_provider()
                logger.debug("TTS starting with provider: %s", provider)

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
                logger.debug("Generating speech with %s, voice=%s", model, voice)
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

                    audio_device = os.environ.get("AUDIODEV", "default")
                    logger.debug("TTS playing audio on device: %s", audio_device)
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
                    timeout = total_duration + 15

                    while audio_proc.poll() is None:
                        elapsed = time.time() - start_time

                        if elapsed > timeout:
                            logger.warning("TTS aplay timed out after %.1fs (expected %.1fs), killing", elapsed, total_duration)
                            audio_proc.kill()
                            audio_proc.wait()
                            break

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

                    _, stderr = audio_proc.communicate(timeout=5)
                    if stderr:
                        stderr_text = stderr.decode("utf-8", errors="ignore").strip()
                        if stderr_text and audio_proc.returncode != 0:
                            logger.warning("TTS audio stderr: %s", stderr_text)
                    os.unlink(tmp.name)

                logger.debug("TTS completed with %s", model)
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


async def speak_with_display(text, display_manager=None):
    register_all_display_activity()

    dm = display_manager or get_display_manager()

    from src.display.auxiliary import get_all_auxiliary, restore_all_headers, show_word_all

    aux_displays = get_all_auxiliary()
    has_any_display = bool(aux_displays) or (dm and dm.is_available)

    if not has_any_display:
        stop_event = asyncio.Event()
        await speak(text, stop_event)
        return

    aux_word_lists: dict = {}

    async def on_word(word_idx, word):
        await show_word_all(word, aux_word_lists)

        if dm and dm.is_available and not dm._has_tool_animation:
            try:
                await dm.stream_response_word(word)
            except Exception:
                pass

    await restore_all_headers()

    stop_event = asyncio.Event()
    await speak(text, stop_event, word_callback=on_word)

    if dm and dm.is_available:
        try:
            await dm.clear_streaming()
        except Exception:
            pass


async def handle_error(message, state_task):
    if state_task:
        state_task.cancel()
    stop_event = asyncio.Event()
    await speak_with_display(message)
    logger.critical(f"An error occurred: {message}\n{traceback.format_exc()}")
