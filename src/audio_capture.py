"""
Real-time audio capture for waveform visualization.

Captures audio in real-time using PyAudio and sends amplitude data
to the display manager for visualization. Supports two modes:
- Output capture (monitor): For TTS playback visualization
- Microphone capture: For user speech visualization
"""

import asyncio
import logging
import math
import os
import queue as _queue_mod
import re
import struct
import subprocess
import threading
import time
from collections import deque
from enum import Enum
from typing import Callable, Optional

import numpy as np

logger = logging.getLogger("audio_capture")

_logged_alsa_card = None

MIC_PRIORITIES = [
    ("usb", 100),
    ("microphone", 90),
    ("mic", 80),
    ("audio", 70),
    ("voicehat", 60),
    ("googlevoice", 60),
    ("wm8960", 60),
    ("input", 50),
    ("capture", 40),
]


class CaptureMode(Enum):
    OUTPUT = "output"
    MICROPHONE = "microphone"


def _check_alsa_input_devices_at_startup() -> bool:
    """Check if ALSA input devices exist before allowing PyAudio import.

    PortAudio can crash with assertion failures during Pa_Initialize() if
    no valid default input device is configured. This check runs at module
    load time to prevent the crash.

    NOTE: This function only checks for device availability.
    It does NOT set global ALSA environment variables, as those would interfere
    with audio playback (which uses a different card for output).
    PyAudio is deferred to first use.
    """
    try:
        result = subprocess.run(
            ["arecord", "-l"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            logger.warning("No ALSA input devices (arecord failed)")
            return False
        if "card" not in result.stdout.lower():
            logger.warning("No ALSA input devices found")
            return False

        card_match = re.search(r"card\s+(\d+):", result.stdout.lower())
        if card_match:
            card_num = card_match.group(1)
            logger.debug("Found ALSA input device on card %s", card_num)

        return True
    except Exception as e:
        logger.error("ALSA check failed: %s", e)
        return False


_ALSA_DEVICES_AVAILABLE = _check_alsa_input_devices_at_startup()

_pyaudio_module = None
_pyaudio_instance = None
_pyaudio_instance_lock = threading.Lock()
PYAUDIO_AVAILABLE = _ALSA_DEVICES_AVAILABLE


def _get_pyaudio():
    """Lazily import and return pyaudio module."""
    global _pyaudio_module, PYAUDIO_AVAILABLE
    if _pyaudio_module is not None:
        return _pyaudio_module
    if not _ALSA_DEVICES_AVAILABLE:
        return None

    import sys

    if "pyaudio" in sys.modules:
        _pyaudio_module = sys.modules["pyaudio"]
        return _pyaudio_module

    try:
        import pyaudio

        _pyaudio_module = pyaudio
        return pyaudio
    except ImportError:
        PYAUDIO_AVAILABLE = False
        logger.error("PyAudio not available")
        return None


def _get_pyaudio_instance():
    """Get or create the singleton PyAudio instance."""
    global _pyaudio_instance
    with _pyaudio_instance_lock:
        if _pyaudio_instance is not None:
            try:
                _pyaudio_instance.get_device_count()
                return _pyaudio_instance
            except Exception:
                try:
                    _pyaudio_instance.terminate()
                except Exception:
                    pass
                _pyaudio_instance = None

        pyaudio = _get_pyaudio()
        if pyaudio is None:
            return None

        try:
            inst = pyaudio.PyAudio()
            inst.get_device_count()
            _pyaudio_instance = inst
            return _pyaudio_instance
        except Exception as e:
            logger.error("Failed to create PyAudio instance: %s", e)
            try:
                inst.terminate()
            except Exception:
                pass
            return None


def _release_pyaudio_instance():
    """Release the singleton PyAudio instance."""
    global _pyaudio_instance
    with _pyaudio_instance_lock:
        if _pyaudio_instance is not None:
            try:
                _pyaudio_instance.terminate()
            except Exception as e:
                logger.error("Error terminating PyAudio: %s", e)
            _pyaudio_instance = None


class AudioCapture:
    """Real-time audio capture for waveform visualization."""

    def __init__(
        self,
        callback: Optional[Callable[[list], None]] = None,
        mode: CaptureMode = CaptureMode.OUTPUT,
    ):
        """
        Initialize audio capture.

        Args:
            callback: Function to call with amplitude values (list of 32 floats 0-1)
            mode: CaptureMode.OUTPUT for TTS playback, CaptureMode.MICROPHONE for user speech
        """
        self._callback = callback
        self._mode = mode
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._pyaudio: Optional["pyaudio.PyAudio"] = None
        self._stream = None

        # Audio parameters - FORMAT is set lazily when pyaudio is loaded
        self._format_initialized = False
        self.FORMAT = None
        self.CHANNELS = 1
        self.RATE = 44100
        self.CHUNK = 1024  # ~23ms at 44100Hz
        self.NUM_BARS = 32

        # For smoothing
        self._prev_values = [0.0] * self.NUM_BARS

        # Adaptive gain: track recent peak to auto-scale
        self._recent_peak = 0.0
        self._peak_decay = 0.95  # Slow decay for stable gain

        self._raw_buffer: deque = deque(maxlen=25)
        self._capture_sample_rate: int = self.RATE
        self._listen_queue: Optional[_queue_mod.Queue] = None

    def _find_monitor_device(self, p: "pyaudio.PyAudio") -> Optional[int]:
        """
        Find a monitor/loopback device for capturing audio output.

        On Raspberry Pi with PulseAudio, we look for the monitor source
        which captures what's being played through the speakers.
        """
        # Priority order for finding output monitor devices
        # Higher priority = checked first
        monitor_priorities = [
            ("monitor of", 100),  # PulseAudio monitor source (exact)
            (".monitor", 90),  # PulseAudio monitor suffix
            ("pulse", 80),  # PulseAudio default
            ("loopback", 70),  # ALSA loopback
            ("stereo mix", 60),  # Windows stereo mix
            ("what u hear", 50),  # Some sound cards
        ]

        best_device = None
        best_priority = -1

        for i in range(p.get_device_count()):
            try:
                info = p.get_device_info_by_index(i)
                name = info.get("name", "").lower()
                max_input = info.get("maxInputChannels", 0)

                if max_input > 0:
                    for keyword, priority in monitor_priorities:
                        if keyword in name and priority > best_priority:
                            best_device = i
                            best_priority = priority
                            break
            except Exception:
                continue

        if best_device is not None:
            info = p.get_device_info_by_index(best_device)
            logger.debug(
                "Selected monitor device: %s (index %d)", info["name"], best_device
            )
        else:
            logger.debug("No monitor device found")

        return best_device

    def _find_default_input(self, p: "pyaudio.PyAudio") -> Optional[int]:
        """Find the default input device."""
        try:
            default_info = p.get_default_input_device_info()
            if default_info and default_info.get("maxInputChannels", 0) > 0:
                idx = default_info.get("index")
                logger.debug(
                    "Using default input device: %s (index %s)",
                    default_info.get("name"),
                    idx,
                )
                return idx
        except Exception:
            pass
        return None

    def _find_microphone_device_alsa(self) -> Optional[int]:
        """Find the best microphone device using ALSA directly.

        This avoids PyAudio initialization which can crash with PortAudio
        assertion failures when no default input device is configured.
        Returns the ALSA card number for the best microphone found.
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

            mic_priorities = MIC_PRIORITIES

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

            global _logged_alsa_card
            if best_card is not None and best_card != _logged_alsa_card:
                logger.debug("Found microphone via ALSA: card %d", best_card)
                _logged_alsa_card = best_card

            return best_card

        except subprocess.TimeoutExpired:
            return None
        except FileNotFoundError:
            return None
        except Exception as e:
            logger.error("Error finding microphone via ALSA: %s", e)
            return None

    def _find_pyaudio_index_for_card(
        self, p: "pyaudio.PyAudio", card_num: int
    ) -> Optional[int]:
        """Find the PyAudio device index for a given ALSA card number."""
        try:
            for i in range(p.get_device_count()):
                try:
                    info = p.get_device_info_by_index(i)
                    name = info.get("name", "").lower()
                    max_input = info.get("maxInputChannels", 0)

                    if max_input > 0:
                        if f"hw:{card_num}" in name or f"plughw:{card_num}" in name:
                            return i
                except Exception:
                    continue
        except Exception as e:
            logger.error("Error mapping card to PyAudio index: %s", e)

        return None

    def _find_microphone_device(self, p: "pyaudio.PyAudio") -> Optional[int]:
        """Find the best microphone device for capturing user speech."""
        try:
            info = p.get_default_input_device_info()
            idx = int(info["index"])
            logger.debug("Using default ALSA input device (index %d)", idx)
            return idx
        except Exception:
            pass

        alsa_card = self._find_microphone_device_alsa()
        if alsa_card is not None:
            pyaudio_idx = self._find_pyaudio_index_for_card(p, alsa_card)
            if pyaudio_idx is not None:
                return pyaudio_idx

        logger.debug("ALSA detection failed, trying PyAudio enumeration")

        mic_priorities = MIC_PRIORITIES

        best_device = None
        best_priority = -1

        try:
            for i in range(p.get_device_count()):
                try:
                    info = p.get_device_info_by_index(i)
                    name = info.get("name", "").lower()
                    max_input = info.get("maxInputChannels", 0)

                    if max_input > 0:
                        if "monitor" in name or "loopback" in name:
                            continue

                        for keyword, priority in mic_priorities:
                            if keyword in name and priority > best_priority:
                                best_device = i
                                best_priority = priority
                                break
                except Exception:
                    continue
        except Exception as e:
            logger.error("PyAudio enumeration error: %s", e)

        if best_device is not None:
            try:
                info = p.get_device_info_by_index(best_device)
                logger.debug(
                    "Selected microphone: %s (index %d)", info["name"], best_device
                )
            except Exception:
                pass

        return best_device

    def get_recent_audio(self, duration_s: float = 0.5) -> tuple:
        chunks_needed = max(1, int(duration_s * self._capture_sample_rate / self.CHUNK))
        recent = list(self._raw_buffer)[-chunks_needed:]
        if not recent:
            return b"", self._capture_sample_rate, 2
        return b"".join(recent), self._capture_sample_rate, 2

    def _calculate_bar_values(self, data: bytes) -> list:
        """
        Calculate bar values from audio data using shifting RMS amplitude.

        Calculates a single RMS value from the audio buffer and shifts it
        into the array, creating a scrolling waveform visualization.
        Uses adaptive gain to auto-scale based on recent audio levels.

        Returns list of 32 normalized amplitude values (0-1).
        """
        try:
            samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)

            if len(samples) == 0:
                rms = 0.0
            else:
                raw_rms = np.sqrt(np.mean(samples**2))

                # Track recent peak for adaptive gain (slow decay)
                if raw_rms > self._recent_peak:
                    self._recent_peak = raw_rms
                else:
                    self._recent_peak *= self._peak_decay

                # Use adaptive normalization: divide by recent peak with a floor
                # Floor of 800 prevents noise from being amplified too much
                # Ceiling of 3000 prevents very loud audio from under-scaling
                divisor = max(500.0, min(2000.0, self._recent_peak * 1.2))
                rms = min(1.0, raw_rms / divisor)

            self._prev_values.pop(0)
            self._prev_values.append(rms)

            return list(self._prev_values)

        except Exception as e:
            logger.error("Error calculating bars: %s", e)
            return [0.0] * self.NUM_BARS

    def _calculate_rms(self, data: bytes) -> float:
        """Calculate RMS amplitude from audio data."""
        try:
            samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
            if len(samples) == 0:
                return 0.0
            rms = np.sqrt(np.mean(samples**2))
            # Normalize (16-bit max is 32768)
            return min(1.0, rms / 16384.0)
        except Exception:
            return 0.0

    def _validate_device(self, p: "pyaudio.PyAudio", device_index: int) -> bool:
        """Validate that a device can be opened."""
        try:
            info = p.get_device_info_by_index(device_index)
            name = info.get("name", "")
            max_input = info.get("maxInputChannels", 0)

            if max_input <= 0:
                return False

            return True
        except Exception:
            return False

    def _capture_loop(self):
        """Main capture loop running in separate thread."""
        pyaudio = _get_pyaudio()
        if pyaudio is None:
            self._running = False
            return

        if not self._format_initialized:
            self.FORMAT = pyaudio.paInt16
            self._format_initialized = True

        device_index = None
        for attempt in range(5):
            if not self._running:
                return

            self._pyaudio = _get_pyaudio_instance()
            if self._pyaudio is None:
                time.sleep(1.0 * (attempt + 1))
                continue

            if self._mode == CaptureMode.MICROPHONE:
                device_index = self._find_microphone_device(self._pyaudio)
                if device_index is not None and self._validate_device(self._pyaudio, device_index):
                    break
                device_index = None
            else:
                device_index = self._find_monitor_device(self._pyaudio)

                if device_index is None:
                    self._setup_pulseaudio_monitor()
                    _release_pyaudio_instance()
                    self._pyaudio = _get_pyaudio_instance()
                    if self._pyaudio:
                        device_index = self._find_monitor_device(self._pyaudio)

                if device_index is None and self._pyaudio:
                    device_index = self._find_default_input(self._pyaudio)

                if device_index is not None and self._validate_device(self._pyaudio, device_index):
                    break
                device_index = None

            _release_pyaudio_instance()
            time.sleep(1.0 * (attempt + 1))

        if device_index is None:
            logger.error("Could not find audio device after retries")
            self._running = False
            self._cleanup()
            return

        try:
            device_info = self._pyaudio.get_device_info_by_index(device_index)
            sample_rate = int(device_info.get("defaultSampleRate", self.RATE))

            self._capture_sample_rate = sample_rate

            self._stream = self._pyaudio.open(
                format=self.FORMAT,
                channels=self.CHANNELS,
                rate=sample_rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=self.CHUNK,
            )

            while self._running:
                if self._stream is None:
                    time.sleep(0.05)
                    continue
                try:
                    data = self._stream.read(self.CHUNK, exception_on_overflow=False)
                    self._raw_buffer.append(data)
                    lq = self._listen_queue
                    if lq is not None:
                        try:
                            lq.put_nowait(data)
                        except _queue_mod.Full:
                            pass
                    bar_values = self._calculate_bar_values(data)

                    if self._callback and self._running:
                        self._callback(bar_values)

                except IOError:
                    continue
                except Exception as e:
                    if self._stream is None:
                        continue
                    logger.error("Error in capture loop: %s", e)
                    break

        except Exception as e:
            logger.error("Failed to start capture: %s", e, exc_info=True)
        finally:
            self._running = False
            self._cleanup()

    def _setup_pulseaudio_monitor(self):
        """Try to set up PulseAudio monitor source for capturing audio output."""
        import subprocess

        try:
            # Check if PulseAudio is running
            result = subprocess.run(
                ["pactl", "info"], capture_output=True, text=True, timeout=5
            )

            if result.returncode != 0:
                return

            # List sinks to find the default output
            result = subprocess.run(
                ["pactl", "list", "short", "sinks"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0 and result.stdout.strip():
                sinks = result.stdout.strip().split("\n")
                if sinks:
                    # Get the first sink name
                    sink_name = (
                        sinks[0].split("\t")[1]
                        if "\t" in sinks[0]
                        else sinks[0].split()[1]
                    )
                    monitor_source = f"{sink_name}.monitor"

                    subprocess.run(
                        ["pactl", "set-default-source", monitor_source],
                        capture_output=True,
                        timeout=5,
                    )

        except FileNotFoundError:
            pass
        except subprocess.TimeoutExpired:
            pass
        except Exception as e:
            logger.error("PulseAudio setup error: %s", e)

    def _cleanup(self):
        """Clean up audio resources."""
        if self._stream:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception as e:
                logger.error("Error closing stream: %s", e)
            self._stream = None

        self._pyaudio = None
        self._running = False

    def start(self):
        """Start audio capture in background thread."""
        if self._running:
            return

        self._running = True
        self._prev_values = [0.0] * self.NUM_BARS
        self._recent_peak = 0.0
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop audio capture."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        self._prev_values = [0.0] * self.NUM_BARS

    def is_running(self) -> bool:
        return self._running


# Global instance for easy access
_audio_capture: Optional[AudioCapture] = None
_amplitude_callback: Optional[Callable[[list], None]] = None


def set_amplitude_callback(callback: Callable[[list], None]):
    """Set the callback function for amplitude updates."""
    global _amplitude_callback
    _amplitude_callback = callback


def start_audio_capture(mode: CaptureMode = CaptureMode.OUTPUT):
    """Start global audio capture.

    Args:
        mode: CaptureMode.OUTPUT for TTS playback, CaptureMode.MICROPHONE for user speech
    """
    global _audio_capture

    if not PYAUDIO_AVAILABLE:
        return

    if _audio_capture and _audio_capture.is_running():
        return

    def callback(values: list):
        if _amplitude_callback:
            _amplitude_callback(values)

    _audio_capture = AudioCapture(callback=callback, mode=mode)
    _audio_capture.start()


def stop_audio_capture():
    """Stop global audio capture."""
    global _audio_capture

    if _audio_capture:
        _audio_capture.stop()
        _audio_capture = None


def is_capturing() -> bool:
    """Check if audio capture is running."""
    return _audio_capture is not None and _audio_capture.is_running()


# Microphone capture for user speech visualization
_mic_capture: Optional[AudioCapture] = None
_mic_callback: Optional[Callable[[list], None]] = None


def set_mic_callback(callback: Callable[[list], None]):
    """Set callback for microphone amplitude updates."""
    global _mic_callback
    _mic_callback = callback


def start_mic_capture():
    """Start microphone capture for user speech visualization."""
    global _mic_capture

    if not PYAUDIO_AVAILABLE:
        return

    if _mic_capture and _mic_capture.is_running():
        return

    def callback(values: list):
        if _mic_callback:
            _mic_callback(values)

    _mic_capture = AudioCapture(callback=callback, mode=CaptureMode.MICROPHONE)
    _mic_capture.start()


def stop_mic_capture():
    """Stop microphone capture and release PyAudio resources.

    Releases the global PyAudio singleton so that sr.Microphone (which creates
    its own PyAudio instance) can safely use PortAudio without heap corruption.
    """
    global _mic_capture

    if _mic_capture:
        _mic_capture.stop()
        _mic_capture = None
    _release_pyaudio_instance()


def is_mic_capturing() -> bool:
    return _mic_capture is not None and _mic_capture.is_running()


def get_current_mic_values() -> list:
    if _mic_capture and _mic_capture.is_running():
        return list(_mic_capture._prev_values)
    return [0.0] * 32


def get_mic_audio(duration_s: float = 0.5) -> tuple:
    if _mic_capture and _mic_capture.is_running():
        return _mic_capture.get_recent_audio(duration_s)
    return b"", 44100, 2


def get_mic_capture_info() -> tuple:
    if _mic_capture and _mic_capture.is_running():
        return _mic_capture._capture_sample_rate, _mic_capture.CHUNK
    return 44100, 1024


def start_mic_listen_feed(q: _queue_mod.Queue) -> None:
    if _mic_capture:
        _mic_capture._listen_queue = q


def stop_mic_listen_feed() -> None:
    if _mic_capture:
        _mic_capture._listen_queue = None


# Async wrappers for use in async code
async def async_start_audio_capture(mode: CaptureMode = CaptureMode.OUTPUT):
    """Async wrapper to start audio capture."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: start_audio_capture(mode))


async def async_stop_audio_capture():
    """Async wrapper to stop audio capture."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, stop_audio_capture)


async def async_start_mic_capture():
    """Async wrapper to start microphone capture."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, start_mic_capture)


async def async_stop_mic_capture():
    """Async wrapper to stop microphone capture."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, stop_mic_capture)
