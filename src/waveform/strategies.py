"""Rendering strategies for waveform display.

Implements the Strategy pattern for different rendering behaviors.
All strategies show waveform when listening - they differ in minimum bar height
and whether silence shows flat bars or no bars.

Alexa/Google Home behavior:
- Always show listening indicator when in listening state
- Animate bars based on audio amplitude
- Show flat/minimal bars when silent (not hidden)
"""

from typing import Dict, List

from .interfaces import RenderStrategy, WaveformData, WaveformState


class VoiceGatedStrategy(RenderStrategy):
    """Strategy for SMART mode on full displays.

    Shows waveform whenever listening is active:
    - Flat (zero height) when no audio
    - Animated bars when audio detected
    """

    def __init__(self):
        self._smoothing_speed = 12.0
        self._decay_speed = 8.0
        self._min_bar_height = 0.0

    def should_render(self, data: WaveformData) -> bool:
        """Render whenever in listening state."""
        return data.state in (
            WaveformState.LISTENING_MIC,
            WaveformState.LISTENING_OUTPUT,
        )

    def apply_smoothing(
        self, current: List[float], target: List[float], dt: float
    ) -> List[float]:
        result = []
        for curr, tgt in zip(current, target):
            effective_target = max(self._min_bar_height, tgt)
            if effective_target > curr:
                speed = self._smoothing_speed
            else:
                speed = self._decay_speed
            diff = effective_target - curr
            new_val = curr + diff * min(1.0, speed * dt)
            result.append(max(self._min_bar_height, min(1.0, new_val)))
        return result

    def get_render_params(self) -> Dict:
        return {
            "min_bar_height": self._min_bar_height,
            "smoothing_speed": self._smoothing_speed,
        }


class AlwaysOnStrategy(RenderStrategy):
    """Strategy for dedicated WAVEFORM mode on full displays.

    Flat when silent, animated when audio detected.
    """

    def __init__(self):
        self._smoothing_speed = 10.0
        self._min_bar_height = 0.0

    def should_render(self, data: WaveformData) -> bool:
        return data.state in (
            WaveformState.LISTENING_MIC,
            WaveformState.LISTENING_OUTPUT,
        )

    def apply_smoothing(
        self, current: List[float], target: List[float], dt: float
    ) -> List[float]:
        result = []
        for curr, tgt in zip(current, target):
            effective_target = max(self._min_bar_height, tgt)
            diff = effective_target - curr
            new_val = curr + diff * min(1.0, self._smoothing_speed * dt)
            result.append(max(self._min_bar_height, min(1.0, new_val)))
        return result

    def get_render_params(self) -> Dict:
        return {
            "min_bar_height": self._min_bar_height,
            "smoothing_speed": self._smoothing_speed,
        }


class I2CDisplayStrategy(RenderStrategy):
    """Strategy for I2C OLED displays.

    Always shows waveform with visible flat bars when silent.
    """

    def __init__(self):
        self._smoothing_speed = 8.0
        self._min_bar_height = 0.08

    def should_render(self, data: WaveformData) -> bool:
        return data.state in (
            WaveformState.LISTENING_MIC,
            WaveformState.LISTENING_OUTPUT,
        )

    def apply_smoothing(
        self, current: List[float], target: List[float], dt: float
    ) -> List[float]:
        result = []
        for curr, tgt in zip(current, target):
            effective_target = max(self._min_bar_height, tgt)
            diff = effective_target - curr
            new_val = curr + diff * min(1.0, self._smoothing_speed * dt)
            result.append(max(self._min_bar_height, min(1.0, new_val)))
        return result

    def get_render_params(self) -> Dict:
        return {
            "min_bar_height": self._min_bar_height,
            "smoothing_speed": self._smoothing_speed,
            "bar_count": 32,
        }
