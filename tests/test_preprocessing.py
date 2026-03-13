"""Tests for ``vibfault.core.preprocessing``.

Covers:
* ``detrend`` -- DC / linear trend removal, input validation.
* ``apply_window`` -- Hann / Hamming windowing, input validation.
* ``compute_fft`` -- Known sinusoid frequency and amplitude recovery.
* ``compute_envelope`` -- AM demodulation for bearing-like signals.
* ``compute_cepstrum`` -- Shape, periodic signal peak, input validation.
* ``time_domain_features`` -- RMS, peak, kurtosis, crest factor, skewness.
* ``velocity_rms`` -- Integration accuracy for a pure tone.
"""

from __future__ import annotations

import numpy as np
import pytest
from pytest import approx

from vibfault.core.preprocessing import (
    apply_window,
    bandpass_filter,
    compute_cepstrum,
    compute_envelope,
    compute_fft,
    detrend,
    time_domain_features,
    velocity_rms,
)

# ---------------------------------------------------------------------------
# detrend
# ---------------------------------------------------------------------------


class TestDetrend:
    """Verify DC offset and linear trend removal."""

    def test_removes_dc_offset(self) -> None:
        signal = np.ones(1024) * 5.0
        result = detrend(signal)
        assert np.abs(np.mean(result)) < 1e-10

    def test_removes_linear_trend(self) -> None:
        t = np.linspace(0, 1, 1024)
        signal = 3.0 * t + 2.0  # y = 3t + 2
        result = detrend(signal)
        assert np.abs(np.mean(result)) < 1e-10
        assert np.std(result) < 1e-10

    def test_preserves_oscillation(self) -> None:
        t = np.linspace(0, 1, 4096)
        pure_sine = np.sin(2 * np.pi * 10 * t)
        signal = pure_sine + 5.0 + 2.0 * t  # sine + DC + trend
        result = detrend(signal)
        # The sine component should remain
        assert np.std(result) > 0.5

    def test_rejects_2d_input(self) -> None:
        with pytest.raises(ValueError, match="1-D"):
            detrend(np.ones((4, 4)))


# ---------------------------------------------------------------------------
# apply_window
# ---------------------------------------------------------------------------


class TestApplyWindow:
    """Verify windowing functions."""

    def test_hann_window_zeros_endpoints(self) -> None:
        signal = np.ones(1024)
        windowed = apply_window(signal, window="hann")
        assert windowed[0] == approx(0.0, abs=1e-10)
        assert windowed[-1] == approx(0.0, abs=1e-10)

    def test_hann_window_peaks_at_center(self) -> None:
        signal = np.ones(1024)
        windowed = apply_window(signal, window="hann")
        center = len(signal) // 2
        assert windowed[center] > 0.9

    def test_hamming_window(self) -> None:
        signal = np.ones(256)
        windowed = apply_window(signal, window="hamming")
        # Hamming window endpoints are ~0.08, not zero
        assert windowed[0] > 0.05
        assert windowed[0] < 0.15

    def test_rejects_2d_input(self) -> None:
        with pytest.raises(ValueError, match="1-D"):
            apply_window(np.ones((4, 4)))


# ---------------------------------------------------------------------------
# bandpass_filter
# ---------------------------------------------------------------------------


class TestBandpassFilter:
    """Verify bandpass filter edge cases and validation."""

    def test_rejects_low_ge_high(self) -> None:
        signal = np.ones(1024)
        with pytest.raises(ValueError, match="low"):
            bandpass_filter(signal, fs=1000, low=500, high=100)

    def test_rejects_high_above_nyquist(self) -> None:
        signal = np.ones(1024)
        with pytest.raises(ValueError, match="Nyquist"):
            bandpass_filter(signal, fs=1000, low=10, high=600)

    def test_rejects_negative_low(self) -> None:
        signal = np.ones(1024)
        with pytest.raises(ValueError, match="positive"):
            bandpass_filter(signal, fs=1000, low=-10, high=100)

    def test_passes_in_band_signal(self) -> None:
        fs = 10000
        t = np.arange(0, 1.0, 1.0 / fs)
        # 200 Hz signal is in-band for [100, 500]
        signal = np.sin(2 * np.pi * 200 * t)
        filtered = bandpass_filter(signal, fs=fs, low=100, high=500)
        # In-band signal should be largely preserved
        assert np.std(filtered) > 0.5


# ---------------------------------------------------------------------------
# compute_fft
# ---------------------------------------------------------------------------


class TestComputeFFT:
    """Known-sinusoid recovery from FFT amplitude spectrum."""

    def test_single_sine_frequency(self) -> None:
        """A pure 100 Hz sine at amplitude 1.0 should produce a peak at 100 Hz."""
        fs = 10000.0
        n = 10000  # exactly 1 second → freq resolution = 1 Hz
        t = np.arange(n) / fs
        signal = 1.0 * np.sin(2 * np.pi * 100 * t)

        freqs, amps = compute_fft(signal, fs)
        peak_idx = np.argmax(amps)
        assert freqs[peak_idx] == approx(100.0, abs=1.0)
        assert amps[peak_idx] == approx(1.0, rel=0.05)

    def test_two_sines(self) -> None:
        """Two sines at different frequencies should produce two peaks."""
        fs = 10000.0
        n = 10000
        t = np.arange(n) / fs
        signal = 2.0 * np.sin(2 * np.pi * 50 * t) + 0.5 * np.sin(2 * np.pi * 200 * t)

        freqs, amps = compute_fft(signal, fs)

        # Check peak near 50 Hz
        mask_50 = (freqs >= 49) & (freqs <= 51)
        assert np.max(amps[mask_50]) == approx(2.0, rel=0.05)

        # Check peak near 200 Hz
        mask_200 = (freqs >= 199) & (freqs <= 201)
        assert np.max(amps[mask_200]) == approx(0.5, rel=0.05)

    def test_dc_component(self) -> None:
        """A constant signal should have amplitude at DC only."""
        fs = 1000.0
        n = 1000
        signal = np.ones(n) * 3.0

        freqs, amps = compute_fft(signal, fs)
        assert amps[0] == approx(3.0, rel=0.01)
        # Non-DC bins should be negligible
        assert np.max(amps[1:]) < 1e-10

    def test_rejects_2d_input(self) -> None:
        with pytest.raises(ValueError, match="1-D"):
            compute_fft(np.ones((4, 4)), fs=1000.0)


# ---------------------------------------------------------------------------
# compute_envelope
# ---------------------------------------------------------------------------


class TestComputeEnvelope:
    """Verify envelope (demodulation) analysis on AM signals."""

    def test_am_signal_demodulation(self) -> None:
        """An AM signal modulated at 50 Hz should show a 50 Hz envelope peak."""
        fs = 10000.0
        n = 20000  # 2 seconds
        t = np.arange(n) / fs

        carrier = np.cos(2 * np.pi * 3000 * t)
        modulation = 0.8 * np.cos(2 * np.pi * 50 * t)
        signal = carrier * (1.0 + modulation)

        env_freqs, env_amps = compute_envelope(signal, fs)

        # Find peak near 50 Hz in envelope spectrum
        mask = (env_freqs >= 48) & (env_freqs <= 52)
        assert np.max(env_amps[mask]) > 0.1, (
            "Expected significant peak at 50 Hz in envelope spectrum"
        )

    def test_envelope_with_bandpass(self) -> None:
        """Envelope with bandpass should isolate the resonance band."""
        fs = 10000.0
        n = 20000
        t = np.arange(n) / fs

        carrier = np.cos(2 * np.pi * 3000 * t)
        modulation = 0.5 * np.cos(2 * np.pi * 100 * t)
        signal = carrier * (1.0 + modulation)

        env_freqs, env_amps = compute_envelope(signal, fs, band=(2000, 4000))

        mask = (env_freqs >= 98) & (env_freqs <= 102)
        assert np.max(env_amps[mask]) > 0.05


# ---------------------------------------------------------------------------
# compute_cepstrum
# ---------------------------------------------------------------------------


class TestCepstrumShape:
    """Output arrays must have the same length as the input signal."""

    def test_cepstrum_shape(self) -> None:
        n = 1024
        fs = 1000.0
        rng = np.random.default_rng(42)
        signal = rng.standard_normal(n)

        quefrency, cepstrum = compute_cepstrum(signal, fs)

        assert quefrency.shape == (n,)
        assert cepstrum.shape == (n,)


class TestCepstrumPeriodicSignal:
    """A signal with harmonically related sines should produce a cepstral
    peak at the quefrency corresponding to the fundamental period."""

    def test_cepstrum_periodic_signal(self) -> None:
        fs = 10000.0
        n = 8192
        t = np.arange(n) / fs

        signal = np.sin(2 * np.pi * 100 * t) + 0.5 * np.sin(2 * np.pi * 200 * t)

        quefrency, cepstrum = compute_cepstrum(signal, fs)

        expected_quefrency = np.arange(n) / fs
        np.testing.assert_array_almost_equal(quefrency, expected_quefrency)

        target_quefrency = 0.01  # 1/100 Hz
        search_low = target_quefrency * 0.8
        search_high = target_quefrency * 1.2
        mask = (quefrency >= search_low) & (quefrency <= search_high)
        peak_idx = np.argmax(np.abs(cepstrum[mask]))
        peak_quefrency = quefrency[mask][peak_idx]

        quefrency_resolution = 1.0 / fs
        assert peak_quefrency == approx(target_quefrency, abs=3 * quefrency_resolution)


class TestCepstrum1DValidation:
    """Passing a non-1-D array should raise ValueError."""

    def test_cepstrum_1d_validation(self) -> None:
        signal_2d = np.ones((4, 4))
        with pytest.raises(ValueError, match="1-D"):
            compute_cepstrum(signal_2d, fs=1000.0)


# ---------------------------------------------------------------------------
# time_domain_features
# ---------------------------------------------------------------------------


class TestTimeDomainFeatures:
    """Validate statistical feature calculations."""

    def test_pure_sine_rms(self) -> None:
        """RMS of sin(t) over full cycles is 1/sqrt(2) ≈ 0.7071."""
        t = np.linspace(0, 1, 10000, endpoint=False)
        signal = np.sin(2 * np.pi * 10 * t)  # 10 full cycles
        features = time_domain_features(signal)
        assert features["rms"] == approx(1.0 / np.sqrt(2), rel=0.01)

    def test_peak_value(self) -> None:
        t = np.linspace(0, 1, 10000, endpoint=False)
        signal = 3.0 * np.sin(2 * np.pi * 5 * t)
        features = time_domain_features(signal)
        assert features["peak"] == approx(3.0, rel=0.01)

    def test_peak_to_peak(self) -> None:
        t = np.linspace(0, 1, 10000, endpoint=False)
        signal = 2.0 * np.sin(2 * np.pi * 5 * t)
        features = time_domain_features(signal)
        assert features["peak_to_peak"] == approx(4.0, rel=0.01)

    def test_crest_factor_sine(self) -> None:
        """Crest factor of a sine wave is sqrt(2) ≈ 1.414."""
        t = np.linspace(0, 1, 10000, endpoint=False)
        signal = np.sin(2 * np.pi * 10 * t)
        features = time_domain_features(signal)
        assert features["crest_factor"] == approx(np.sqrt(2), rel=0.02)

    def test_kurtosis_gaussian(self) -> None:
        """Excess kurtosis of Gaussian noise should be near 0."""
        rng = np.random.default_rng(42)
        signal = rng.standard_normal(100000)
        features = time_domain_features(signal)
        assert features["kurtosis"] == approx(0.0, abs=0.1)

    def test_kurtosis_sine(self) -> None:
        """Excess kurtosis of a sine wave is -1.5."""
        t = np.linspace(0, 1, 10000, endpoint=False)
        signal = np.sin(2 * np.pi * 10 * t)
        features = time_domain_features(signal)
        assert features["kurtosis"] == approx(-1.5, abs=0.05)

    def test_skewness_symmetric(self) -> None:
        """Skewness of a symmetric signal should be near 0."""
        t = np.linspace(0, 1, 10000, endpoint=False)
        signal = np.sin(2 * np.pi * 10 * t)
        features = time_domain_features(signal)
        assert features["skewness"] == approx(0.0, abs=0.05)


# ---------------------------------------------------------------------------
# velocity_rms
# ---------------------------------------------------------------------------


class TestVelocityRMS:
    """Validate acceleration-to-velocity integration."""

    def test_pure_tone_integration(self) -> None:
        """A single-frequency acceleration signal should integrate to known
        velocity amplitude.

        If a(t) = A * sin(2*pi*f*t), then v(t) = -A/(2*pi*f) * cos(2*pi*f*t).
        v_rms = A / (2*pi*f) / sqrt(2), in m/s. Multiply by 1000 for mm/s.
        """
        fs = 10000.0
        n = 10000
        f = 50.0  # Hz
        amp = 1.0  # m/s^2
        t = np.arange(n) / fs

        signal = amp * np.sin(2 * np.pi * f * t)
        v_rms = velocity_rms(signal, fs)

        expected_v_rms_ms = amp / (2 * np.pi * f * np.sqrt(2))
        expected_v_rms_mms = expected_v_rms_ms * 1000.0

        assert v_rms == approx(expected_v_rms_mms, rel=0.05)

    def test_zero_signal_returns_zero(self) -> None:
        signal = np.zeros(1024)
        assert velocity_rms(signal, fs=1000.0) == approx(0.0, abs=1e-10)
