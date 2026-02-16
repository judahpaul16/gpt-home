"""Waveform observers for display systems.

Implements the Observer pattern for different display targets.
"""

import threading
import time
from typing import List, Optional

from .interfaces import (
    RenderStrategy,
    WaveformData,
    WaveformObserver,
    WaveformState,
)
from .strategies import AlwaysOnStrategy, I2CDisplayStrategy, VoiceGatedStrategy


class FullDisplayWaveformObserver(WaveformObserver):
    """Observer for full display waveform rendering."""

    def __init__(self, voice_gated: bool = True):
        self._lock = threading.Lock()
        self._voice_gated = voice_gated
        self._strategy: RenderStrategy = (
            VoiceGatedStrategy() if voice_gated else AlwaysOnStrategy()
        )
        self._smoothed_values: List[float] = [0.0] * 32
        self._last_update_time = time.time()
        self._last_data: Optional[WaveformData] = None
        self._is_active = False

    def set_voice_gated(self, voice_gated: bool) -> None:
        with self._lock:
            if voice_gated != self._voice_gated:
                self._voice_gated = voice_gated
                self._strategy = (
                    VoiceGatedStrategy() if voice_gated else AlwaysOnStrategy()
                )

    def on_waveform_update(self, data: WaveformData) -> None:
        now = time.time()
        with self._lock:
            dt = now - self._last_update_time
            self._last_update_time = now
            self._last_data = data

            if self._strategy.should_render(data):
                self._smoothed_values = self._strategy.apply_smoothing(
                    self._smoothed_values, list(data.values), dt
                )

    def on_waveform_state_change(
        self, old_state: WaveformState, new_state: WaveformState
    ) -> None:
        with self._lock:
            self._is_active = new_state in (
                WaveformState.LISTENING_MIC,
                WaveformState.LISTENING_OUTPUT,
            )
            if self._is_active:
                min_height = self._strategy.get_render_params().get(
                    "min_bar_height", 0.0
                )
                self._smoothed_values = [min_height] * 32
            else:
                self._smoothed_values = [0.0] * 32

    def get_render_values(self) -> List[float]:
        with self._lock:
            return list(self._smoothed_values)

    def should_render(self) -> bool:
        with self._lock:
            return self._is_active

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._is_active

    @property
    def has_voice(self) -> bool:
        with self._lock:
            return self._last_data.has_voice if self._last_data else False


class I2CDisplayWaveformObserver(WaveformObserver):
    """Observer for I2C display waveform rendering."""

    def __init__(self):
        self._lock = threading.Lock()
        self._strategy = I2CDisplayStrategy()
        self._smoothed_values: List[float] = [0.0] * 32
        self._last_update_time = time.time()
        self._is_active = False

    def on_waveform_update(self, data: WaveformData) -> None:
        now = time.time()
        with self._lock:
            dt = now - self._last_update_time
            self._last_update_time = now

            if self._strategy.should_render(data):
                self._smoothed_values = self._strategy.apply_smoothing(
                    self._smoothed_values, list(data.values), dt
                )

    def on_waveform_state_change(
        self, old_state: WaveformState, new_state: WaveformState
    ) -> None:
        with self._lock:
            self._is_active = new_state in (
                WaveformState.LISTENING_MIC,
                WaveformState.LISTENING_OUTPUT,
            )
            if self._is_active:
                min_height = self._strategy.get_render_params().get(
                    "min_bar_height", 0.08
                )
                self._smoothed_values = [min_height] * 32
            else:
                self._smoothed_values = [0.0] * 32

    def get_render_values(self) -> List[float]:
        with self._lock:
            return list(self._smoothed_values)

    def should_render(self) -> bool:
        with self._lock:
            return self._is_active

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._is_active
