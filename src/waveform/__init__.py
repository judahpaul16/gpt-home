"""Waveform visualization system.

This package provides a unified waveform visualization architecture using:
- Mediator Pattern: Central coordinator (WaveformMediator)
- Observer Pattern: Display subscriptions (WaveformObserver)
- Strategy Pattern: Rendering behaviors (RenderStrategy)
- State Pattern: Lifecycle management (WaveformState)
"""

from .interfaces import (
    RenderStrategy,
    WaveformData,
    WaveformObserver,
    WaveformSource,
    WaveformState,
)
from .mediator import WaveformMediator, get_waveform_mediator
from .observers import (
    FullDisplayWaveformObserver,
    I2CDisplayWaveformObserver,
)
from .strategies import (
    AlwaysOnStrategy,
    I2CDisplayStrategy,
    VoiceGatedStrategy,
)

__all__ = [
    # Interfaces
    "WaveformState",
    "WaveformSource",
    "WaveformData",
    "WaveformObserver",
    "RenderStrategy",
    # Mediator
    "WaveformMediator",
    "get_waveform_mediator",
    # Strategies
    "VoiceGatedStrategy",
    "AlwaysOnStrategy",
    "I2CDisplayStrategy",
    # Observers
    "FullDisplayWaveformObserver",
    "I2CDisplayWaveformObserver",
]
