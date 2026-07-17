import numpy as np
import pytest

from src.audio_capture import AudioCapture


def _pcm(values):
    return np.array(values, dtype=np.int16).tobytes()


def test_rms_empty_is_zero():
    assert AudioCapture()._calculate_rms(b"") == 0.0


def test_rms_silence_is_zero():
    assert AudioCapture()._calculate_rms(_pcm([0, 0, 0, 0])) == 0.0


def test_rms_full_scale_is_one():
    data = _pcm([16384, -16384, 16384, -16384])
    assert AudioCapture()._calculate_rms(data) == pytest.approx(1.0)


def test_rms_half_scale():
    assert AudioCapture()._calculate_rms(_pcm([8192, -8192])) == pytest.approx(0.5)


def test_bar_values_silence_all_zero():
    out = AudioCapture()._calculate_bar_values(_pcm([0] * 1024))
    assert len(out) == 32
    assert all(v == 0.0 for v in out)


def test_bar_values_loud_last_is_positive():
    out = AudioCapture()._calculate_bar_values(_pcm([20000, -20000] * 512))
    assert len(out) == 32
    assert out[-1] > 0.0
