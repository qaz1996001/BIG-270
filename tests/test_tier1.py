"""Tests for Tier 1 analyzer -- RPM-based fault diagnosis.

Covers all 6 fault rules:
* Fault #1: Unbalance — dominant 1X, low 2X/1X ratio.
* Fault #2: Bent Shaft — elevated 1X with 2X/1X > 0.5.
* Fault #3: Parallel Misalignment — dominant 2X.
* Fault #9: Angular Misalignment — elevated 1X (partial diagnosis).
* Fault #6: Mechanical Looseness — ≥5 harmonics + sub-harmonic.
* Faults #11/#12: Oil Whirl/Whip — sub-synchronous peak at 0.35–0.50X.

Also tests:
* Auto-estimated RPM penalty (0.7× confidence).
* can_run gate.
"""

from __future__ import annotations

import numpy as np
import pytest

from vibfault.analyzers.tier1 import Tier1Analyzer
from vibfault.core.models import MachineParameters

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

FS = 4096  # Hz
RPM = 1800  # 30 Hz shaft frequency
SHAFT_FREQ = RPM / 60.0  # 30 Hz
DURATION = 2.0  # seconds — gives 0.5 Hz frequency resolution
N_HARMONICS = 10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_signal(
    components: list[tuple[float, float]],
    noise: float = 0.001,
) -> np.ndarray:
    """Build a synthetic signal from frequency/amplitude pairs."""
    rng = np.random.default_rng(42)
    t = np.arange(0, DURATION, 1.0 / FS)
    signal = sum(amp * np.sin(2 * np.pi * freq * t) for freq, amp in components)
    signal += noise * rng.standard_normal(len(t))
    return signal


def _make_looseness_signal(
    sub_harmonic_ratio: float | None,
    *,
    harmonic_amplitude: float = 1.0,
    sub_amplitude: float = 0.5,
) -> np.ndarray:
    """Build a looseness-pattern signal with shaft harmonics + optional sub-harmonic."""
    components: list[tuple[float, float]] = []
    for order in range(1, N_HARMONICS + 1):
        components.append((SHAFT_FREQ * order, harmonic_amplitude))
    if sub_harmonic_ratio is not None:
        components.append((SHAFT_FREQ * sub_harmonic_ratio, sub_amplitude))
    return _make_signal(components)


def _fault_ids(candidates) -> set[int]:
    return {c.fault_id for c in candidates}


def _get_fault(candidates, fault_id: int):
    for c in candidates:
        if c.fault_id == fault_id:
            return c
    return None


# ---------------------------------------------------------------------------
# Fault #1: Unbalance
# ---------------------------------------------------------------------------


class TestUnbalance:
    """Dominant 1X with low 2X/1X ratio triggers Fault #1."""

    def test_unbalance_detected(self) -> None:
        """Strong 1X, tiny 2X → Unbalance."""
        components = [
            (SHAFT_FREQ, 5.0),  # very strong 1X
            (2 * SHAFT_FREQ, 0.2),  # tiny 2X (ratio 0.04)
        ]
        signal = _make_signal(components)
        params = MachineParameters(sampling_rate=FS, rpm=RPM)

        analyzer = Tier1Analyzer()
        candidates = analyzer.analyze(signal, params)

        assert 1 in _fault_ids(candidates), (
            f"Expected Fault #1 (Unbalance); got {_fault_ids(candidates)}"
        )
        fault = _get_fault(candidates, 1)
        assert fault.confidence >= 0.8

    def test_unbalance_not_triggered_when_2x_dominant(self) -> None:
        """If 2X is dominant, Unbalance should NOT fire."""
        components = [
            (SHAFT_FREQ, 0.3),
            (2 * SHAFT_FREQ, 5.0),  # 2X dominant
        ]
        signal = _make_signal(components)
        params = MachineParameters(sampling_rate=FS, rpm=RPM)

        analyzer = Tier1Analyzer()
        candidates = analyzer.analyze(signal, params)

        assert 1 not in _fault_ids(candidates)


# ---------------------------------------------------------------------------
# Fault #2: Bent Shaft
# ---------------------------------------------------------------------------


class TestBentShaft:
    """Elevated 1X AND 2X with 2X/1X > 0.5 triggers Fault #2."""

    def test_bent_shaft_detected(self) -> None:
        components = [
            (SHAFT_FREQ, 1.0),  # 1X
            (2 * SHAFT_FREQ, 0.8),  # 2X (ratio = 0.8 > 0.5)
        ]
        signal = _make_signal(components)
        params = MachineParameters(sampling_rate=FS, rpm=RPM)

        analyzer = Tier1Analyzer()
        candidates = analyzer.analyze(signal, params)

        assert 2 in _fault_ids(candidates), (
            f"Expected Fault #2 (Bent Shaft); got {_fault_ids(candidates)}"
        )

    def test_bent_shaft_not_triggered_low_ratio(self) -> None:
        """If 2X/1X <= 0.5, Bent Shaft should NOT fire."""
        components = [
            (SHAFT_FREQ, 5.0),
            (2 * SHAFT_FREQ, 0.2),  # ratio = 0.04
        ]
        signal = _make_signal(components)
        params = MachineParameters(sampling_rate=FS, rpm=RPM)

        analyzer = Tier1Analyzer()
        candidates = analyzer.analyze(signal, params)

        assert 2 not in _fault_ids(candidates)


# ---------------------------------------------------------------------------
# Fault #3: Parallel Misalignment
# ---------------------------------------------------------------------------


class TestParallelMisalignment:
    """Dominant 2X triggers Fault #3."""

    def test_parallel_misalignment_detected(self) -> None:
        components = [
            (SHAFT_FREQ, 0.3),
            (2 * SHAFT_FREQ, 5.0),  # 2X dominant
        ]
        signal = _make_signal(components)
        params = MachineParameters(sampling_rate=FS, rpm=RPM)

        analyzer = Tier1Analyzer()
        candidates = analyzer.analyze(signal, params)

        assert 3 in _fault_ids(candidates), (
            f"Expected Fault #3 (Parallel Misalignment); got {_fault_ids(candidates)}"
        )

    def test_not_triggered_when_1x_dominant(self) -> None:
        components = [
            (SHAFT_FREQ, 5.0),  # 1X dominant
            (2 * SHAFT_FREQ, 0.5),
        ]
        signal = _make_signal(components)
        params = MachineParameters(sampling_rate=FS, rpm=RPM)

        analyzer = Tier1Analyzer()
        candidates = analyzer.analyze(signal, params)

        assert 3 not in _fault_ids(candidates)


# ---------------------------------------------------------------------------
# Fault #9: Angular Misalignment
# ---------------------------------------------------------------------------


class TestAngularMisalignment:
    """Elevated 1X (even partial diagnosis) triggers Fault #9."""

    def test_angular_misalignment_detected(self) -> None:
        """Any signal with 1X > 0 triggers angular misalignment (partial)."""
        components = [
            (SHAFT_FREQ, 2.0),
        ]
        signal = _make_signal(components)
        params = MachineParameters(sampling_rate=FS, rpm=RPM)

        analyzer = Tier1Analyzer()
        candidates = analyzer.analyze(signal, params)

        assert 9 in _fault_ids(candidates), (
            f"Expected Fault #9 (Angular Misalignment); got {_fault_ids(candidates)}"
        )


# ---------------------------------------------------------------------------
# Fault #6: Mechanical Looseness
# ---------------------------------------------------------------------------


class TestLoosenessSubHarmonics:
    """Verify that Fault #6 fires for each accepted sub-harmonic type
    and does NOT fire when no sub-harmonic is present."""

    def test_looseness_with_half_subharmonic(self) -> None:
        signal = _make_looseness_signal(sub_harmonic_ratio=0.5)
        params = MachineParameters(sampling_rate=FS, rpm=RPM)

        analyzer = Tier1Analyzer()
        candidates = analyzer.analyze(signal, params)

        assert 6 in _fault_ids(candidates), (
            f"Expected Fault #6 with 0.5X sub-harmonic; got {_fault_ids(candidates)}"
        )

    def test_looseness_with_third_subharmonic(self) -> None:
        signal = _make_looseness_signal(sub_harmonic_ratio=1.0 / 3.0)
        params = MachineParameters(sampling_rate=FS, rpm=RPM)

        analyzer = Tier1Analyzer()
        candidates = analyzer.analyze(signal, params)

        assert 6 in _fault_ids(candidates), (
            f"Expected Fault #6 with 1/3X sub-harmonic; got {_fault_ids(candidates)}"
        )

    def test_looseness_with_quarter_subharmonic(self) -> None:
        signal = _make_looseness_signal(sub_harmonic_ratio=0.25)
        params = MachineParameters(sampling_rate=FS, rpm=RPM)

        analyzer = Tier1Analyzer()
        candidates = analyzer.analyze(signal, params)

        assert 6 in _fault_ids(candidates), (
            f"Expected Fault #6 with 1/4X sub-harmonic; got {_fault_ids(candidates)}"
        )

    def test_looseness_no_subharmonic_fails(self) -> None:
        signal = _make_looseness_signal(sub_harmonic_ratio=None)
        params = MachineParameters(sampling_rate=FS, rpm=RPM)

        analyzer = Tier1Analyzer()
        candidates = analyzer.analyze(signal, params)

        assert 6 not in _fault_ids(candidates), (
            f"Fault #6 should NOT fire without sub-harmonics; got {_fault_ids(candidates)}"
        )


# ---------------------------------------------------------------------------
# Faults #11/#12: Oil Whirl / Whip
# ---------------------------------------------------------------------------


class TestOilWhirlWhip:
    """Sub-synchronous peak at 0.35–0.50X triggers the merged Oil Whirl/Whip."""

    def test_oil_whirl_detected(self) -> None:
        """Peak at 0.42X (12.6 Hz) should trigger Fault #11 (merged with #12)."""
        components = [
            (SHAFT_FREQ, 1.0),  # 1X
            (SHAFT_FREQ * 0.42, 3.0),  # 0.42X — strong sub-sync
        ]
        signal = _make_signal(components)
        params = MachineParameters(sampling_rate=FS, rpm=RPM)

        analyzer = Tier1Analyzer()
        candidates = analyzer.analyze(signal, params)

        assert 11 in _fault_ids(candidates), (
            f"Expected Fault #11 (Oil Whirl/Whip); got {_fault_ids(candidates)}"
        )
        fault = _get_fault(candidates, 11)
        assert fault.merged_with is not None
        assert 12 in fault.merged_with

    def test_oil_whip_detected_with_critical_speed(self) -> None:
        """When sub-sync freq matches critical speed, emit Oil Whip (#12) only."""
        # critical_speed = 756 RPM → critical_freq = 12.6 Hz
        # sub-sync at 0.42X = 12.6 Hz → matches critical → Oil Whip
        critical_rpm = SHAFT_FREQ * 0.42 * 60.0  # 756 RPM
        components = [
            (SHAFT_FREQ, 1.0),
            (SHAFT_FREQ * 0.42, 3.0),
        ]
        signal = _make_signal(components)
        params = MachineParameters(
            sampling_rate=FS,
            rpm=RPM,
            critical_speed=critical_rpm,
        )

        analyzer = Tier1Analyzer()
        candidates = analyzer.analyze(signal, params)

        assert 12 in _fault_ids(candidates), (
            f"Expected Fault #12 (Oil Whip); got {_fault_ids(candidates)}"
        )
        fault = _get_fault(candidates, 12)
        assert fault.merged_with is None  # NOT merged — distinguished

    def test_oil_whirl_detected_with_critical_speed(self) -> None:
        """When sub-sync freq does NOT match critical speed, emit Oil Whirl (#11)."""
        # critical_speed = 3000 RPM → critical_freq = 50 Hz
        # sub-sync at 0.42X = 12.6 Hz → does NOT match → Oil Whirl
        components = [
            (SHAFT_FREQ, 1.0),
            (SHAFT_FREQ * 0.42, 3.0),
        ]
        signal = _make_signal(components)
        params = MachineParameters(
            sampling_rate=FS,
            rpm=RPM,
            critical_speed=3000.0,
        )

        analyzer = Tier1Analyzer()
        candidates = analyzer.analyze(signal, params)

        assert 11 in _fault_ids(candidates), (
            f"Expected Fault #11 (Oil Whirl); got {_fault_ids(candidates)}"
        )
        fault = _get_fault(candidates, 11)
        assert fault.merged_with is None  # NOT merged — distinguished
        assert fault.fault_name == "Oil Whirl"

    def test_oil_whirl_not_triggered_outside_range(self) -> None:
        """Peak at 0.2X should NOT trigger Oil Whirl/Whip."""
        components = [
            (SHAFT_FREQ, 1.0),
            (SHAFT_FREQ * 0.2, 3.0),  # 0.2X — too low
        ]
        signal = _make_signal(components)
        params = MachineParameters(sampling_rate=FS, rpm=RPM)

        analyzer = Tier1Analyzer()
        candidates = analyzer.analyze(signal, params)

        assert 11 not in _fault_ids(candidates)


# ---------------------------------------------------------------------------
# Auto-estimated RPM penalty
# ---------------------------------------------------------------------------


class TestAutoRPMPenalty:
    """Confidence should be scaled by 0.7 when rpm_source='auto_estimated'."""

    def test_auto_estimated_reduces_confidence(self) -> None:
        components = [(SHAFT_FREQ, 5.0), (2 * SHAFT_FREQ, 0.1)]
        signal = _make_signal(components)

        params_manual = MachineParameters(sampling_rate=FS, rpm=RPM, rpm_source="manual")
        params_auto = MachineParameters(sampling_rate=FS, rpm=RPM, rpm_source="auto_estimated")

        analyzer = Tier1Analyzer()

        cands_manual = analyzer.analyze(signal, params_manual)
        cands_auto = analyzer.analyze(signal, params_auto)

        # Both should detect Fault #1
        fault_manual = _get_fault(cands_manual, 1)
        fault_auto = _get_fault(cands_auto, 1)

        if fault_manual and fault_auto:
            assert fault_auto.confidence < fault_manual.confidence
            assert fault_auto.confidence == pytest.approx(fault_manual.confidence * 0.7, rel=0.01)


# ---------------------------------------------------------------------------
# can_run gate
# ---------------------------------------------------------------------------


class TestTier1CanRun:
    """Tier 1 requires RPM to run."""

    def test_cannot_run_without_rpm(self) -> None:
        analyzer = Tier1Analyzer()
        params = MachineParameters(sampling_rate=FS)
        assert analyzer.can_run(params) is False

    def test_can_run_with_rpm(self) -> None:
        analyzer = Tier1Analyzer()
        params = MachineParameters(sampling_rate=FS, rpm=RPM)
        assert analyzer.can_run(params) is True
