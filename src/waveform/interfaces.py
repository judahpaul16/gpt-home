"""Interfaces for the waveform visualization system.

Defines abstract base classes and data types used across the waveform package.
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List


class WaveformState(Enum):
    """State machine for waveform display lifecycle."""

    INACTIVE = auto()  # Not listening, no waveform
    LISTENING_MIC = auto()  # Listening to microphone input
    LISTENING_OUTPUT = auto()  # Listening to audio output (TTS)
    PAUSED = auto()  # Paused (e.g., Spotify playing)


class WaveformSource(Enum):
    """Source of audio for waveform."""

    MICROPHONE = "microphone"
    OUTPUT = "output"


@dataclass(frozen=True)
class WaveformData:
    """Immutable snapshot of waveform state.

    This is the data passed to observers on each update.
    Immutable to prevent observers from modifying shared state.
    """

    values: tuple  # 32 float values (0.0 - 1.0)
    has_voice: bool  # WebRTC VAD detected voice
    state: WaveformState
    source: WaveformSource
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self):
        # Ensure values is a tuple of exactly 32 floats
        if len(self.values) != 32:
            raise ValueError(
                f"WaveformData requires exactly 32 values, got {len(self.values)}"
            )


class WaveformObserver(ABC):
    """Observer interface for waveform updates.

    Implement this interface to receive waveform data updates.
    Each observer can process the data according to its needs
    (e.g., render to display, log, etc.).
    """

    @abstractmethod
    def on_waveform_update(self, data: WaveformData) -> None:
        """Called when waveform values change.

        This method is called at approximately 30fps when audio is active.
        Implementations should be efficient to avoid blocking.

        Args:
            data: Immutable snapshot of current waveform state
        """
        pass

    @abstractmethod
    def on_waveform_state_change(
        self, old_state: WaveformState, new_state: WaveformState
    ) -> None:
        """Called when waveform state transitions.

        Use this to handle lifecycle events (start/stop/pause).

        Args:
            old_state: Previous state
            new_state: New state
        """
        pass


class RenderStrategy(ABC):
    """Strategy for determining waveform rendering behavior.

    Different strategies implement different policies for when
    and how to render waveform visualization.
    """

    @abstractmethod
    def should_render(self, data: WaveformData) -> bool:
        """Determine if waveform should be rendered.

        Args:
            data: Current waveform data

        Returns:
            True if waveform bars should be rendered, False otherwise
        """
        pass

    @abstractmethod
    def apply_smoothing(
        self, current: List[float], target: List[float], dt: float
    ) -> List[float]:
        """Apply smoothing algorithm to waveform values.

        Args:
            current: Current smoothed values
            target: Target values from audio
            dt: Delta time since last frame

        Returns:
            New smoothed values
        """
        pass

    @abstractmethod
    def get_render_params(self) -> dict:
        """Get rendering parameters.

        Returns:
            Dictionary with rendering configuration
        """
        pass
