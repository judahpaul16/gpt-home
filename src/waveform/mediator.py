"""WaveformMediator - Central coordinator for waveform operations.

Implements the Mediator pattern to coordinate between:
- Audio capture (producer)
- Display systems (consumers/observers)
- State management

Single source of truth for waveform data.
Thread-safe for audio capture thread updates.
"""

import threading
import time
from typing import List, Optional, Set

import speech_recognition as sr

from .interfaces import (
    WaveformData,
    WaveformObserver,
    WaveformSource,
    WaveformState,
)


class WaveformMediator:
    """Central coordinator for all waveform operations.

    Singleton pattern ensures single instance across the application.
    All waveform data flows through this mediator.
    """

    _instance: Optional["WaveformMediator"] = None
    _instance_lock = threading.Lock()

    def __new__(cls):
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # Single source of truth for waveform values
        self._values: List[float] = [0.0] * 32
        self._data_lock = threading.Lock()

        # State management
        self._state = WaveformState.INACTIVE
        self._source = WaveformSource.MICROPHONE
        self._has_voice = False

        # Observer management
        self._observers: Set[WaveformObserver] = set()
        self._observer_lock = threading.Lock()

        # Throttling for display updates (~30fps)
        self._last_notify_time = 0.0
        self._min_notify_interval = 0.033

        # Audio activity detector reference (for VAD)
        self._detector = None

        self._initialized = True

    @classmethod
    def get_instance(cls) -> "WaveformMediator":
        """Get the singleton instance."""
        return cls()

    def set_audio_detector(self, detector) -> None:
        """Set reference to AudioActivityDetector for VAD.

        Args:
            detector: AudioActivityDetector instance
        """
        self._detector = detector

    # -------------------------------------------------------------------------
    # Observer Pattern
    # -------------------------------------------------------------------------

    def register_observer(self, observer: WaveformObserver) -> None:
        """Register an observer for waveform updates.

        Args:
            observer: Observer to register
        """
        with self._observer_lock:
            self._observers.add(observer)

    def unregister_observer(self, observer: WaveformObserver) -> None:
        """Unregister an observer.

        Args:
            observer: Observer to unregister
        """
        with self._observer_lock:
            self._observers.discard(observer)

    def _notify_observers(self, data: WaveformData) -> None:
        """Notify all observers of waveform update.

        Called outside of data lock to prevent deadlocks.
        """
        with self._observer_lock:
            observers = list(self._observers)

        for observer in observers:
            try:
                observer.on_waveform_update(data)
            except Exception:
                pass  # Don't let one observer break others

    def _notify_state_change(
        self, old_state: WaveformState, new_state: WaveformState
    ) -> None:
        """Notify observers of state transition."""
        with self._observer_lock:
            observers = list(self._observers)

        for observer in observers:
            try:
                observer.on_waveform_state_change(old_state, new_state)
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # State Pattern
    # -------------------------------------------------------------------------

    def start(self, source: WaveformSource = WaveformSource.MICROPHONE) -> None:
        old_state = self._state
        self._source = source

        if source == WaveformSource.MICROPHONE:
            self._state = WaveformState.LISTENING_MIC
        else:
            self._state = WaveformState.LISTENING_OUTPUT

        self.clear()

        if old_state != self._state:
            self._notify_state_change(old_state, self._state)

    def stop(self) -> None:
        """Stop waveform capture and display."""
        old_state = self._state
        self._state = WaveformState.INACTIVE
        self.clear()

        if old_state != self._state:
            self._notify_state_change(old_state, self._state)

    def pause(self) -> None:
        """Pause waveform (e.g., Spotify playing)."""
        old_state = self._state
        self._state = WaveformState.PAUSED

        if old_state != self._state:
            self._notify_state_change(old_state, self._state)

    def resume(self) -> None:
        """Resume from pause."""
        if self._state == WaveformState.PAUSED:
            old_state = self._state
            self._state = WaveformState.LISTENING_MIC
            self._notify_state_change(old_state, self._state)

    @property
    def state(self) -> WaveformState:
        """Get current state."""
        return self._state

    @property
    def is_active(self) -> bool:
        """Check if waveform is actively listening."""
        return self._state in (
            WaveformState.LISTENING_MIC,
            WaveformState.LISTENING_OUTPUT,
        )

    # -------------------------------------------------------------------------
    # Data Management (Single Source of Truth)
    # -------------------------------------------------------------------------

    def update_from_values(self, values: List[float]) -> None:
        """Update waveform from pre-computed amplitude values (thread-safe).

        Used by AudioCapture's continuous mic capture to feed the mediator
        without requiring sr.AudioData conversion.

        Args:
            values: List of 32 float values (0.0 - 1.0)
        """
        if not self.is_active:
            return

        if len(values) != 32:
            return

        has_voice = max(values) > 0.02

        with self._data_lock:
            self._values = list(values)
            self._has_voice = has_voice

        now = time.time()
        if now - self._last_notify_time >= self._min_notify_interval:
            self._last_notify_time = now
            data = self._create_snapshot()
            self._notify_observers(data)

    def update_from_audio_chunk(self, audio_chunk: sr.AudioData) -> None:
        if not self.is_active:
            return

        try:
            import audioop

            raw = audio_chunk.get_raw_data()
            sample_width = audio_chunk.sample_width

            if len(raw) < 64:
                return

            chunk_size = len(raw) // 32
            new_values = []

            for i in range(32):
                start = i * chunk_size
                end = start + chunk_size
                chunk = raw[start:end]
                try:
                    rms = audioop.rms(chunk, sample_width)
                    max_val = (1 << (8 * sample_width - 1)) - 1
                    normalized = min(1.0, rms / (max_val * 0.35))
                    new_values.append(normalized)
                except Exception:
                    new_values.append(0.0)

            has_voice = False
            if self._detector:
                try:
                    has_voice = self._detector.detect_voice_in_audio_data(audio_chunk)
                except Exception:
                    pass

            with self._data_lock:
                self._values = new_values
                self._has_voice = has_voice

            now = time.time()
            if now - self._last_notify_time >= self._min_notify_interval:
                self._last_notify_time = now
                data = self._create_snapshot()
                self._notify_observers(data)

        except Exception:
            pass

    def get_values(self) -> List[float]:
        """Get current waveform values (thread-safe copy).

        Returns:
            Copy of current 32 waveform values
        """
        with self._data_lock:
            return list(self._values)

    def get_snapshot(self) -> WaveformData:
        """Get immutable snapshot of current state.

        Returns:
            WaveformData with current values and state
        """
        with self._data_lock:
            return self._create_snapshot()

    def _create_snapshot(self) -> WaveformData:
        """Create snapshot (must hold _data_lock)."""
        return WaveformData(
            values=tuple(self._values),
            has_voice=self._has_voice,
            state=self._state,
            source=self._source,
            timestamp=time.time(),
        )

    def clear(self) -> None:
        """Clear waveform values."""
        with self._data_lock:
            self._values = [0.0] * 32
            self._has_voice = False


def get_waveform_mediator() -> WaveformMediator:
    """Get the singleton WaveformMediator instance.

    Returns:
        WaveformMediator singleton
    """
    return WaveformMediator.get_instance()
