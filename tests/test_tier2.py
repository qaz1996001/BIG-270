"""Tests for Tier 2 analyzer -- Ball Defect / BSF sideband-only fix (Fault #7).

Validates the two detection paths in ``_check_ball_defect``:

1. **Classic**: BSF harmonics + FTF sidebands -> confidence >= 0.65.
2. **Sideband-only**: BSF fundamental + FTF sidebands, no BSF harmonics
   -> reduced confidence (0.50-0.60) with ``sideband-only`` evidence.
3. **No sidebands**: BSF harmonics only, no FTF sidebands -> NOT detected.

Signals are constructed using amplitude modulation of a high-frequency
carrier so that the fault-frequency components appear in the *envelope*
spectrum (as computed by ``compute_envelope``).
"""

from __future__ import annotations

import numpy as np

from vibfault.analyzers.tier2 import Tier2Analyzer
from vibfault.core.frequencies import bearing_bsf, bearing_ftf
from vibfault.core.models import BearingGeometry, MachineParameters

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

FS = 8192  # Hz
RPM = 1800  # 30 Hz shaft frequency
SHAFT_FREQ = RPM / 60.0  # 30 Hz
DURATION = 2.0  # seconds -- gives 0.5 Hz frequency resolution
CARRIER_FREQ = 3000.0  # Hz -- simulated bearing resonance band

BEARING = BearingGeometry(
    n_balls=9,
    ball_diameter=7.94,
    pitch_diameter=39.04,
    contact_angle=0.0,
)

# Pre-compute characteristic frequencies for reference
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
    """Create an amplitude-modulated signal with the given modulation tones.

    The signal is constructed as::

        x(t) = cos(2*pi*f_carrier*t) * (1 + sum(m_i * cos(2*pi*f_i*t)))

    so that the *envelope spectrum* contains peaks at the modulation
    frequencies ``f_i``.

    Parameters
    ----------
    modulation_components :
        List of ``(frequency_hz, modulation_depth)`` pairs.

    Returns
    -------
    np.ndarray
        1-D time-domain signal.
    """
    t = np.arange(0, DURATION, 1.0 / FS)
    carrier = np.cos(2 * np.pi * CARRIER_FREQ * t)

    modulation = np.zeros_like(t)
    for freq, depth in modulation_components:
        modulation += depth * np.cos(2 * np.pi * freq * t)

    return carrier * (1.0 + modulation)


def _fault_ids(candidates) -> set[int]:
    """Extract the set of fault IDs from a list of ``FaultCandidate``."""
    return {c.fault_id for c in candidates}


def _get_fault(candidates, fault_id: int):
    """Return the candidate with the given fault_id, or None."""
    for c in candidates:
        if c.fault_id == fault_id:
            return c
    return None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBSFDetection:
    """Verify Ball Defect (Fault #7) detection via both classic and
    sideband-only paths, and rejection when sidebands are missing."""

    def test_bsf_classic_detection(self) -> None:
        """Classic path: BSF fundamental + 2nd harmonic + FTF sidebands.

        Expected confidence >= 0.65 (base 0.70 * 1.0 modifier).
        """
        modulation = [
            (BSF, 0.6),           # BSF fundamental
            (2 * BSF, 0.4),       # 2nd harmonic of BSF
            (BSF + FTF, 0.3),     # upper FTF sideband
            (BSF - FTF, 0.3),     # lower FTF sideband
        ]
        signal = _make_am_signal(modulation)
        params = MachineParameters(sampling_rate=FS, rpm=RPM, bearing=BEARING)

        analyzer = Tier2Analyzer()
        candidates = analyzer.analyze(signal, params)

        assert 7 in _fault_ids(candidates), (
            f"Expected Fault #7 (Ball Defect) with classic pattern; "
            f"got fault IDs {_fault_ids(candidates)}"
        )

        ball_fault = _get_fault(candidates, 7)
        assert ball_fault.confidence >= 0.65, (
            f"Classic BSF confidence should be >= 0.65, got {ball_fault.confidence:.3f}"
        )

    def test_bsf_sideband_only_detection(self) -> None:
        """Sideband-only path: BSF fundamental (low amplitude) + FTF
        sidebands, no BSF harmonics.

        Expected confidence in range 0.50 -- 0.60 (base 0.55) with
        'sideband-only' noted in evidence.
        """
        modulation = [
            (BSF, 0.25),          # BSF fundamental -- weaker, just detectable
            (BSF + FTF, 0.35),    # upper FTF sideband
            (BSF - FTF, 0.35),    # lower FTF sideband
            # No 2*BSF -- this is the sideband-only pattern
        ]
        signal = _make_am_signal(modulation)
        params = MachineParameters(sampling_rate=FS, rpm=RPM, bearing=BEARING)

        analyzer = Tier2Analyzer()
        candidates = analyzer.analyze(signal, params)

        assert 7 in _fault_ids(candidates), (
            f"Expected Fault #7 (Ball Defect) with sideband-only pattern; "
            f"got fault IDs {_fault_ids(candidates)}"
        )

        ball_fault = _get_fault(candidates, 7)
        assert 0.50 <= ball_fault.confidence <= 0.60, (
            f"Sideband-only BSF confidence should be in [0.50, 0.60], "
            f"got {ball_fault.confidence:.3f}"
        )

        # Verify that "sideband-only" is noted in the evidence
        evidence_descriptions = [e.description for e in ball_fault.evidence]
        assert any("sideband-only" in desc.lower() for desc in evidence_descriptions), (
            "Expected 'sideband-only' mention in evidence descriptions; "
            f"got: {evidence_descriptions}"
        )

    def test_bsf_no_sidebands_fails(self) -> None:
        """BSF harmonics only, no FTF sidebands -- Fault #7 must NOT fire."""
        modulation = [
            (BSF, 0.6),           # BSF fundamental
            (2 * BSF, 0.4),       # 2nd harmonic of BSF
            # No FTF sidebands at all
        ]
        signal = _make_am_signal(modulation)
        params = MachineParameters(sampling_rate=FS, rpm=RPM, bearing=BEARING)

        analyzer = Tier2Analyzer()
        candidates = analyzer.analyze(signal, params)

        assert 7 not in _fault_ids(candidates), (
            f"Fault #7 (Ball Defect) should NOT fire without FTF sidebands; "
            f"got fault IDs {_fault_ids(candidates)}"
        )
