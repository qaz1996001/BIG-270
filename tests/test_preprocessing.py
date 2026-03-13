"""Tests for cepstrum analysis in ``vibfault.core.preprocessing``.

Covers ``compute_cepstrum``:

* Output shape matches input length.
* Periodic signal produces a cepstral peak at the expected quefrency.
* Non-1-D input raises ``ValueError``.
"""

import numpy as np
import pytest
from pytest import approx

from vibfault.core.preprocessing import compute_cepstrum

# ---------------------------------------------------------------------------
# Shape validation
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


# ---------------------------------------------------------------------------
# Periodic signal detection
# ---------------------------------------------------------------------------


class TestCepstrumPeriodicSignal:
    """A signal with harmonically related sines should produce a cepstral
    peak at the quefrency corresponding to the fundamental period."""

    def test_cepstrum_periodic_signal(self) -> None:
        fs = 10000.0
        n = 8192
        t = np.arange(n) / fs

        # Two harmonically related sines: 100 Hz and 200 Hz.
        # The harmonic spacing is 100 Hz -> period = 0.01 s.
        signal = np.sin(2 * np.pi * 100 * t) + 0.5 * np.sin(2 * np.pi * 200 * t)

        quefrency, cepstrum = compute_cepstrum(signal, fs)

        # Verify quefrency axis: q = np.arange(n) / fs
        expected_quefrency = np.arange(n) / fs
        np.testing.assert_array_almost_equal(quefrency, expected_quefrency)

        # The cepstrum should show a peak near quefrency = 1/100 = 0.01 s.
        # Search in a window around 0.01 s (exclude the very first samples
        # which carry the spectral power / DC information).
        target_quefrency = 0.01  # seconds
        search_low = target_quefrency * 0.8
        search_high = target_quefrency * 1.2
        mask = (quefrency >= search_low) & (quefrency <= search_high)
        peak_idx = np.argmax(np.abs(cepstrum[mask]))
        peak_quefrency = quefrency[mask][peak_idx]

        # Peak should be within a few quefrency bins of 0.01 s.
        # Spectral leakage can shift the peak by 1-2 bins, so allow 3 bins.
        quefrency_resolution = 1.0 / fs
        assert peak_quefrency == approx(target_quefrency, abs=3 * quefrency_resolution)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


class TestCepstrum1DValidation:
    """Passing a non-1-D array should raise ValueError."""

    def test_cepstrum_1d_validation(self) -> None:
        signal_2d = np.ones((4, 4))
        with pytest.raises(ValueError, match="1-D"):
            compute_cepstrum(signal_2d, fs=1000.0)
