"""Tests for the Tier 3 electrical fault analyzer.

Covers the three electrical fault groups diagnosed by
:class:`~vibfault.analyzers.tier3.Tier3Analyzer`:

=====  ================================  =========================================
 ID    Name                              Key spectral signature
=====  ================================  =========================================
 8     Air Gap Eccentricity              2FL peak + pole-pass (Fp) sidebands
 14/15 Broken Rotor Bar / End Ring       1X +/- Fp sidebands (merged)
 10/13 Stator Electrical (Phase/Winding) 2FL elevated, NO 1X +/- Fp sidebands
=====  ================================  =========================================

Motor parameters used throughout:
    6-pole motor (3 pole pairs), 60 Hz supply, 1080 RPM
    shaft_freq = 18 Hz, f_sync = 20 Hz, f_slip = 2 Hz, Fp = 6 Hz

    Fp = 6 Hz ensures sideband search windows (±3% tolerance) around 2FL = 120 Hz
    do NOT overlap with the centre peak, which was the problem with Fp = 1 Hz.
"""

from __future__ import annotations

import numpy as np
from pytest import approx

from vibfault.analyzers.tier3 import Tier3Analyzer
from vibfault.core.models import MachineParameters

# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------

FS = 4096  # sampling rate (Hz)
DURATION = 2.0  # seconds

# Motor parameters — 6-pole induction motor at 60 Hz supply
RPM = 1080
SHAFT_FREQ = RPM / 60.0  # 18.0 Hz
LINE_FREQ = 60.0
POLE_PAIRS = 3
F_2FL = 2 * LINE_FREQ  # 120 Hz
F_SYNC = LINE_FREQ / POLE_PAIRS  # 20 Hz
F_SLIP = F_SYNC - SHAFT_FREQ  # 2.0 Hz
F_POLE_PASS = POLE_PAIRS * F_SLIP  # 6.0 Hz


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _time_vector(duration: float = DURATION) -> np.ndarray:
    """Return a time vector [0, duration) at sampling rate FS."""
    return np.arange(0, duration, 1.0 / FS)


def _add_tone(signal: np.ndarray, t: np.ndarray, freq: float, amp: float) -> np.ndarray:
    """Add a sinusoidal component at *freq* Hz with peak amplitude *amp*."""
    return signal + amp * np.sin(2 * np.pi * freq * t)


def _add_noise(signal: np.ndarray, sigma: float = 0.01, seed: int = 42) -> np.ndarray:
    """Add Gaussian noise with standard deviation *sigma*.

    Each call uses its own RNG seeded with *seed* so that test results are
    reproducible and independent of execution order.
    """
    rng = np.random.default_rng(seed)
    return signal + sigma * rng.standard_normal(len(signal))


def _base_params(**overrides: object) -> MachineParameters:
    """Build a MachineParameters instance with standard motor settings."""
    defaults: dict[str, object] = {
        "sampling_rate": float(FS),
        "rpm": float(RPM),
        "pole_pairs": POLE_PAIRS,
        "line_frequency": LINE_FREQ,
    }
    defaults.update(overrides)
    return MachineParameters(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAirGapEccentricity:
    """Fault #8: Air Gap Eccentricity -- 2FL peak + Fp sidebands around 2FL."""

    def test_air_gap_eccentricity(self) -> None:
        """Signal with 120 Hz (2FL) + sidebands at 114/126 Hz (2FL +/- Fp).

        Should detect Fault #8 with confidence ~0.80.
        """
        t = _time_vector()
        signal = np.zeros_like(t)
        signal = _add_tone(signal, t, F_2FL, 1.0)  # 120 Hz
        signal = _add_tone(signal, t, F_2FL - F_POLE_PASS, 0.5)  # 119 Hz
        signal = _add_tone(signal, t, F_2FL + F_POLE_PASS, 0.5)  # 121 Hz
        signal = _add_noise(signal, seed=100)

        params = _base_params()
        analyzer = Tier3Analyzer()
        candidates = analyzer.analyze(signal, params)

        fault_ids = [c.fault_id for c in candidates]
        assert 8 in fault_ids, f"Expected Fault #8, got {fault_ids}"

        fault_8 = next(c for c in candidates if c.fault_id == 8)
        assert fault_8.confidence == approx(0.80, abs=0.05)
        assert fault_8.fault_category == "electrical"
        assert fault_8.diagnosis_type == "S"
        assert len(fault_8.evidence) >= 1  # at least the 2FL peak evidence


class TestBrokenRotorBar:
    """Faults #14/#15: Broken Rotor Bar / End Ring (merged)."""

    def test_broken_rotor_bar(self) -> None:
        """Signal with 18 Hz (1X) + sidebands at 12/24 Hz (1X +/- Fp).

        Should detect Fault #14 as merged with #15, diagnosis_type='M'.
        """
        t = _time_vector()
        signal = np.zeros_like(t)
        signal = _add_tone(signal, t, SHAFT_FREQ, 1.0)  # 29.5 Hz
        signal = _add_tone(signal, t, SHAFT_FREQ - F_POLE_PASS, 0.5)  # 28.5 Hz
        signal = _add_tone(signal, t, SHAFT_FREQ + F_POLE_PASS, 0.5)  # 30.5 Hz
        signal = _add_noise(signal, seed=200)

        params = _base_params()
        analyzer = Tier3Analyzer()
        candidates = analyzer.analyze(signal, params)

        fault_ids = [c.fault_id for c in candidates]
        assert 14 in fault_ids, f"Expected Fault #14, got {fault_ids}"

        fault_14 = next(c for c in candidates if c.fault_id == 14)
        assert fault_14.merged_with == [15]
        assert fault_14.diagnosis_type == "M"
        assert fault_14.confidence == approx(0.75, abs=0.05)

    def test_broken_rotor_bar_with_rbpf(self) -> None:
        """Same as above but with n_bars=28 and RBPF peak at 504 Hz.

        RBPF evidence should boost confidence from ~0.75 to ~0.80.
        """
        t = _time_vector()
        signal = np.zeros_like(t)
        signal = _add_tone(signal, t, SHAFT_FREQ, 1.0)  # 29.5 Hz
        signal = _add_tone(signal, t, SHAFT_FREQ - F_POLE_PASS, 0.5)  # 28.5 Hz
        signal = _add_tone(signal, t, SHAFT_FREQ + F_POLE_PASS, 0.5)  # 30.5 Hz
        rbpf = 28 * SHAFT_FREQ  # 826 Hz
        signal = _add_tone(signal, t, rbpf, 0.8)  # RBPF
        signal = _add_noise(signal, seed=300)

        params = _base_params(n_bars=28)
        analyzer = Tier3Analyzer()
        candidates = analyzer.analyze(signal, params)

        fault_ids = [c.fault_id for c in candidates]
        assert 14 in fault_ids, f"Expected Fault #14, got {fault_ids}"

        fault_14 = next(c for c in candidates if c.fault_id == 14)
        assert fault_14.confidence == approx(0.80, abs=0.05)
        # RBPF evidence should be present
        rbpf_evidence = [e for e in fault_14.evidence if e.feature_name == "RBPF_peak"]
        assert len(rbpf_evidence) == 1, "Expected RBPF peak in evidence"


class TestStatorElectrical:
    """Faults #10/#13: Stator Electrical (Phase/Winding) -- merged."""

    def test_stator_electrical(self) -> None:
        """Signal with 120 Hz (2FL) only, NO Fp sidebands around 1X.

        Should detect Fault #10 as merged with #13, diagnosis_type='M',
        confidence ~0.65.
        """
        t = _time_vector()
        signal = np.zeros_like(t)
        signal = _add_tone(signal, t, F_2FL, 1.0)  # 120 Hz only
        signal = _add_noise(signal, seed=1)

        params = _base_params()
        analyzer = Tier3Analyzer()
        candidates = analyzer.analyze(signal, params)

        fault_ids = [c.fault_id for c in candidates]
        assert 10 in fault_ids, f"Expected Fault #10, got {fault_ids}"

        fault_10 = next(c for c in candidates if c.fault_id == 10)
        assert fault_10.merged_with == [13]
        assert fault_10.diagnosis_type == "M"
        assert fault_10.confidence == approx(0.65, abs=0.05)

    def test_stator_not_detected_when_rotor_present(self) -> None:
        """Signal with 120 Hz (2FL) + 1X +/- Fp sidebands.

        The presence of pole-pass sidebands around 1X indicates a rotor fault
        (Fault #14), so Fault #10 (stator) should NOT be reported.
        """
        t = _time_vector()
        signal = np.zeros_like(t)
        signal = _add_tone(signal, t, F_2FL, 1.0)  # 120 Hz
        signal = _add_tone(signal, t, SHAFT_FREQ, 1.0)  # 18 Hz (1X)
        signal = _add_tone(signal, t, SHAFT_FREQ - F_POLE_PASS, 0.5)  # 12 Hz
        signal = _add_tone(signal, t, SHAFT_FREQ + F_POLE_PASS, 0.5)  # 24 Hz
        signal = _add_noise(signal, seed=500)

        params = _base_params()
        analyzer = Tier3Analyzer()
        candidates = analyzer.analyze(signal, params)

        fault_ids = [c.fault_id for c in candidates]
        assert 10 not in fault_ids, (
            f"Fault #10 should NOT be detected when rotor bar sidebands are present, "
            f"got {fault_ids}"
        )
        # Rotor bar fault should be detected instead
        assert 14 in fault_ids, f"Expected Fault #14 (rotor bar), got {fault_ids}"


class TestTier3CanRun:
    """Prerequisite gate: can_run should return False without electrical params."""

    def test_tier3_cannot_run_without_electrical_params(self) -> None:
        """Verify can_run returns False when pole_pairs or line_frequency is None."""
        analyzer = Tier3Analyzer()

        # Missing both electrical params
        params_no_elec = MachineParameters(sampling_rate=float(FS), rpm=float(RPM))
        assert not analyzer.can_run(params_no_elec)

        # Missing line_frequency only
        params_no_line = MachineParameters(
            sampling_rate=float(FS),
            rpm=float(RPM),
            pole_pairs=POLE_PAIRS,
        )
        assert not analyzer.can_run(params_no_line)

        # Missing pole_pairs only
        params_no_poles = MachineParameters(
            sampling_rate=float(FS),
            rpm=float(RPM),
            line_frequency=LINE_FREQ,
        )
        assert not analyzer.can_run(params_no_poles)

        # Missing rpm (also required)
        params_no_rpm = MachineParameters(
            sampling_rate=float(FS),
            pole_pairs=POLE_PAIRS,
            line_frequency=LINE_FREQ,
        )
        assert not analyzer.can_run(params_no_rpm)

        # All present -- should succeed
        params_ok = _base_params()
        assert analyzer.can_run(params_ok)
