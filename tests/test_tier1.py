"""Tests for Tier 1 analyzer -- Mechanical Looseness (Fault #6).

Validates that ``_check_looseness`` accepts 0.5X, 1/3X, and 1/4X
sub-harmonics as indicators of looseness, and rejects signals
that have many harmonics but no sub-harmonic at all.
"""

from __future__ import annotations

import numpy as np

from vibfault.analyzers.tier1 import Tier1Analyzer
from vibfault.core.models import MachineParameters

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

FS = 4096  # Hz
RPM = 1800  # 30 Hz shaft frequency
SHAFT_FREQ = RPM / 60.0  # 30 Hz
DURATION = 2.0  # seconds -- gives 0.5 Hz frequency resolution
N_HARMONICS = 10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_looseness_signal(
    sub_harmonic_ratio: float | None,
    *,
    harmonic_amplitude: float = 1.0,
    sub_amplitude: float = 0.5,
) -> np.ndarray:
    """Build a synthetic signal with shaft harmonics and an optional sub-harmonic.

    Parameters
    ----------
    sub_harmonic_ratio :
        Frequency ratio relative to shaft frequency for the sub-harmonic
        component (e.g. 0.5 for half-order, 1/3, 1/4).  ``None`` means
        no sub-harmonic is added.
    harmonic_amplitude :
        Peak amplitude of each shaft harmonic.
    sub_amplitude :
        Peak amplitude of the sub-harmonic component.

    Returns
    -------
    np.ndarray
        1-D time-series signal.
    """
    t = np.arange(0, DURATION, 1.0 / FS)

    components: list[tuple[float, float]] = []

    # Shaft harmonics 1X through N_HARMONICS * X
    for order in range(1, N_HARMONICS + 1):
        freq = SHAFT_FREQ * order
        components.append((freq, harmonic_amplitude))

    # Optional sub-harmonic
    if sub_harmonic_ratio is not None:
        freq = SHAFT_FREQ * sub_harmonic_ratio
        components.append((freq, sub_amplitude))

    signal = sum(amp * np.sin(2 * np.pi * freq * t) for freq, amp in components)
    return signal


def _fault_ids(candidates) -> set[int]:
    """Extract the set of fault IDs from a list of ``FaultCandidate``."""
    return {c.fault_id for c in candidates}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLoosenessSubHarmonics:
    """Verify that Fault #6 (Mechanical Looseness) fires for each accepted
    sub-harmonic type and does NOT fire when no sub-harmonic is present."""

    def test_looseness_with_half_subharmonic(self) -> None:
        """0.5X sub-harmonic (15 Hz) should trigger Fault #6."""
        signal = _make_looseness_signal(sub_harmonic_ratio=0.5)
        params = MachineParameters(sampling_rate=FS, rpm=RPM)

        analyzer = Tier1Analyzer()
        candidates = analyzer.analyze(signal, params)

        assert 6 in _fault_ids(candidates), (
            f"Expected Fault #6 (Looseness) with 0.5X sub-harmonic; "
            f"got fault IDs {_fault_ids(candidates)}"
        )

    def test_looseness_with_third_subharmonic(self) -> None:
        """1/3X sub-harmonic (10 Hz) should trigger Fault #6."""
        signal = _make_looseness_signal(sub_harmonic_ratio=1.0 / 3.0)
        params = MachineParameters(sampling_rate=FS, rpm=RPM)

        analyzer = Tier1Analyzer()
        candidates = analyzer.analyze(signal, params)

        assert 6 in _fault_ids(candidates), (
            f"Expected Fault #6 (Looseness) with 1/3X sub-harmonic; "
            f"got fault IDs {_fault_ids(candidates)}"
        )

    def test_looseness_with_quarter_subharmonic(self) -> None:
        """1/4X sub-harmonic (7.5 Hz) should trigger Fault #6."""
        signal = _make_looseness_signal(sub_harmonic_ratio=0.25)
        params = MachineParameters(sampling_rate=FS, rpm=RPM)

        analyzer = Tier1Analyzer()
        candidates = analyzer.analyze(signal, params)

        assert 6 in _fault_ids(candidates), (
            f"Expected Fault #6 (Looseness) with 1/4X sub-harmonic; "
            f"got fault IDs {_fault_ids(candidates)}"
        )

    def test_looseness_no_subharmonic_fails(self) -> None:
        """Without any sub-harmonic, Fault #6 must NOT be reported."""
        signal = _make_looseness_signal(sub_harmonic_ratio=None)
        params = MachineParameters(sampling_rate=FS, rpm=RPM)

        analyzer = Tier1Analyzer()
        candidates = analyzer.analyze(signal, params)

        assert 6 not in _fault_ids(candidates), (
            f"Fault #6 (Looseness) should not fire without sub-harmonics; "
            f"got fault IDs {_fault_ids(candidates)}"
        )
