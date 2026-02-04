"""Unified audio activity detection using Strategy pattern.

This module centralizes all audio threshold and activity detection logic,
providing a clean interface for both I2C and full displays to determine
when audio activity (speech) is present.

Design Patterns Used:
- Strategy: Different detection strategies (RMS, Peak, VAD, WebRTC VAD)
- Observer: Notify registered callbacks when activity state changes
- Singleton: Single detector instance shared across the application
"""

import audioop
import math
import struct
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Deque, Dict, List, Optional

import speech_recognition as sr

try:
    import webrtcvad

    WEBRTC_VAD_AVAILABLE = True
except ImportError:
    WEBRTC_VAD_AVAILABLE = False


class DetectionStrategy(Enum):
    RMS = auto()
    PEAK = auto()
    WINDOWED_PEAK = auto()
    WEBRTC_VAD = auto()


@dataclass
class AudioMetrics:
    db_level: float = -100.0
    rms: float = 0.0
    peak: float = 0.0
    normalized_amplitude: float = 0.0
    has_activity: bool = False
    timestamp: float = field(default_factory=time.time)


@dataclass
class ThresholdConfig:
    vad_threshold_db: float = -50.0
    silence_rms_threshold: int = 200
    grace_frames: int = 10


class BaseDetectionStrategy(ABC):
    @abstractmethod
    def detect(
        self, audio_data: bytes, sample_width: int, config: ThresholdConfig
    ) -> AudioMetrics:
        pass


class RMSDetectionStrategy(BaseDetectionStrategy):
    def detect(
        self, audio_data: bytes, sample_width: int, config: ThresholdConfig
    ) -> AudioMetrics:
        if len(audio_data) < 2:
            return AudioMetrics()

        try:
            rms = audioop.rms(audio_data, sample_width)
            max_val = (1 << (8 * sample_width - 1)) - 1
            normalized = min(1.0, rms / (max_val * 0.35))
            db_level = 20 * math.log10(rms / max_val + 1e-10) if rms > 0 else -100.0

            return AudioMetrics(
                db_level=db_level,
                rms=float(rms),
                normalized_amplitude=normalized,
                has_activity=db_level > config.vad_threshold_db,
                timestamp=time.time(),
            )
        except Exception:
            return AudioMetrics()


class PeakDetectionStrategy(BaseDetectionStrategy):
    def detect(
        self, audio_data: bytes, sample_width: int, config: ThresholdConfig
    ) -> AudioMetrics:
        if len(audio_data) < 2:
            return AudioMetrics()

        try:
            peak = audioop.max(audio_data, sample_width)
            max_val = (1 << (8 * sample_width - 1)) - 1
            normalized = min(1.0, peak / max_val)
            db_level = 20 * math.log10(peak / max_val + 1e-10) if peak > 0 else -100.0

            return AudioMetrics(
                db_level=db_level,
                peak=float(peak),
                normalized_amplitude=normalized,
                has_activity=db_level > config.vad_threshold_db,
                timestamp=time.time(),
            )
        except Exception:
            return AudioMetrics()


class WindowedPeakDetectionStrategy(BaseDetectionStrategy):
    def __init__(self, window_size: int = 1600, hop_size: int = 800):
        self._window_size = window_size
        self._hop_size = hop_size

    def detect(
        self, audio_data: bytes, sample_width: int, config: ThresholdConfig
    ) -> AudioMetrics:
        if len(audio_data) < 100:
            return AudioMetrics()

        try:
            samples = struct.unpack(f"<{len(audio_data) // sample_width}h", audio_data)
            if not samples:
                return AudioMetrics()

            peak_rms = 0.0
            for i in range(0, len(samples) - self._window_size, self._hop_size):
                window = samples[i : i + self._window_size]
                sum_squares = sum(s * s for s in window)
                rms = math.sqrt(sum_squares / len(window))
                peak_rms = max(peak_rms, rms)

            if peak_rms < 1:
                return AudioMetrics()

            max_val = 32768.0
            db_level = 20 * math.log10(peak_rms / max_val)
            normalized = min(1.0, peak_rms / (max_val * 0.35))

            return AudioMetrics(
                db_level=db_level,
                rms=peak_rms,
                peak=peak_rms,
                normalized_amplitude=normalized,
                has_activity=db_level > config.vad_threshold_db,
                timestamp=time.time(),
            )
        except Exception:
            return AudioMetrics()


class WebRTCVADStrategy(BaseDetectionStrategy):
    """Voice Activity Detection using WebRTC VAD.

    This strategy detects actual human speech rather than just audio amplitude.
    It's more robust against ambient noise like fans, traffic, etc.

    Aggressiveness modes (0-3):
    - 0: Least aggressive, more false positives but catches more speech
    - 1: Moderate
    - 2: More aggressive
    - 3: Most aggressive, fewer false positives but may miss quiet speech
    """

    def __init__(self, aggressiveness: int = 2, sample_rate: int = 16000):
        self._aggressiveness = aggressiveness
        self._sample_rate = sample_rate
        self._vad = None
        self._init_vad()
        self._speech_frames = 0
        self._silence_frames = 0
        self._min_speech_frames = 3
        self._lock = threading.Lock()

    def _init_vad(self) -> None:
        if WEBRTC_VAD_AVAILABLE:
            try:
                self._vad = webrtcvad.Vad(self._aggressiveness)
            except Exception:
                self._vad = None

    def _resample_audio(
        self, audio_data: bytes, orig_rate: int, target_rate: int, sample_width: int
    ) -> bytes:
        """Resample audio to target sample rate."""
        if orig_rate == target_rate:
            return audio_data
        try:
            resampled, _ = audioop.ratecv(
                audio_data, sample_width, 1, orig_rate, target_rate, None
            )
            return resampled
        except Exception:
            return audio_data

    def detect(
        self, audio_data: bytes, sample_width: int, config: ThresholdConfig
    ) -> AudioMetrics:
        if not WEBRTC_VAD_AVAILABLE or self._vad is None:
            return RMSDetectionStrategy().detect(audio_data, sample_width, config)

        if len(audio_data) < 320:
            return AudioMetrics()

        try:
            rms = audioop.rms(audio_data, sample_width)
            max_val = (1 << (8 * sample_width - 1)) - 1
            normalized = min(1.0, rms / (max_val * 0.35))
            db_level = 20 * math.log10(rms / max_val + 1e-10) if rms > 0 else -100.0

            if sample_width != 2:
                audio_data = audioop.lin2lin(audio_data, sample_width, 2)

            frame_duration_ms = 30
            bytes_per_frame = int(self._sample_rate * 2 * frame_duration_ms / 1000)

            speech_detected = False
            frames_checked = 0
            speech_frame_count = 0

            for i in range(0, len(audio_data) - bytes_per_frame, bytes_per_frame):
                frame = audio_data[i : i + bytes_per_frame]
                if len(frame) == bytes_per_frame:
                    try:
                        is_speech = self._vad.is_speech(frame, self._sample_rate)
                        frames_checked += 1
                        if is_speech:
                            speech_frame_count += 1
                    except Exception:
                        pass

            with self._lock:
                if speech_frame_count >= self._min_speech_frames:
                    self._speech_frames += 1
                    self._silence_frames = 0
                    speech_detected = True
                else:
                    self._silence_frames += 1
                    if self._silence_frames > 5:
                        self._speech_frames = 0
                    speech_detected = self._speech_frames > 0

            return AudioMetrics(
                db_level=db_level,
                rms=float(rms),
                normalized_amplitude=normalized,
                has_activity=speech_detected,
                timestamp=time.time(),
            )
        except Exception:
            return AudioMetrics()

    def detect_voice_in_audio(
        self, audio: sr.AudioData, sample_rate: int = 16000
    ) -> bool:
        """Check if audio contains human voice using WebRTC VAD."""
        if not WEBRTC_VAD_AVAILABLE or self._vad is None:
            return True

        try:
            raw_data = audio.get_raw_data(convert_rate=sample_rate, convert_width=2)

            frame_duration_ms = 30
            bytes_per_frame = int(sample_rate * 2 * frame_duration_ms / 1000)

            speech_frames = 0
            total_frames = 0

            for i in range(0, len(raw_data) - bytes_per_frame, bytes_per_frame):
                frame = raw_data[i : i + bytes_per_frame]
                if len(frame) == bytes_per_frame:
                    try:
                        if self._vad.is_speech(frame, sample_rate):
                            speech_frames += 1
                        total_frames += 1
                    except Exception:
                        pass

            if total_frames == 0:
                return False

            speech_ratio = speech_frames / total_frames
            return speech_ratio > 0.1

        except Exception:
            return True


ActivityCallback = Callable[[bool, AudioMetrics], None]


class AudioActivityDetector:
    _instance: Optional["AudioActivityDetector"] = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._config = ThresholdConfig()
        self._webrtc_vad = WebRTCVADStrategy() if WEBRTC_VAD_AVAILABLE else None
        self._strategies: Dict[DetectionStrategy, BaseDetectionStrategy] = {
            DetectionStrategy.RMS: RMSDetectionStrategy(),
            DetectionStrategy.PEAK: PeakDetectionStrategy(),
            DetectionStrategy.WINDOWED_PEAK: WindowedPeakDetectionStrategy(),
            DetectionStrategy.WEBRTC_VAD: self._webrtc_vad or RMSDetectionStrategy(),
        }
        self._active_strategy = DetectionStrategy.RMS
        self._callbacks: List[ActivityCallback] = []
        self._callback_lock = threading.Lock()

        self._metrics_history: Deque[AudioMetrics] = deque(maxlen=30)
        self._current_activity_state = False
        self._frames_since_activity = 0
        self._smoothed_amplitude = 0.0

        self._initialized = True

    @classmethod
    def get_instance(cls) -> "AudioActivityDetector":
        return cls()

    def configure(
        self,
        vad_threshold_db: Optional[float] = None,
        silence_rms_threshold: Optional[int] = None,
        grace_frames: Optional[int] = None,
    ) -> None:
        if vad_threshold_db is not None:
            self._config.vad_threshold_db = vad_threshold_db
        if silence_rms_threshold is not None:
            self._config.silence_rms_threshold = silence_rms_threshold
        if grace_frames is not None:
            self._config.grace_frames = grace_frames

    def set_strategy(self, strategy: DetectionStrategy) -> None:
        if strategy in self._strategies:
            self._active_strategy = strategy

    def register_callback(self, callback: ActivityCallback) -> None:
        with self._callback_lock:
            if callback not in self._callbacks:
                self._callbacks.append(callback)

    def unregister_callback(self, callback: ActivityCallback) -> None:
        with self._callback_lock:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

    def _notify_callbacks(self, has_activity: bool, metrics: AudioMetrics) -> None:
        with self._callback_lock:
            callbacks = list(self._callbacks)
        for callback in callbacks:
            try:
                callback(has_activity, metrics)
            except Exception:
                pass

    def analyze(self, audio_data: bytes, sample_width: int = 2) -> AudioMetrics:
        strategy = self._strategies[self._active_strategy]
        metrics = strategy.detect(audio_data, sample_width, self._config)
        self._metrics_history.append(metrics)
        self._update_activity_state(metrics)
        return metrics

    def analyze_audio_data(self, audio: sr.AudioData) -> AudioMetrics:
        try:
            raw_data = audio.get_raw_data(convert_rate=16000, convert_width=2)
            strategy = self._strategies[DetectionStrategy.WINDOWED_PEAK]
            metrics = strategy.detect(raw_data, 2, self._config)
            self._metrics_history.append(metrics)
            self._update_activity_state(metrics)
            return metrics
        except Exception:
            return AudioMetrics()

    def _update_activity_state(self, metrics: AudioMetrics) -> None:
        previous_state = self._current_activity_state

        if metrics.has_activity:
            self._current_activity_state = True
            self._frames_since_activity = 0
        else:
            self._frames_since_activity += 1
            if self._frames_since_activity >= self._config.grace_frames:
                self._current_activity_state = False

        if self._current_activity_state != previous_state:
            self._notify_callbacks(self._current_activity_state, metrics)

    def is_silence(self, rms: float) -> bool:
        return rms < self._config.silence_rms_threshold

    @property
    def has_activity(self) -> bool:
        return self._current_activity_state

    @property
    def config(self) -> ThresholdConfig:
        return self._config

    @property
    def smoothed_amplitude(self) -> float:
        return self._smoothed_amplitude

    def smooth_amplitude(
        self, target: float, attack_rate: float = 0.7, decay_rate: float = 0.3
    ) -> float:
        if target > self._smoothed_amplitude:
            self._smoothed_amplitude = (
                self._smoothed_amplitude * (1 - attack_rate) + target * attack_rate
            )
        else:
            self._smoothed_amplitude = (
                self._smoothed_amplitude * (1 - decay_rate) + target * decay_rate
            )
        return self._smoothed_amplitude

    def get_recent_average_db(self, samples: int = 10) -> float:
        if not self._metrics_history:
            return -100.0
        recent = list(self._metrics_history)[-samples:]
        if not recent:
            return -100.0
        return sum(m.db_level for m in recent) / len(recent)

    def detect_voice(
        self, audio_data: bytes, sample_width: int = 2, sample_rate: int = 16000
    ) -> bool:
        """Detect if audio contains human voice using WebRTC VAD.

        This is more reliable than amplitude thresholds for distinguishing
        speech from ambient noise (fans, traffic, etc.).

        Args:
            audio_data: Raw audio bytes
            sample_width: Bytes per sample (usually 2 for 16-bit audio)
            sample_rate: Sample rate in Hz (will be resampled to 16000 if needed)

        Returns:
            True if voice is detected, False otherwise
        """
        if self._webrtc_vad is None:
            metrics = self.analyze(audio_data, sample_width)
            return metrics.has_activity

        try:
            # Convert to 16-bit if needed
            if sample_width != 2:
                audio_data = audioop.lin2lin(audio_data, sample_width, 2)

            frame_duration_ms = 30
            bytes_per_frame = int(sample_rate * 2 * frame_duration_ms / 1000)

            speech_frames = 0
            total_frames = 0

            for i in range(0, len(audio_data) - bytes_per_frame, bytes_per_frame):
                frame = audio_data[i : i + bytes_per_frame]
                if len(frame) == bytes_per_frame:
                    try:
                        if self._webrtc_vad._vad.is_speech(frame, sample_rate):
                            speech_frames += 1
                        total_frames += 1
                    except Exception:
                        pass

            if total_frames == 0:
                return False

            return speech_frames >= 2
        except Exception:
            metrics = self.analyze(audio_data, sample_width)
            return metrics.has_activity

    def detect_voice_in_audio_data(self, audio: sr.AudioData) -> bool:
        """Detect if AudioData contains human voice using WebRTC VAD.

        Args:
            audio: speech_recognition AudioData object

        Returns:
            True if voice is detected, False otherwise
        """
        if self._webrtc_vad is not None:
            return self._webrtc_vad.detect_voice_in_audio(audio)

        metrics = self.analyze_audio_data(audio)
        return metrics.has_activity


def get_audio_activity_detector() -> AudioActivityDetector:
    return AudioActivityDetector.get_instance()
