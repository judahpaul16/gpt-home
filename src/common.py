import warnings
# Suppress Pydantic V2 config warnings before any imports
warnings.filterwarnings("ignore", message="Valid config keys have changed in V2")
# Suppress Pydantic serialization warnings from LiteLLM
warnings.filterwarnings("ignore", message="Pydantic serializer warnings")
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")
# Suppress LangChain deprecation warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module="langchain")

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import speech_recognition as sr
from dotenv import load_dotenv
from threading import Timer
from pathlib import Path
from phue import Bridge
import subprocess
import traceback
import textwrap
import requests
import litellm
import logging
import asyncio
import pyttsx3
import aiohttp
import caldav
import struct
import string
import busio
import json
import time
import os
import re
import tempfile
from ctypes import CFUNCTYPE, c_char_p, c_int, cdll

# Suppress ALSA error messages (from StackOverflow)
# These are harmless debug messages that clutter logs
def _py_error_handler(filename, line, function, err, fmt):
    pass

_ERROR_HANDLER_FUNC = CFUNCTYPE(None, c_char_p, c_int, c_char_p, c_int, c_char_p)
_c_error_handler = _ERROR_HANDLER_FUNC(_py_error_handler)

try:
    _asound = cdll.LoadLibrary('libasound.so.2')
    _asound.snd_lib_error_set_handler(_c_error_handler)
except OSError:
    pass  # libasound not available

# Suppress JACK error messages
_JACK_ERROR_HANDLER_FUNC = CFUNCTYPE(None, c_char_p)
def _py_jack_error_handler(msg):
    pass
_jack_error_handler = _JACK_ERROR_HANDLER_FUNC(_py_jack_error_handler)

try:
    _jack = cdll.LoadLibrary('libjack.so.0')
    _jack.jack_set_error_function(_jack_error_handler)
    _jack.jack_set_info_function(_jack_error_handler)
except OSError:
    pass  # libjack not available

# Suppress pygame welcome message
import os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

# TTS
from gtts import gTTS
from io import BytesIO
from pygame import mixer
import time

SOURCE_DIR = Path(__file__).parent
ROOT_DIR = SOURCE_DIR.parent
log_file_path = SOURCE_DIR / "events.log"

# LiteLLM TTS/STT compatible providers (by API key prefix/pattern)
LITELLM_TTS_PROVIDERS = {
    "sk-": "openai",      # OpenAI
    "sk-ant-": None,      # Anthropic - no TTS
    "AIza": "gemini",     # Google/Gemini
    "gsk_": "groq",       # Groq - STT only
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
load_dotenv(dotenv_path=ROOT_DIR / '.env')
load_dotenv(dotenv_path=SOURCE_DIR / 'frontend' / '.env', override=False)

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
handler.setLevel(logging.INFO)
handler.setFormatter(logging.Formatter('%(levelname)s:%(name)s:%(message)s'))
logging.root.addHandler(handler)
logging.root.setLevel(logging.INFO)

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
    logger.debug("Board not detected. Skipping... \n    Reason: {e}\n{traceback.format_exc()}")
try:
    import adafruit_ssd1306
except Exception as e:
    logger.debug(f"Failed to import adafruit_ssd1306. Skipping...\n    Reason: {e}\n{traceback.format_exc()}")

executor = ThreadPoolExecutor()

# Initialize the speech recognition engine
r = sr.Recognizer()

# Initialize the LiteLLM API key from environment
# API keys are stored in .env and loaded via python-dotenv
litellm.api_key = os.getenv("LITELLM_API_KEY", "")

# Initialize the text-to-speech engine
engine = pyttsx3.init()
# Set properties
engine.setProperty('rate', 145)
engine.setProperty('volume', 1.0)
# Direct audio to specific hardware
engine.setProperty('alsa_device', 'hw:Headphones,0')
speak_lock = asyncio.Lock()
display_lock = asyncio.Lock()

def network_connected():
    try:
        response = requests.get("http://www.google.com", timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False

# Manually draw a degree symbol °
def degree_symbol(display, x, y, radius, color):
    for i in range(x-radius, x+radius+1):
        for j in range(y-radius, y+radius+1):
            if (i-x)**2 + (j-y)**2 <= radius**2:
                display.pixel(i, j, color)
                # clear center of circle
                if (i-x)**2 + (j-y)**2 <= (radius-1)**2:
                    display.pixel(i, j, 0)

async def calculate_delay(message):
    """Legacy delay calculation - kept for backward compatibility."""
    base_delay = 0.02
    extra_delay = 0.0
    
    # Patterns to look for
    patterns = [r": ", r"\. ", r"\? ", r"! ", r"\.{2,}", r", ", r"\n"]
    
    for pattern in patterns:
        extra_delay += (len(re.findall(pattern, message)) * 0.001)  # Add 0.001 seconds for each match

    return base_delay + extra_delay


def estimate_word_duration(word, base_wpm=150):
    """
    Estimate how long a word takes to speak based on syllables and punctuation.
    Returns duration in seconds.
    """
    # Count syllables (rough estimate based on vowel groups)
    vowels = 'aeiouyAEIOUY'
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
    if word.endswith(('.', '!', '?')):
        base_duration += 0.3  # Sentence-ending pause
    elif word.endswith((',', ';', ':')):
        base_duration += 0.15  # Clause pause
    
    return base_duration

def initLCD():
    try:
        # Create the I2C interface.
        i2c = busio.I2C(SCL, SDA)
        # Create the SSD1306 OLED class.
        # The first two parameters are the pixel width and pixel height. Change these
        # to the right size for your display
        display = adafruit_ssd1306.SSD1306_I2C(128, 32, i2c)
        # Alternatively, you can change the I2C address of the device with an addr parameter:
        # display = adafruit_ssd1306.SSD1306_I2C(128, 32, i2c, addr=0x31)
        # Set the display rotation to 180 degrees.
        display.rotation = 2
        # Clear the display. Always call show after changing pixels to make the display
        # update visible
        display.fill(0)
        # Display IP address
        ip_address = subprocess.check_output(["hostname", "-I"]).decode("utf-8").split(" ")[0]
        display.text(f"{ip_address}", 0, 0, 1)
        # Display CPU temperature in Celsius (e.g., 39°)
        cpu_temp = int(float(subprocess.check_output(["vcgencmd", "measure_temp"]).decode("utf-8").split("=")[1].split("'")[0]))
        temp_text_x = 100
        display.text(f"{cpu_temp}", temp_text_x, 0, 1)
        # degree symbol
        degree_x = 100 + len(f"{cpu_temp}") * 7 # Assuming each character is 7 pixels wide
        degree_y = 2
        degree_symbol(display, degree_x, degree_y, 2, 1)
        c_x = degree_x + 7 # Assuming each character is 7 pixels wide
        display.text("C", c_x, 0, 1)
        # Show the updated display with the text.
        display.show()
        return display
    except Exception as e:
        logger.debug(f"Failed to initialize display, skipping...\n Reason: {e}\n{traceback.format_exc()}")
        return None

async def initialize_system():
    display = initLCD()
    stop_event_init = asyncio.Event()
    state_task = asyncio.create_task(display_state("Connecting", display, stop_event_init))
    while not network_connected():
        await asyncio.sleep(1)
        message = "Network not connected. Retrying..."
        logger.info(message)
    stop_event_init.set()  # Signal to stop the 'Connecting' display
    state_task.cancel()  # Cancel the display task
    display = initLCD()  # Reinitialize the display
    return display

def load_settings():
    settings_path = SOURCE_DIR / "settings.json"
    with open(settings_path, "r") as f:
        settings = json.load(f)
        return settings

async def updateLCD(text, display, stop_event=None, delay=0.02, word_sync_event=None):
    """
    Update LCD display with text.
    
    Args:
        text: Text to display
        display: OLED display object
        stop_event: Event to signal when to stop
        delay: Delay between characters (legacy, used when word_sync_event is None)
        word_sync_event: asyncio.Event that gets set each time a word should be displayed
    """
    if display is None:
        return  # Skip updating the display if it's not initialized
    
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
            ip_address = subprocess.check_output(["hostname", "-I"]).decode("utf-8").split(" ")[0]
            display.text(f"{ip_address}", 0, 0, 1)
            try:
                cpu_temp = int(float(subprocess.check_output(["vcgencmd", "measure_temp"]).decode("utf-8").split("=")[1].split("'")[0]))
                temp_text_x = 100
                display.text(f"{cpu_temp}", temp_text_x, 0, 1)
                degree_x = 100 + len(f"{cpu_temp}") * 7
                degree_y = 2
                degree_symbol(display, degree_x, degree_y, 2, 1)
                c_x = degree_x + 7
                display.text("C", c_x, 0, 1)
            except:
                pass  # Skip temp if vcgencmd not available
            display.show()

        init_display_header()
        lines = textwrap.fill(text, 21).split('\n')
        line_count = len(lines)
        await display_text_legacy(delay)

async def listen(display, state_task, stop_event):
    """Listen for voice input and return recognized text."""
    settings = load_settings()
    speech_engine = settings.get("speechEngine", "pyttsx3")
    loop = asyncio.get_running_loop()

    def recognize_audio_litellm():
        """Use LiteLLM for STT with provider auto-detection."""
        try:
            from litellm import transcription
            import wave
            provider = get_litellm_provider()
            
            # Select model based on provider
            if provider == "openai":
                model = "openai/whisper-1"
            elif provider == "groq":
                model = "groq/whisper-large-v3"
            elif provider == "gemini":
                model = "gemini/gemini-1.5-flash"
            else:
                raise ValueError(f"No STT support for provider: {provider}")
            
            # Record audio to temp file
            with sr.Microphone() as source:
                if source.stream is None:
                    raise RuntimeError("Microphone not initialized.")
                audio = r.listen(source, timeout=2, phrase_time_limit=15)
            
            # Save audio as proper WAV file with correct format for Whisper
            # Whisper expects 16kHz mono WAV
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name
            
            # Get raw audio data and write proper WAV
            raw_data = audio.get_raw_data(convert_rate=16000, convert_width=2)
            with wave.open(tmp_path, 'wb') as wav_file:
                wav_file.setnchannels(1)  # mono
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(16000)  # 16kHz
                wav_file.writeframes(raw_data)
            
            try:
                with open(tmp_path, "rb") as audio_file:
                    response = transcription(model=model, file=audio_file)
                    text = response.text if hasattr(response, 'text') else str(response)
                    logger.debug(f"LiteLLM STT result: {text}")
                    return text if text else None
            finally:
                os.unlink(tmp_path)
                
        except sr.WaitTimeoutError:
            logger.debug("Listen timeout - no speech detected")
            return None
        except sr.UnknownValueError:
            logger.debug("Could not understand audio")
            return None
        except Exception as e:
            logger.warning(f"LiteLLM STT failed: {e}, falling back to Google")
            return None

    def recognize_audio_google():
        """Fallback to Google speech recognition."""
        try:
            with sr.Microphone() as source:
                if source.stream is None:
                    raise RuntimeError("Microphone not initialized.")
                
                audio = r.listen(source, timeout=2, phrase_time_limit=15)
                text = r.recognize_google(audio)
                return text if text else None
                        
        except sr.WaitTimeoutError:
            logger.debug("Listen timeout - no speech detected")
            return None
        except sr.UnknownValueError:
            logger.debug("Could not understand audio")
            return None

    # Try LiteLLM STT first if enabled and available
    text = None
    if speech_engine == 'litellm' and litellm_stt_available():
        text = await loop.run_in_executor(executor, recognize_audio_litellm)
    
    # Fallback to Google if LiteLLM failed or not available
    if text is None:
        text = await loop.run_in_executor(executor, recognize_audio_google)
    
    if text:
        state_task.cancel()
    return text

async def display_state(state, display, stop_event):
    if display is None:
        return # Skip updating the display if it's not initialized
    async with display_lock:
        # if state 'Connecting', display the 'No Network' and CPU temperature
        if state == "Connecting":
            display.text("No Network", 0, 0, 1)
            # Display CPU temperature in Celsius (e.g., 39°)
            cpu_temp = int(float(subprocess.check_output(["vcgencmd", "measure_temp"]).decode("utf-8").split("=")[1].split("'")[0]))
            temp_text_x = 100
            display.text(f"{cpu_temp}", temp_text_x, 0, 1)
            # degree symbol
            degree_x = 100 + len(f"{cpu_temp}") * 7 # Assuming each character is 7 pixels wide
            degree_y = 2
            degree_symbol(display, degree_x, degree_y, 2, 1)
            c_x = degree_x + 7 # Assuming each character is 7 pixels wide
            display.text("C", c_x, 0, 1)
            # Show the updated display with the text.
            display.show()
        while not stop_event.is_set():
            for i in range(4):
                if stop_event.is_set():
                    break
                display.fill_rect(0, 10, 128, 22, 0)
                display.text(f"{state}" + '.' * i, 0, 20, 1)
                display.show()
                await asyncio.sleep(0.5)

async def speak(text, stop_event=asyncio.Event(), word_callback=None):
    """
    Speak text using configured TTS engine.
    
    Args:
        text: Text to speak
        stop_event: Event to signal when speech completes
        word_callback: Optional async callback called with (word_index, word) as speech progresses
    """
    settings = load_settings()
    speech_engine = settings.get("speechEngine", "pyttsx3")
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
                
                # Select model based on provider
                if provider == "openai":
                    model = "openai/tts-1"
                    voice = "alloy"
                elif provider == "gemini":
                    model = "gemini/gemini-2.5-flash-preview-tts"
                    voice = "alloy"
                else:
                    raise ValueError(f"No TTS support for provider: {provider}")
                
                # Generate speech
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                    response = speech(model=model, voice=voice, input=text)
                    response.stream_to_file(tmp.name)
                    
                    # Play audio with word timing simulation
                    mixer.init()
                    mixer.music.load(tmp.name)
                    
                    # Get audio duration for timing
                    try:
                        from mutagen.mp3 import MP3
                        audio = MP3(tmp.name)
                        total_duration = audio.info.length
                    except:
                        # Fallback: estimate ~150 WPM
                        total_duration = len(words) * 0.4
                    
                    mixer.music.play()
                    
                    # Simulate word timing based on audio duration
                    if word_queue and words:
                        word_duration = total_duration / len(words)
                        start_time = time.time()
                        word_idx = 0
                        while mixer.music.get_busy():
                            elapsed = time.time() - start_time
                            expected_word = int(elapsed / word_duration)
                            while word_idx <= expected_word and word_idx < len(words):
                                asyncio.run_coroutine_threadsafe(
                                    word_queue.put((word_idx, words[word_idx])), loop
                                )
                                word_idx += 1
                            time.sleep(0.05)
                        # Signal remaining words
                        while word_idx < len(words):
                            asyncio.run_coroutine_threadsafe(
                                word_queue.put((word_idx, words[word_idx])), loop
                            )
                            word_idx += 1
                    else:
                        while mixer.music.get_busy():
                            time.sleep(0.1)
                    
                    mixer.quit()
                    os.unlink(tmp.name)
                    
                logger.debug(f"LiteLLM TTS completed with {model}")
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
                engine.connect('started-word', on_word)
            
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
            tts = gTTS(text, lang='en')
            tts.write_to_fp(mp3_fp)
            mixer.init()
            mp3_fp.seek(0)
            mixer.music.load(mp3_fp, "mp3")
            mixer.music.play()
            
            # Simulate word timing (~150 WPM)
            if word_queue and words:
                for i, word in enumerate(words):
                    duration = estimate_word_duration(word)
                    asyncio.run_coroutine_threadsafe(
                        word_queue.put((i, word)), loop
                    )
                    time.sleep(duration)
            
            while mixer.music.get_busy():
                time.sleep(0.1)
            mixer.quit()
        
        def _speak():
            if speech_engine == 'litellm' and litellm_tts_available():
                _speak_litellm()
            elif speech_engine == 'gtts':
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
                        word_idx, word = await asyncio.wait_for(word_queue.get(), timeout=0.1)
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


async def speak_with_display(text, display):
    """
    Speak text with synchronized OLED display.
    Words appear on screen as they are spoken.
    """
    if display is None:
        # No display, just speak
        stop_event = asyncio.Event()
        await speak(text, stop_event)
        return
    
    words = text.split()
    current_display_text = []
    
    async def on_word(word_idx, word):
        """Callback invoked as each word is spoken."""
        nonlocal current_display_text
        current_display_text.append(word)
        
        # Build display text from words spoken so far
        display_text = ' '.join(current_display_text)
        
        async with display_lock:
            # Clear text area (keep header)
            display.fill_rect(0, 10, 128, 22, 0)
            
            # Word-wrap and show recent text that fits on screen
            lines = textwrap.fill(display_text, 21).split('\n')
            
            # Show last 2 lines (most recent)
            visible_lines = lines[-2:] if len(lines) > 2 else lines
            
            for i, line in enumerate(visible_lines):
                try:
                    display.text(line, 0, 10 + i * 10, 1)
                except struct.error:
                    pass
            display.show()
    
    # Initialize display header
    async with display_lock:
        display.fill(0)
        try:
            ip_address = subprocess.check_output(["hostname", "-I"]).decode("utf-8").split(" ")[0]
            display.text(f"{ip_address}", 0, 0, 1)
            cpu_temp = int(float(subprocess.check_output(["vcgencmd", "measure_temp"]).decode("utf-8").split("=")[1].split("'")[0]))
            temp_text_x = 100
            display.text(f"{cpu_temp}", temp_text_x, 0, 1)
            degree_x = 100 + len(f"{cpu_temp}") * 7
            degree_symbol(display, degree_x, 2, 2, 1)
            display.text("C", degree_x + 7, 0, 1)
        except:
            pass
        display.show()
    
    # Speak with word callbacks
    stop_event = asyncio.Event()
    await speak(text, stop_event, word_callback=on_word)


async def handle_error(message, state_task, display):
    if state_task: 
        state_task.cancel()
    stop_event = asyncio.Event()
    await speak_with_display(message, display)
    logger.critical(f"An error occurred: {message}\n{traceback.format_exc()}")
