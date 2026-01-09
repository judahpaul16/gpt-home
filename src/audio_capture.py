"""
Real-time audio capture for waveform visualization.

Captures audio in real-time using PyAudio and sends amplitude data
to the display manager for visualization. Supports two modes:
- Output capture (monitor): For TTS playback visualization
- Microphone capture: For user speech visualization
"""

import asyncio
import math
import os
import re
import struct
import subprocess
import threading
import time
from enum import Enum
from typing import Callable, Optional

import numpy as np


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
            print("[AudioCapture] No ALSA input devices (arecord failed)", flush=True)
            return False
        if "card" not in result.stdout.lower():
            print("[AudioCapture] No ALSA input devices found", flush=True)
            return False

        # Just check if input devices exist - don't set global ALSA_CARD env vars
        # Setting ALSA_CARD globally would interfere with audio output which may
        # use a different card (e.g., HDMI on card 2 vs USB mic on card 1)
        card_match = re.search(r"card\s+(\d+):", result.stdout.lower())
        if card_match:
            card_num = card_match.group(1)
            print(
                f"[AudioCapture] Found ALSA input device on card {card_num}", flush=True
            )

        return True
    except Exception as e:
        print(f"[AudioCapture] ALSA check failed: {e}", flush=True)
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
        print("[AudioCapture] PyAudio module reused from sys.modules", flush=True)
        return _pyaudio_module

    try:
        import pyaudio

        _pyaudio_module = pyaudio
        print("[AudioCapture] PyAudio module imported", flush=True)
        return pyaudio
    except ImportError:
        PYAUDIO_AVAILABLE = False
        print("[AudioCapture] PyAudio not available", flush=True)
        return None


def _get_pyaudio_instance():
    """Get or create the singleton PyAudio instance."""
    global _pyaudio_instance
    with _pyaudio_instance_lock:
        if _pyaudio_instance is not None:
            return _pyaudio_instance

        pyaudio = _get_pyaudio()
        if pyaudio is None:
            return None

        try:
            _pyaudio_instance = pyaudio.PyAudio()
            print("[AudioCapture] PyAudio instance created", flush=True)
            return _pyaudio_instance
        except Exception as e:
            print(f"[AudioCapture] Failed to create PyAudio instance: {e}", flush=True)
            return None


def _release_pyaudio_instance():
    """Release the singleton PyAudio instance."""
    global _pyaudio_instance
    with _pyaudio_instance_lock:
        if _pyaudio_instance is not None:
            try:
                _pyaudio_instance.terminate()
                print("[AudioCapture] PyAudio instance terminated", flush=True)
            except Exception as e:
                print(f"[AudioCapture] Error terminating PyAudio: {e}", flush=True)
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

        print("[AudioCapture] Scanning audio devices...", flush=True)

        for i in range(p.get_device_count()):
            try:
                info = p.get_device_info_by_index(i)
                name = info.get("name", "").lower()
                max_input = info.get("maxInputChannels", 0)

                print(
                    f"[AudioCapture]   Device {i}: {info.get('name')} (inputs={max_input})",
                    flush=True,
                )

                if max_input > 0:
                    for keyword, priority in monitor_priorities:
                        if keyword in name and priority > best_priority:
                            best_device = i
                            best_priority = priority
                            print(
                                f"[AudioCapture]   -> Candidate monitor: {info['name']} (priority {priority})",
                                flush=True,
                            )
                            break
            except Exception as e:
                print(f"[AudioCapture]   Device {i}: Error - {e}", flush=True)
                continue

        if best_device is not None:
            info = p.get_device_info_by_index(best_device)
            print(
                f"[AudioCapture] Selected monitor device: {info['name']} (index {best_device})",
                flush=True,
            )
        else:
            print("[AudioCapture] No monitor device found", flush=True)

        return best_device

    def _find_default_input(self, p: "pyaudio.PyAudio") -> Optional[int]:
        """Find the default input device."""
        try:
            default_info = p.get_default_input_device_info()
            if default_info and default_info.get("maxInputChannels", 0) > 0:
                idx = default_info.get("index")
                print(
                    f"[AudioCapture] Using default input device: {default_info.get('name')} (index {idx})",
                    flush=True,
                )
                return idx
        except Exception as e:
            print(f"[AudioCapture] No default input device: {e}", flush=True)
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
                print("[AudioCapture] arecord -l failed", flush=True)
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

            if best_card is not None:
                print(
                    f"[AudioCapture] Found microphone via ALSA: card {best_card}",
                    flush=True,
                )

            return best_card

        except subprocess.TimeoutExpired:
            print("[AudioCapture] arecord -l timed out", flush=True)
            return None
        except FileNotFoundError:
            print("[AudioCapture] arecord not found", flush=True)
            return None
        except Exception as e:
            print(f"[AudioCapture] Error finding microphone via ALSA: {e}", flush=True)
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
                            print(
                                f"[AudioCapture] Matched card {card_num} to PyAudio index {i}: {info['name']}",
                                flush=True,
                            )
                            return i
                except Exception:
                    continue
        except Exception as e:
            print(
                f"[AudioCapture] Error mapping card to PyAudio index: {e}", flush=True
            )

        return None

    def _find_microphone_device(self, p: "pyaudio.PyAudio") -> Optional[int]:
        """Find the best microphone device for capturing user speech."""
        alsa_card = self._find_microphone_device_alsa()
        if alsa_card is not None:
            pyaudio_idx = self._find_pyaudio_index_for_card(p, alsa_card)
            if pyaudio_idx is not None:
                return pyaudio_idx

        print(
            "[AudioCapture] ALSA detection failed, trying PyAudio enumeration",
            flush=True,
        )

        mic_priorities = [
            ("usb", 100),
            ("microphone", 90),
            ("mic", 80),
            ("input", 70),
            ("capture", 60),
        ]

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
            print(f"[AudioCapture] PyAudio enumeration error: {e}", flush=True)

        if best_device is not None:
            try:
                info = p.get_device_info_by_index(best_device)
                print(
                    f"[AudioCapture] Selected microphone: {info['name']} (index {best_device})",
                    flush=True,
                )
            except Exception:
                pass

        return best_device

    def _calculate_bar_values(self, data: bytes) -> list:
        """
        Calculate bar values from audio data using shifting RMS amplitude.

        Calculates a single RMS value from the audio buffer and shifts it
        into the array, creating a scrolling waveform visualization.

        Returns list of 32 normalized amplitude values (0-1).
        """
        try:
            samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)

            if len(samples) == 0:
                rms = 0.0
            else:
                rms = np.sqrt(np.mean(samples**2))
                rms = min(1.0, rms / 4000.0)

            self._prev_values.pop(0)
            self._prev_values.append(rms)

            return list(self._prev_values)

        except Exception as e:
            print(f"[AudioCapture] Error calculating bars: {e}", flush=True)
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
                print(f"[AudioCapture] Device {name} has no input channels", flush=True)
                return False

            print(
                f"[AudioCapture] Device {name} validated (inputs={max_input})",
                flush=True,
            )
            return True
        except Exception as e:
            print(f"[AudioCapture] Device validation error: {e}", flush=True)
            return False

    def _capture_loop(self):
        """Main capture loop running in separate thread."""
        pyaudio = _get_pyaudio()
        if pyaudio is None:
            print("[AudioCapture] PyAudio not available, cannot capture", flush=True)
            self._running = False
            return

        # Initialize FORMAT now that pyaudio is available
        if not self._format_initialized:
            self.FORMAT = pyaudio.paInt16
            self._format_initialized = True

        try:
            self._pyaudio = _get_pyaudio_instance()
            if self._pyaudio is None:
                print("[AudioCapture] Failed to get PyAudio instance", flush=True)
                self._running = False
                return

            if self._mode == CaptureMode.MICROPHONE:
                device_index = self._find_microphone_device(self._pyaudio)
                if device_index is None:
                    print("[AudioCapture] No microphone device found", flush=True)
                    self._running = False
                    return
                if not self._validate_device(self._pyaudio, device_index):
                    print(
                        "[AudioCapture] Microphone device validation failed", flush=True
                    )
                    self._running = False
                    return
            else:
                device_index = self._find_monitor_device(self._pyaudio)

                if device_index is None:
                    print(
                        "[AudioCapture] No monitor device found, attempting PulseAudio setup...",
                        flush=True,
                    )
                    self._setup_pulseaudio_monitor()

                    self._pyaudio.terminate()
                    self._pyaudio = pyaudio.PyAudio()
                    device_index = self._find_monitor_device(self._pyaudio)

                if device_index is None:
                    device_index = self._find_default_input(self._pyaudio)
                    if device_index is None:
                        print("[AudioCapture] No input device found at all", flush=True)
                        self._running = False
                        return

                if not self._validate_device(self._pyaudio, device_index):
                    print("[AudioCapture] Output device validation failed", flush=True)
                    self._running = False
                    return

            device_info = self._pyaudio.get_device_info_by_index(device_index)
            sample_rate = int(device_info.get("defaultSampleRate", self.RATE))

            try:
                self._stream = self._pyaudio.open(
                    format=self.FORMAT,
                    channels=self.CHANNELS,
                    rate=sample_rate,
                    input=True,
                    input_device_index=device_index,
                    frames_per_buffer=self.CHUNK,
                )
            except Exception as e:
                print(f"[AudioCapture] Failed to open stream: {e}", flush=True)
                self._running = False
                return

            print(
                f"[AudioCapture] Started capturing audio at {sample_rate}Hz", flush=True
            )

            while self._running:
                try:
                    data = self._stream.read(self.CHUNK, exception_on_overflow=False)
                    bar_values = self._calculate_bar_values(data)

                    if self._callback and self._running:
                        self._callback(bar_values)

                except IOError as e:
                    continue
                except Exception as e:
                    print(f"[AudioCapture] Error in capture loop: {e}", flush=True)
                    break

        except Exception as e:
            print(f"[AudioCapture] Failed to start capture: {e}", flush=True)
            import traceback

            traceback.print_exc()
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
                print("[AudioCapture] PulseAudio not running", flush=True)
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
                    print(
                        f"[AudioCapture] Found PulseAudio sink: {sink_name}", flush=True
                    )
                    print(
                        f"[AudioCapture] Monitor source should be: {monitor_source}",
                        flush=True,
                    )

                    # Set the monitor as default source temporarily
                    subprocess.run(
                        ["pactl", "set-default-source", monitor_source],
                        capture_output=True,
                        timeout=5,
                    )
                    print(
                        f"[AudioCapture] Set default source to {monitor_source}",
                        flush=True,
                    )

        except FileNotFoundError:
            print(
                "[AudioCapture] pactl not found - PulseAudio tools not installed",
                flush=True,
            )
        except subprocess.TimeoutExpired:
            print("[AudioCapture] PulseAudio command timed out", flush=True)
        except Exception as e:
            print(f"[AudioCapture] PulseAudio setup error: {e}", flush=True)

    def _cleanup(self):
        """Clean up audio resources."""
        if self._stream:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception as e:
                print(f"[AudioCapture] Error closing stream: {e}", flush=True)
            self._stream = None

        self._pyaudio = None

        self._running = False
        print("[AudioCapture] Stopped capturing audio", flush=True)

    def start(self):
        """Start audio capture in background thread."""
        if self._running:
            return

        self._running = True
        self._prev_values = [0.0] * self.NUM_BARS
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
        """Check if capture is running."""
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
        print("[AudioCapture] PyAudio not available", flush=True)
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
    """Stop microphone capture."""
    global _mic_capture

    if _mic_capture:
        _mic_capture.stop()
        _mic_capture = None


def is_mic_capturing() -> bool:
    """Check if microphone capture is running."""
    return _mic_capture is not None and _mic_capture.is_running()


def get_current_mic_values() -> list:
    """Get current microphone amplitude values (32 floats 0-1)."""
    if _mic_capture and _mic_capture.is_running():
        return list(_mic_capture._prev_values)
    return [0.0] * 32


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
