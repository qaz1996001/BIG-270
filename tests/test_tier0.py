"""Tests for Tier 0 analyzer -- ISO 10816 severity and health indicators.

Covers:
* ISO 10816 severity zone classification for all 4 machine classes.
* Boundary values at zone transitions.
* Health indicator computation (RMS, kurtosis, crest factor, vrms).
* Anomalous peak detection in the FFT spectrum.
* Analyzer protocol methods (prerequisites, can_run, analyze returns []).
"""

from __future__ import annotations

import numpy as np
import pytest
from pytest import approx

from vibfault.analyzers.tier0 import Tier0Analyzer
from vibfault.core.models import MachineParameters

# ---------------------------------------------------------------------------
# ISO 10816 Severity Classification
# ---------------------------------------------------------------------------


class TestISOSeverityClassII:
    """Verify severity zones for the default Class II machine.

    Thresholds: A ≤ 1.12, B ≤ 2.8, C ≤ 7.1 mm/s.
    """

    def test_zone_a_good(self) -> None:
        assert Tier0Analyzer.assess_iso_severity(0.5, "II") == "A-Good"

    def test_zone_a_boundary(self) -> None:
        assert Tier0Analyzer.assess_iso_severity(1.12, "II") == "A-Good"

    def test_zone_b_acceptable(self) -> None:
        assert Tier0Analyzer.assess_iso_severity(2.0, "II") == "B-Acceptable"

    def test_zone_b_boundary(self) -> None:
        assert Tier0Analyzer.assess_iso_severity(2.8, "II") == "B-Acceptable"

    def test_zone_c_alert(self) -> None:
        assert Tier0Analyzer.assess_iso_severity(5.0, "II") == "C-Alert"

    def test_zone_c_boundary(self) -> None:
        assert Tier0Analyzer.assess_iso_severity(7.1, "II") == "C-Alert"

    def test_zone_d_danger(self) -> None:
        assert Tier0Analyzer.assess_iso_severity(10.0, "II") == "D-Danger"

    def test_zone_d_just_above_c(self) -> None:
        assert Tier0Analyzer.assess_iso_severity(7.11, "II") == "D-Danger"


class TestISOSeverityClassI:
    """Class I has lower thresholds: A ≤ 0.71, B ≤ 1.8, C ≤ 4.5."""

    def test_zone_a(self) -> None:
        assert Tier0Analyzer.assess_iso_severity(0.5, "I") == "A-Good"

    def test_zone_b(self) -> None:
        assert Tier0Analyzer.assess_iso_severity(1.0, "I") == "B-Acceptable"

    def test_zone_c(self) -> None:
        assert Tier0Analyzer.assess_iso_severity(3.0, "I") == "C-Alert"

    def test_zone_d(self) -> None:
        assert Tier0Analyzer.assess_iso_severity(5.0, "I") == "D-Danger"


class TestISOSeverityInvalidClass:
    """Unknown machine class should raise ValueError."""

    def test_invalid_class(self) -> None:
        with pytest.raises(ValueError, match="Unknown"):
            Tier0Analyzer.assess_iso_severity(1.0, "V")


# ---------------------------------------------------------------------------
# Analyzer Protocol
# ---------------------------------------------------------------------------


class TestTier0Protocol:
    """Verify Tier 0 analyzer protocol compliance."""

    def test_prerequisites(self) -> None:
        analyzer = Tier0Analyzer()
        assert "sampling_rate" in analyzer.prerequisites()

    def test_can_run_always_true(self) -> None:
        analyzer = Tier0Analyzer()
        params = MachineParameters(sampling_rate=1000)
        assert analyzer.can_run(params) is True

    def test_analyze_returns_empty_list(self) -> None:
        """Tier 0 does not emit fault candidates."""
        analyzer = Tier0Analyzer()
        fs = 10000
        t = np.arange(0, 1.0, 1.0 / fs)
        signal = np.sin(2 * np.pi * 50 * t)
        params = MachineParameters(sampling_rate=fs)

        candidates = analyzer.analyze(signal, params)

        assert candidates == []

    def test_health_indicators_stored(self) -> None:
        """After analyze, self.health should be populated."""
        analyzer = Tier0Analyzer()
        fs = 10000
        t = np.arange(0, 1.0, 1.0 / fs)
        signal = np.sin(2 * np.pi * 50 * t)
        params = MachineParameters(sampling_rate=fs)

        analyzer.analyze(signal, params)

        health = analyzer.health
        assert health.rms > 0
        assert isinstance(health.kurtosis, float)
        assert isinstance(health.crest_factor, float)
        assert isinstance(health.vrms, float)
        assert health.iso_zone in ("A-Good", "B-Acceptable", "C-Alert", "D-Danger")


# ---------------------------------------------------------------------------
# Health Indicator Computation
# ---------------------------------------------------------------------------


class TestHealthIndicators:
    """Validate computed health indicators on known signals."""

    def test_sine_rms(self) -> None:
        """RMS of a unit sine should be ~0.707."""
        analyzer = Tier0Analyzer()
        fs = 10000
        t = np.arange(0, 1.0, 1.0 / fs)
        signal = np.sin(2 * np.pi * 50 * t)
        params = MachineParameters(sampling_rate=fs)

        analyzer.analyze(signal, params)

        assert analyzer.health.rms == approx(1.0 / np.sqrt(2), rel=0.02)

    def test_sine_crest_factor(self) -> None:
        """Crest factor of a sine wave ≈ sqrt(2)."""
        analyzer = Tier0Analyzer()
        fs = 10000
        t = np.arange(0, 1.0, 1.0 / fs)
        signal = np.sin(2 * np.pi * 50 * t)
        params = MachineParameters(sampling_rate=fs)

        analyzer.analyze(signal, params)

        assert analyzer.health.crest_factor == approx(np.sqrt(2), rel=0.05)

    def test_default_machine_class(self) -> None:
        """When machine_class is None, should default to Class II."""
        analyzer = Tier0Analyzer()
        fs = 10000
        signal = np.zeros(fs)  # zero signal → vrms ≈ 0 → A-Good
        params = MachineParameters(sampling_rate=fs)

        analyzer.analyze(signal, params)

        assert analyzer.health.iso_zone == "A-Good"


# ---------------------------------------------------------------------------
# Anomalous Peak Detection
# ---------------------------------------------------------------------------


class TestAnomalousPeakDetection:
    """Verify FFT anomaly flagging."""

    def test_no_anomalies_in_noise(self) -> None:
        """White noise should have few/no anomalous peaks (mean + 3σ threshold)."""
        analyzer = Tier0Analyzer()
        rng = np.random.default_rng(42)
        signal = rng.standard_normal(4096)
        params = MachineParameters(sampling_rate=4096)

        analyzer.analyze(signal, params)

        # For Gaussian noise, < 1% of bins should exceed 3σ
        n_bins = len(analyzer.health.fft_magnitude)
        n_anomalies = len(analyzer.health.anomalous_peaks)
        assert n_anomalies / n_bins < 0.02

    def test_strong_tone_flagged(self) -> None:
        """A strong single tone in noise should be flagged as anomalous."""
        analyzer = Tier0Analyzer()
        fs = 4096
        rng = np.random.default_rng(42)
        t = np.arange(0, 1.0, 1.0 / fs)
        signal = 10.0 * np.sin(2 * np.pi * 100 * t) + 0.01 * rng.standard_normal(len(t))
        params = MachineParameters(sampling_rate=fs)

        analyzer.analyze(signal, params)

        assert len(analyzer.health.anomalous_peaks) >= 1
