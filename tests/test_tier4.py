"""Tests for Tier 4 gear fault analyzer.

Covers five gear fault types using synthetic signals:

* Fault #16: Gear Misalignment -- GMF + 2xGMF + asymmetric sidebands
* Fault #17: Broken Tooth -- impulsive signal (kurtosis>4), GMF harmonics, cepstrum rahmonic
* Fault #18: Gear Eccentricity -- GMF +/- 1X symmetric sidebands + 1X elevated
* Fault #19: Gear Shaft Bend -- 1X + 2X elevated + GMF +/- 1X sidebands
* Fault #20: Gear Wear -- broadband around GMF + >=3 GMF harmonics

Also tests that ``can_run()`` correctly rejects incomplete parameters.
"""

from __future__ import annotations

import numpy as np

from vibfault.analyzers.tier4 import Tier4Analyzer
from vibfault.core.models import MachineParameters
from vibfault.core.preprocessing import bandpass_filter

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

FS = 8192  # sampling rate (Hz)
DURATION = 2.0  # seconds
RPM = 1800
SHAFT_FREQ = RPM / 60.0  # 30 Hz
TEETH_DRIVE = 20
TEETH_DRIVEN = 40
GMF = TEETH_DRIVE * SHAFT_FREQ  # 600 Hz


def _make_params() -> MachineParameters:
    """Create standard Tier 4 machine parameters."""
    return MachineParameters(
        sampling_rate=FS,
        rpm=RPM,
        gear_teeth_drive=TEETH_DRIVE,
        gear_teeth_driven=TEETH_DRIVEN,
    )


def _time_axis() -> np.ndarray:
    """Return a 2-second time vector at 8192 Hz."""
    return np.arange(0, DURATION, 1.0 / FS)


# ---------------------------------------------------------------------------
# Test: Fault #16 -- Gear Misalignment
# ---------------------------------------------------------------------------


class TestGearMisalignment:
    """Fault #16: GMF + 2xGMF + asymmetric sidebands around GMF."""

    def test_gear_misalignment(self) -> None:
        rng = np.random.default_rng(42)
        t = _time_axis()

        # GMF (600 Hz) and 2xGMF (1200 Hz)
        signal = np.sin(2 * np.pi * GMF * t)
        signal += 0.5 * np.sin(2 * np.pi * 2 * GMF * t)

        # Asymmetric sidebands around GMF
        # Upper sideband at 630 Hz (GMF + shaft_freq), amplitude 0.3
        signal += 0.3 * np.sin(2 * np.pi * 630 * t)
        # Lower sideband at 570 Hz (GMF - shaft_freq), amplitude 0.1
        signal += 0.1 * np.sin(2 * np.pi * 570 * t)

        # Small noise
        signal += 0.01 * rng.standard_normal(len(t))

        analyzer = Tier4Analyzer()
        params = _make_params()
        candidates = analyzer.analyze(signal, params)

        fault_ids = [c.fault_id for c in candidates]
        assert 16 in fault_ids, (
            f"Expected Fault #16 (Gear Misalignment) in results, got {fault_ids}"
        )

        fault_16 = next(c for c in candidates if c.fault_id == 16)
        assert fault_16.confidence >= 0.3


# ---------------------------------------------------------------------------
# Test: Fault #17 -- Broken Tooth
# ---------------------------------------------------------------------------


class TestBrokenTooth:
    """Fault #17: Impulsive signal with kurtosis>4, GMF harmonics, cepstrum rahmonic."""

    def test_broken_tooth(self) -> None:
        rng = np.random.default_rng(42)
        t = _time_axis()

        signal = np.zeros_like(t)

        # Add GMF harmonics
        for n in range(1, 4):
            signal += 0.5 / n * np.sin(2 * np.pi * n * GMF * t)

        # Add periodic impulses at shaft period (every 1/30 s)
        period_samples = int(FS / SHAFT_FREQ)
        for i in range(0, len(t), period_samples):
            width = 10
            signal[i : i + width] += 5.0  # sharp impulse

        # Small noise
        signal += 0.01 * rng.standard_normal(len(t))

        analyzer = Tier4Analyzer()
        params = _make_params()
        candidates = analyzer.analyze(signal, params)

        fault_ids = [c.fault_id for c in candidates]
        assert 17 in fault_ids, (
            f"Expected Fault #17 (Broken Tooth) in results, got {fault_ids}"
        )

        fault_17 = next(c for c in candidates if c.fault_id == 17)
        assert fault_17.confidence >= 0.3


# ---------------------------------------------------------------------------
# Test: Fault #18 -- Gear Eccentricity
# ---------------------------------------------------------------------------


class TestGearEccentricity:
    """Fault #18: GMF +/- 1X symmetric sidebands + elevated 1X."""

    def test_gear_eccentricity(self) -> None:
        rng = np.random.default_rng(42)
        t = _time_axis()

        # GMF at 600 Hz
        signal = np.sin(2 * np.pi * GMF * t)

        # Symmetric 1X sidebands at 570 Hz and 630 Hz (GMF +/- 30 Hz)
        signal += 0.3 * np.sin(2 * np.pi * (GMF - SHAFT_FREQ) * t)
        signal += 0.3 * np.sin(2 * np.pi * (GMF + SHAFT_FREQ) * t)

        # Elevated 1X (30 Hz)
        signal += 0.8 * np.sin(2 * np.pi * SHAFT_FREQ * t)

        # Small noise
        signal += 0.01 * rng.standard_normal(len(t))

        analyzer = Tier4Analyzer()
        params = _make_params()
        candidates = analyzer.analyze(signal, params)

        fault_ids = [c.fault_id for c in candidates]
        assert 18 in fault_ids, (
            f"Expected Fault #18 (Gear Eccentricity) in results, got {fault_ids}"
        )

        fault_18 = next(c for c in candidates if c.fault_id == 18)
        assert fault_18.confidence >= 0.3


# ---------------------------------------------------------------------------
# Test: Fault #19 -- Gear Shaft Bend
# ---------------------------------------------------------------------------


class TestGearShaftBend:
    """Fault #19: 1X + 2X elevated + GMF + sidebands at GMF +/- 1X."""

    def test_gear_shaft_bend(self) -> None:
        rng = np.random.default_rng(42)
        t = _time_axis()

        # Elevated 1X (30 Hz)
        signal = 0.8 * np.sin(2 * np.pi * SHAFT_FREQ * t)

        # Elevated 2X (60 Hz)
        signal += 0.6 * np.sin(2 * np.pi * 2 * SHAFT_FREQ * t)

        # GMF (600 Hz)
        signal += np.sin(2 * np.pi * GMF * t)

        # Sidebands at 570 Hz and 630 Hz (GMF +/- 30 Hz)
        signal += 0.3 * np.sin(2 * np.pi * (GMF - SHAFT_FREQ) * t)
        signal += 0.3 * np.sin(2 * np.pi * (GMF + SHAFT_FREQ) * t)

        # Small noise
        signal += 0.01 * rng.standard_normal(len(t))

        analyzer = Tier4Analyzer()
        params = _make_params()
        candidates = analyzer.analyze(signal, params)

        fault_ids = [c.fault_id for c in candidates]
        assert 19 in fault_ids, (
            f"Expected Fault #19 (Gear Shaft Bend) in results, got {fault_ids}"
        )

        fault_19 = next(c for c in candidates if c.fault_id == 19)
        assert fault_19.confidence >= 0.3


# ---------------------------------------------------------------------------
# Test: Fault #20 -- Gear Wear
# ---------------------------------------------------------------------------


class TestGearWear:
    """Fault #20: Broadband noise around GMF + >=3 GMF harmonics."""

    def test_gear_wear(self) -> None:
        rng = np.random.default_rng(42)
        t = _time_axis()

        # GMF + 2xGMF + 3xGMF + 4xGMF harmonics
        signal = np.sin(2 * np.pi * GMF * t)
        signal += 0.5 * np.sin(2 * np.pi * 2 * GMF * t)
        signal += 0.3 * np.sin(2 * np.pi * 3 * GMF * t)
        signal += 0.2 * np.sin(2 * np.pi * 4 * GMF * t)

        # Broadband noise concentrated around GMF region (450-750 Hz)
        noise = rng.standard_normal(len(t))
        band_noise = bandpass_filter(noise, FS, 450, 750) * 0.3
        signal += band_noise

        # Small background noise
        signal += 0.01 * rng.standard_normal(len(t))

        analyzer = Tier4Analyzer()
        params = _make_params()
        candidates = analyzer.analyze(signal, params)

        fault_ids = [c.fault_id for c in candidates]
        assert 20 in fault_ids, (
            f"Expected Fault #20 (Gear Wear) in results, got {fault_ids}"
        )

        fault_20 = next(c for c in candidates if c.fault_id == 20)
        assert fault_20.confidence >= 0.3


# ---------------------------------------------------------------------------
# Test: can_run() gating
# ---------------------------------------------------------------------------


class TestTier4CannotRunWithoutGearParams:
    """Tier4Analyzer.can_run() should return False when gear params are missing."""

    def test_tier4_cannot_run_without_gear_params(self) -> None:
        analyzer = Tier4Analyzer()

        # Missing both gear params
        params_no_gear = MachineParameters(
            sampling_rate=FS,
            rpm=RPM,
        )
        assert analyzer.can_run(params_no_gear) is False

        # Missing gear_teeth_driven only
        params_no_driven = MachineParameters(
            sampling_rate=FS,
            rpm=RPM,
            gear_teeth_drive=TEETH_DRIVE,
        )
        assert analyzer.can_run(params_no_driven) is False

        # Missing gear_teeth_drive only
        params_no_drive = MachineParameters(
            sampling_rate=FS,
            rpm=RPM,
            gear_teeth_driven=TEETH_DRIVEN,
        )
        assert analyzer.can_run(params_no_drive) is False

        # Missing RPM
        params_no_rpm = MachineParameters(
            sampling_rate=FS,
            gear_teeth_drive=TEETH_DRIVE,
            gear_teeth_driven=TEETH_DRIVEN,
        )
        assert analyzer.can_run(params_no_rpm) is False

        # All present -- should return True
        params_full = _make_params()
        assert analyzer.can_run(params_full) is True
