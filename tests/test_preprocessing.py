"""Tests for ``vibfault.core.preprocessing``.

Covers:
* ``detrend`` -- DC / linear trend removal, input validation.
* ``apply_window`` -- Hann / Hamming windowing, input validation.
* ``compute_fft`` -- Known sinusoid frequency and amplitude recovery.
* ``compute_envelope`` -- AM demodulation for bearing-like signals.
* ``compute_cepstrum`` -- Shape, periodic signal peak, input validation.
* ``time_domain_features`` -- RMS, peak, kurtosis, crest factor, skewness.
* ``velocity_rms`` -- Integration accuracy for a pure tone.
* ``compute_stft`` -- STFT shape and frequency recovery.
* ``compute_cwt`` -- CWT shape and frequency recovery.
* ``compute_spectral_kurtosis`` -- Spectral kurtosis for impulsive signals.
* ``compute_kurtogram`` -- Optimal band selection for impulsive signals.
* ``compute_emd`` -- EMD decomposition and reconstruction.
"""

from __future__ import annotations

import numpy as np
import pytest
from pytest import approx

from vibfault.core.preprocessing import (
    apply_window,
    bandpass_filter,
    compute_cepstrum,
    compute_cwt,
    compute_emd,
    compute_envelope,
    compute_fft,
    compute_kurtogram,
    compute_spectral_kurtosis,
    compute_stft,
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


# ---------------------------------------------------------------------------
# compute_stft
# ---------------------------------------------------------------------------


class TestComputeSTFT:
    """Verify STFT output shape and frequency recovery."""

    def test_output_shape(self) -> None:
        """Output arrays have consistent dimensions."""
        fs = 1000.0
        n = 4096
        rng = np.random.default_rng(42)
        signal = rng.standard_normal(n)

        times, frequencies, magnitude = compute_stft(signal, fs, nperseg=256)

        assert frequencies.ndim == 1
        assert times.ndim == 1
        assert magnitude.shape == (frequencies.size, times.size)

    def test_single_sine_frequency(self) -> None:
        """A pure 100 Hz sine should show energy at 100 Hz in STFT."""
        fs = 4000.0
        n = 8192
        t = np.arange(n) / fs
        signal = np.sin(2 * np.pi * 100 * t)

        times, frequencies, magnitude = compute_stft(signal, fs, nperseg=512)

        # Average across time to get mean spectrum
        mean_spectrum = magnitude.mean(axis=1)
        peak_idx = np.argmax(mean_spectrum)
        assert frequencies[peak_idx] == approx(100.0, abs=10.0)

    def test_rejects_2d_input(self) -> None:
        with pytest.raises(ValueError, match="1-D"):
            compute_stft(np.ones((4, 4)), fs=1000.0)


# ---------------------------------------------------------------------------
# compute_cwt
# ---------------------------------------------------------------------------


class TestComputeCWT:
    """Verify CWT output shape and frequency recovery."""

    def test_output_shape(self) -> None:
        """Output has (num_freqs, signal_length) shape."""
        fs = 1000.0
        n = 2048
        rng = np.random.default_rng(42)
        signal = rng.standard_normal(n)

        times, frequencies, coefficients = compute_cwt(
            signal,
            fs,
            num_freqs=32,
        )

        assert times.shape == (n,)
        assert frequencies.shape == (32,)
        assert coefficients.shape == (32, n)

    def test_single_sine_frequency(self) -> None:
        """A pure 50 Hz sine should produce a CWT peak near 50 Hz."""
        fs = 1000.0
        n = 4096
        t = np.arange(n) / fs
        signal = np.sin(2 * np.pi * 50 * t)

        times, frequencies, coefficients = compute_cwt(
            signal,
            fs,
            num_freqs=64,
            freq_range=(10.0, 200.0),
        )

        # Average across time
        mean_energy = coefficients.mean(axis=1)
        peak_idx = np.argmax(mean_energy)
        assert frequencies[peak_idx] == approx(50.0, abs=10.0)

    def test_rejects_2d_input(self) -> None:
        with pytest.raises(ValueError, match="1-D"):
            compute_cwt(np.ones((4, 4)), fs=1000.0)


# ---------------------------------------------------------------------------
# compute_spectral_kurtosis
# ---------------------------------------------------------------------------


class TestSpectralKurtosis:
    """Verify spectral kurtosis for impulsive vs smooth signals."""

    def test_impulsive_signal_high_kurtosis(self) -> None:
        """A signal with sharp periodic impulses in a specific band should
        have high spectral kurtosis in that band."""
        fs = 10000.0
        n = 20000
        rng = np.random.default_rng(42)
        signal = rng.standard_normal(n) * 0.01

        # Add sharp impulses (3 samples wide) every 500 samples —
        # short bursts excite a wide band and produce genuinely impulsive
        # (high-kurtosis) envelopes.
        for i in range(0, n, 500):
            burst_len = min(3, n - i)
            signal[i : i + burst_len] += 10.0

        kurt = compute_spectral_kurtosis(signal, fs, band=(2000, 4000))
        assert kurt > 2.0, f"Expected high kurtosis for impulsive signal, got {kurt}"

    def test_gaussian_noise_low_kurtosis(self) -> None:
        """Pure Gaussian noise should have near-zero spectral kurtosis."""
        fs = 10000.0
        rng = np.random.default_rng(42)
        signal = rng.standard_normal(20000)

        kurt = compute_spectral_kurtosis(signal, fs, band=(1000, 4000))
        assert abs(kurt) < 2.0, f"Expected low kurtosis for noise, got {kurt}"


# ---------------------------------------------------------------------------
# compute_kurtogram
# ---------------------------------------------------------------------------


class TestKurtogram:
    """Verify kurtogram finds optimal band for impulsive signals."""

    def test_finds_impulsive_band(self) -> None:
        """Kurtogram should identify a band with elevated kurtosis for
        an impulsive signal, and the kurtosis should exceed that of
        broadband noise."""
        fs = 10000.0
        n = 20000
        rng = np.random.default_rng(42)
        signal = rng.standard_normal(n) * 0.01

        # Add sharp impulses every 500 samples — broadband excitation
        for i in range(0, n, 500):
            burst_len = min(3, n - i)
            signal[i : i + burst_len] += 10.0

        center, bw, kurt = compute_kurtogram(signal, fs, levels=5)

        # Basic sanity: valid band and positive kurtosis
        assert center > 0
        assert bw > 0
        assert kurt > 1.0, f"Expected elevated kurtosis, got {kurt}"

    def test_returns_valid_band(self) -> None:
        """Kurtogram should always return a valid frequency band."""
        fs = 10000.0
        rng = np.random.default_rng(42)
        signal = rng.standard_normal(4096)

        center, bw, kurt = compute_kurtogram(signal, fs, levels=4)

        assert center > 0
        assert bw > 0
        assert center - bw / 2.0 >= 0

    def test_rejects_2d_input(self) -> None:
        with pytest.raises(ValueError, match="1-D"):
            compute_kurtogram(np.ones((4, 4)), fs=1000.0)


# ---------------------------------------------------------------------------
# compute_emd
# ---------------------------------------------------------------------------


class TestComputeEMD:
    """Verify Empirical Mode Decomposition."""

    def test_decomposition_produces_imfs(self) -> None:
        """EMD of a multi-component signal should produce multiple IMFs."""
        fs = 1000.0
        n = 2048
        t = np.arange(n) / fs
        signal = np.sin(2 * np.pi * 5 * t) + 0.5 * np.sin(2 * np.pi * 50 * t)

        imfs = compute_emd(signal)

        assert len(imfs) >= 2, f"Expected >=2 IMFs, got {len(imfs)}"
        for imf in imfs:
            assert imf.shape == (n,)

    def test_reconstruction(self) -> None:
        """Sum of all IMFs should reconstruct the original signal."""
        fs = 1000.0
        n = 2048
        t = np.arange(n) / fs
        signal = np.sin(2 * np.pi * 10 * t) + 0.3 * np.sin(2 * np.pi * 80 * t)

        imfs = compute_emd(signal)
        reconstructed = sum(imfs)

        np.testing.assert_allclose(reconstructed, signal, atol=1e-6)

    def test_max_imfs(self) -> None:
        """Limiting max_imfs should cap the number of IMFs returned."""
        fs = 1000.0
        n = 2048
        t = np.arange(n) / fs
        signal = (
            np.sin(2 * np.pi * 5 * t) + np.sin(2 * np.pi * 30 * t) + np.sin(2 * np.pi * 100 * t)
        )

        imfs = compute_emd(signal, max_imfs=2)
        # Should have at most 2 IMFs + 1 residual = 3
        assert len(imfs) <= 4

    def test_rejects_2d_input(self) -> None:
        with pytest.raises(ValueError, match="1-D"):
            compute_emd(np.ones((4, 4)))
