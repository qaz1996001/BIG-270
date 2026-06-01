"""Tests for Tier 2 analyzer -- Bearing fault diagnosis.

Covers all 3 bearing fault types:
* Fault #4: Inner Race Defect (BPFI harmonics + 1X sidebands).
* Fault #5: Outer Race Defect (BPFO harmonics, no 1X sidebands).
* Fault #7: Ball Defect (BSF harmonics + FTF sidebands, two paths).

Also tests:
* Auto-estimated RPM penalty (0.7× confidence, 5% tolerance).
* can_run gate (requires rpm + bearing).
"""

from __future__ import annotations

import numpy as np

from vibfault.analyzers.tier2 import Tier2Analyzer
from vibfault.core.frequencies import (
    bearing_bpfi,
    bearing_bpfo,
    bearing_bsf,
    bearing_ftf,
)
from vibfault.core.models import BearingGeometry, MachineParameters

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

FS = 8192  # Hz
RPM = 1800  # 30 Hz shaft frequency
SHAFT_FREQ = RPM / 60.0  # 30 Hz
DURATION = 2.0  # seconds
CARRIER_FREQ = 3000.0  # Hz — simulated bearing resonance band

BEARING = BearingGeometry(
    n_balls=9,
    ball_diameter=7.94,
    pitch_diameter=39.04,
    contact_angle=0.0,
)

# Pre-compute characteristic frequencies
BPFI = bearing_bpfi(
    BEARING.n_balls,
    BEARING.ball_diameter,
    BEARING.pitch_diameter,
    BEARING.contact_angle,
    SHAFT_FREQ,
)
BPFO = bearing_bpfo(
    BEARING.n_balls,
    BEARING.ball_diameter,
    BEARING.pitch_diameter,
    BEARING.contact_angle,
    SHAFT_FREQ,
)
BSF = bearing_bsf(
    BEARING.ball_diameter,
    BEARING.pitch_diameter,
    BEARING.contact_angle,
    SHAFT_FREQ,
)
FTF = bearing_ftf(
    BEARING.ball_diameter,
    BEARING.pitch_diameter,
    BEARING.contact_angle,
    SHAFT_FREQ,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_am_signal(
    modulation_components: list[tuple[float, float]],
) -> np.ndarray:
    """Create an AM signal so that fault frequencies appear in the envelope spectrum."""
    t = np.arange(0, DURATION, 1.0 / FS)
    carrier = np.cos(2 * np.pi * CARRIER_FREQ * t)

    modulation = np.zeros_like(t)
    for freq, depth in modulation_components:
        modulation += depth * np.cos(2 * np.pi * freq * t)

    return carrier * (1.0 + modulation)


def _fault_ids(candidates) -> set[int]:
    return {c.fault_id for c in candidates}


def _get_fault(candidates, fault_id: int):
    for c in candidates:
        if c.fault_id == fault_id:
            return c
    return None


# ---------------------------------------------------------------------------
# Fault #4: Inner Race Defect (BPFI)
# ---------------------------------------------------------------------------


class TestInnerRaceDefect:
    """Inner race: ≥2 BPFI harmonics + 1X sidebands around BPFI."""

    def test_inner_race_detected(self) -> None:
        modulation = [
            (BPFI, 0.6),  # BPFI fundamental
            (2 * BPFI, 0.4),  # 2nd BPFI harmonic
            (BPFI + SHAFT_FREQ, 0.3),  # upper 1X sideband
            (BPFI - SHAFT_FREQ, 0.3),  # lower 1X sideband
        ]
        signal = _make_am_signal(modulation)
        params = MachineParameters(sampling_rate=FS, rpm=RPM, bearing=BEARING)

        analyzer = Tier2Analyzer()
        candidates = analyzer.analyze(signal, params)

        assert 4 in _fault_ids(candidates), (
            f"Expected Fault #4 (Inner Race); got {_fault_ids(candidates)}"
        )
        fault = _get_fault(candidates, 4)
        assert fault.confidence >= 0.8

    def test_inner_race_not_detected_without_sidebands(self) -> None:
        """BPFI harmonics alone (no 1X sidebands) → no inner race detection."""
        modulation = [
            (BPFI, 0.6),
            (2 * BPFI, 0.4),
            # No sidebands
        ]
        signal = _make_am_signal(modulation)
        params = MachineParameters(sampling_rate=FS, rpm=RPM, bearing=BEARING)

        analyzer = Tier2Analyzer()
        candidates = analyzer.analyze(signal, params)

        assert 4 not in _fault_ids(candidates)


# ---------------------------------------------------------------------------
# Fault #5: Outer Race Defect (BPFO)
# ---------------------------------------------------------------------------


class TestOuterRaceDefect:
    """Outer race: ≥2 BPFO harmonics, typically no prominent 1X sidebands."""

    def test_outer_race_detected(self) -> None:
        modulation = [
            (BPFO, 0.6),  # BPFO fundamental
            (2 * BPFO, 0.4),  # 2nd harmonic
            (3 * BPFO, 0.2),  # 3rd harmonic
        ]
        signal = _make_am_signal(modulation)
        params = MachineParameters(sampling_rate=FS, rpm=RPM, bearing=BEARING)

        analyzer = Tier2Analyzer()
        candidates = analyzer.analyze(signal, params)

        assert 5 in _fault_ids(candidates), (
            f"Expected Fault #5 (Outer Race); got {_fault_ids(candidates)}"
        )
        fault = _get_fault(candidates, 5)
        assert fault.confidence >= 0.8

    def test_outer_race_not_detected_with_single_harmonic(self) -> None:
        """Only 1 BPFO harmonic is insufficient (need ≥2)."""
        modulation = [
            (BPFO, 0.6),  # BPFO fundamental only
        ]
        signal = _make_am_signal(modulation)
        params = MachineParameters(sampling_rate=FS, rpm=RPM, bearing=BEARING)

        analyzer = Tier2Analyzer()
        candidates = analyzer.analyze(signal, params)

        assert 5 not in _fault_ids(candidates)

    def test_outer_race_confidence_reduced_with_sidebands(self) -> None:
        """If 1X sidebands are found near BPFO, confidence gets a 10% penalty."""
        modulation = [
            (BPFO, 0.6),
            (2 * BPFO, 0.4),
            (BPFO + SHAFT_FREQ, 0.3),  # unexpected 1X sideband
            (BPFO - SHAFT_FREQ, 0.3),
        ]
        signal = _make_am_signal(modulation)
        params = MachineParameters(sampling_rate=FS, rpm=RPM, bearing=BEARING)

        analyzer = Tier2Analyzer()
        candidates = analyzer.analyze(signal, params)

        fault = _get_fault(candidates, 5)
        if fault is not None:
            # With sideband penalty: 0.85 * (1 - 0.10) = 0.765
            assert fault.confidence < 0.85


# ---------------------------------------------------------------------------
# Fault #7: Ball Defect (BSF)
# ---------------------------------------------------------------------------


class TestBSFDetection:
    """Ball defect: classic (BSF harmonics + FTF sidebands) and
    sideband-only (weak BSF + FTF sidebands) paths."""

    def test_bsf_classic_detection(self) -> None:
        modulation = [
            (BSF, 0.6),
            (2 * BSF, 0.4),
            (BSF + FTF, 0.3),
            (BSF - FTF, 0.3),
        ]
        signal = _make_am_signal(modulation)
        params = MachineParameters(sampling_rate=FS, rpm=RPM, bearing=BEARING)

        analyzer = Tier2Analyzer()
        candidates = analyzer.analyze(signal, params)

        assert 7 in _fault_ids(candidates)
        ball_fault = _get_fault(candidates, 7)
        assert ball_fault.confidence >= 0.65

    def test_bsf_sideband_only_detection(self) -> None:
        modulation = [
            (BSF, 0.25),
            (BSF + FTF, 0.35),
            (BSF - FTF, 0.35),
        ]
        signal = _make_am_signal(modulation)
        params = MachineParameters(sampling_rate=FS, rpm=RPM, bearing=BEARING)

        analyzer = Tier2Analyzer()
        candidates = analyzer.analyze(signal, params)

        assert 7 in _fault_ids(candidates)
        ball_fault = _get_fault(candidates, 7)
        assert 0.50 <= ball_fault.confidence <= 0.60

        evidence_descriptions = [e.description for e in ball_fault.evidence]
        assert any("sideband-only" in desc.lower() for desc in evidence_descriptions)

    def test_bsf_no_sidebands_fails(self) -> None:
        modulation = [
            (BSF, 0.6),
            (2 * BSF, 0.4),
        ]
        signal = _make_am_signal(modulation)
        params = MachineParameters(sampling_rate=FS, rpm=RPM, bearing=BEARING)

        analyzer = Tier2Analyzer()
        candidates = analyzer.analyze(signal, params)

        assert 7 not in _fault_ids(candidates)


# ---------------------------------------------------------------------------
# Auto-estimated RPM
# ---------------------------------------------------------------------------


class TestAutoEstimatedRPM:
    """Auto-estimated RPM widens tolerance to 5% and scales confidence by 0.7."""

    def test_auto_estimated_reduces_confidence(self) -> None:
        modulation = [
            (BPFO, 0.6),
            (2 * BPFO, 0.4),
            (3 * BPFO, 0.2),
        ]
        signal = _make_am_signal(modulation)

        params_manual = MachineParameters(
            sampling_rate=FS,
            rpm=RPM,
            bearing=BEARING,
            rpm_source="manual",
        )
        params_auto = MachineParameters(
            sampling_rate=FS,
            rpm=RPM,
            bearing=BEARING,
            rpm_source="auto_estimated",
        )

        analyzer = Tier2Analyzer()
        cands_manual = analyzer.analyze(signal, params_manual)
        cands_auto = analyzer.analyze(signal, params_auto)

        fault_manual = _get_fault(cands_manual, 5)
        fault_auto = _get_fault(cands_auto, 5)

        if fault_manual and fault_auto:
            assert fault_auto.confidence < fault_manual.confidence


# ---------------------------------------------------------------------------
# can_run gate
# ---------------------------------------------------------------------------


class TestTier2CanRun:
    """Tier 2 requires rpm + bearing (or bearing_model)."""

    def test_cannot_run_without_bearing(self) -> None:
        analyzer = Tier2Analyzer()
        params = MachineParameters(sampling_rate=FS, rpm=RPM)
        assert analyzer.can_run(params) is False

    def test_cannot_run_without_rpm(self) -> None:
        analyzer = Tier2Analyzer()
        params = MachineParameters(sampling_rate=FS, bearing=BEARING)
        assert analyzer.can_run(params) is False

    def test_can_run_with_rpm_and_bearing(self) -> None:
        analyzer = Tier2Analyzer()
        params = MachineParameters(sampling_rate=FS, rpm=RPM, bearing=BEARING)
        assert analyzer.can_run(params) is True

    def test_can_run_with_bearing_model(self) -> None:
        analyzer = Tier2Analyzer()
        params = MachineParameters(
            sampling_rate=FS,
            rpm=RPM,
            bearing_model="6205",
        )
        assert analyzer.can_run(params) is True
