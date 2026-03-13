"""Tier 1 analyzer -- RPM-based vibration fault diagnosis.

Requires a known shaft speed (RPM).  Extracts order-based features
(1X, 2X, ... nX amplitudes relative to shaft frequency) from the FFT
spectrum and matches them against a set of deterministic fault rules.

Diagnosed faults
-----------------
=====  ========================  ========================================
 ID    Name                      Key spectral signature
=====  ========================  ========================================
 1     Unbalance                 1X dominant, low harmonic content
 2     Bent Shaft                Elevated 1X *and* 2X (ratio > 0.5)
 3     Parallel Misalignment     2X dominant
 9     Angular Misalignment      Elevated 1X (partial without axial data)
 6     Mechanical Looseness      >= 5 harmonics + 0.5X sub-harmonic
 11    Oil Whirl / Whip          Sub-synchronous peak at 0.35X -- 0.50X
=====  ========================  ========================================
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

from vibfault.analyzers._helpers import find_peak_near
from vibfault.analyzers.protocol import FaultCandidate
from vibfault.core.preprocessing import apply_window, compute_fft, detrend

if TYPE_CHECKING:
    from vibfault.core.models import Evidence, MachineParameters

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_TOLERANCE: float = 0.03
"""Fractional tolerance (±3 %) used when searching for peaks near order
frequencies."""

_NOISE_SIGMA: float = 3.0
"""A harmonic is considered 'above the noise floor' when its amplitude
exceeds ``mean + _NOISE_SIGMA * std`` of the full spectrum."""

_MIN_CONFIDENCE: float = 0.3
"""Candidates with confidence below this threshold are discarded."""

_AUTO_RPM_PENALTY: float = 0.7
"""Multiplicative penalty applied to all confidences when the RPM was
obtained via automatic estimation rather than a tachometer or manual entry."""


# ---------------------------------------------------------------------------
# Helper: extract order-based features
# ---------------------------------------------------------------------------


def extract_order_features(
    freqs: np.ndarray,
    amps: np.ndarray,
    rpm: float,
    max_order: int = 10,
) -> dict[str, object]:
    """Extract order-based (synchronous) features from an FFT spectrum.

    Parameters
    ----------
    freqs : np.ndarray
        Frequency axis (Hz) of the single-sided FFT.
    amps : np.ndarray
        Amplitude spectrum corresponding to *freqs*.
    rpm : float
        Shaft rotational speed in revolutions per minute.
    max_order : int
        Highest harmonic order to extract (default ``10``).

    Returns
    -------
    dict[str, object]
        Feature dictionary with the following keys:

        * ``shaft_freq`` -- shaft frequency in Hz (rpm / 60).
        * ``1X_amplitude`` -- amplitude at 1x shaft frequency.
        * ``2X_amplitude`` -- amplitude at 2x shaft frequency.
        * ``nX_amplitudes`` -- list of amplitudes from 1X to *max_order* X.
        * ``1X_is_dominant`` -- whether 1X is the largest peak in 0--10X.
        * ``2X_is_dominant`` -- whether 2X is the largest peak in 0--10X.
        * ``2X_to_1X_ratio`` -- ratio of the 2X to 1X amplitude.
        * ``harmonic_count`` -- number of harmonics above the noise floor.
        * ``sub_harmonic_present`` -- 0.5X peak detected.
        * ``sub_sync_peak_present`` -- any peak between 0.35X and 0.50X.
        * ``sub_sync_frequency_ratio`` -- freq / shaft_freq for the
          strongest sub-synchronous peak (``0.0`` if none found).
    """
    shaft_freq: float = rpm / 60.0

    # --- Amplitudes at each harmonic order -----------------------------------
    nx_amplitudes: list[float] = []
    for order in range(1, max_order + 1):
        result = find_peak_near(freqs, amps, shaft_freq * order)
        nx_amplitudes.append(result[1] if result is not None else 0.0)

    amp_1x: float = nx_amplitudes[0]
    amp_2x: float = nx_amplitudes[1] if len(nx_amplitudes) > 1 else 0.0

    # --- Dominance checks (within 0 -- max_order * shaft_freq range) ---------
    max_amp = max(nx_amplitudes) if nx_amplitudes else 0.0
    is_1x_dominant: bool = (amp_1x > 0.0) and (amp_1x >= max_amp)
    is_2x_dominant: bool = (amp_2x > 0.0) and (amp_2x >= max_amp)

    # --- 2X / 1X ratio -------------------------------------------------------
    ratio_2x_1x: float = (amp_2x / amp_1x) if amp_1x > 1e-12 else 0.0

    # --- Noise floor (mean + _NOISE_SIGMA * std of the full spectrum) --------
    mean_amp: float = float(np.mean(amps))
    std_amp: float = float(np.std(amps))
    noise_floor: float = mean_amp + _NOISE_SIGMA * std_amp
    harmonic_count: int = sum(1 for a in nx_amplitudes if a > noise_floor)

    # --- Sub-harmonics at 0.5X, 1/3X, 1/4X ----------------------------------
    sub_half = find_peak_near(freqs, amps, shaft_freq * 0.5)
    sub_harmonic_present: bool = sub_half is not None and sub_half[1] > noise_floor

    sub_third = find_peak_near(freqs, amps, shaft_freq / 3.0)
    sub_third_harmonic_present: bool = sub_third is not None and sub_third[1] > noise_floor

    sub_quarter = find_peak_near(freqs, amps, shaft_freq * 0.25)
    sub_quarter_harmonic_present: bool = sub_quarter is not None and sub_quarter[1] > noise_floor

    # --- Sub-synchronous peaks (0.35X -- 0.50X) ------------------------------
    low_sub = shaft_freq * 0.35
    high_sub = shaft_freq * 0.50
    sub_mask = (freqs >= low_sub) & (freqs <= high_sub)
    sub_sync_peak_present: bool = False
    sub_sync_frequency_ratio: float = 0.0
    if np.any(sub_mask):
        sub_idx = int(np.argmax(amps[sub_mask]))
        sub_peak_amp = float(amps[sub_mask][sub_idx])
        if sub_peak_amp > noise_floor:
            sub_sync_peak_present = True
            sub_sync_frequency_ratio = float(freqs[sub_mask][sub_idx]) / shaft_freq

    return {
        "shaft_freq": shaft_freq,
        "1X_amplitude": amp_1x,
        "2X_amplitude": amp_2x,
        "nX_amplitudes": nx_amplitudes,
        "1X_is_dominant": is_1x_dominant,
        "2X_is_dominant": is_2x_dominant,
        "2X_to_1X_ratio": ratio_2x_1x,
        "harmonic_count": harmonic_count,
        "sub_harmonic_present": sub_harmonic_present,
        "sub_third_harmonic_present": sub_third_harmonic_present,
        "sub_quarter_harmonic_present": sub_quarter_harmonic_present,
        "sub_sync_peak_present": sub_sync_peak_present,
        "sub_sync_frequency_ratio": sub_sync_frequency_ratio,
    }


# ---------------------------------------------------------------------------
# Evidence factory
# ---------------------------------------------------------------------------


def _evidence(
    feature_name: str,
    observed: float,
    expected: tuple[float, float],
    score: float,
    description: str,
) -> Evidence:
    """Convenience constructor that avoids an import at module level."""
    from vibfault.core.models import Evidence

    return Evidence(
        feature_name=feature_name,
        observed_value=observed,
        expected_range=expected,
        match_score=min(max(score, 0.0), 1.0),
        description=description,
    )


# ---------------------------------------------------------------------------
# Fault-rule evaluation helpers
# ---------------------------------------------------------------------------


def _check_unbalance(features: dict[str, object]) -> FaultCandidate | None:
    """Fault 1 -- Unbalance.

    Conditions:
      - 1X is dominant among the first 10 harmonics.
      - 1X carries more than 60 % of the total energy in the 0--5X band.
      - 2X / 1X ratio is less than 0.5.

    Base confidence: 0.85.
    """
    if not features["1X_is_dominant"]:
        return None

    nx: list[float] = features["nX_amplitudes"]  # type: ignore[assignment]
    energy_0_5x = sum(a**2 for a in nx[:5])
    amp_1x: float = features["1X_amplitude"]  # type: ignore[assignment]
    energy_1x = amp_1x**2
    energy_fraction = energy_1x / energy_0_5x if energy_0_5x > 1e-12 else 0.0

    if energy_fraction <= 0.60:
        return None

    ratio: float = features["2X_to_1X_ratio"]  # type: ignore[assignment]
    if ratio >= 0.5:
        return None

    evidence = [
        _evidence("1X_is_dominant", 1.0, (1.0, 1.0), 1.0, "1X is the dominant peak"),
        _evidence(
            "1X_energy_fraction",
            energy_fraction,
            (0.60, 1.0),
            min(energy_fraction / 0.60, 1.0),
            f"1X carries {energy_fraction:.0%} of 0-5X energy",
        ),
        _evidence(
            "2X_to_1X_ratio",
            ratio,
            (0.0, 0.5),
            1.0 - ratio / 0.5,
            f"2X/1X ratio is {ratio:.2f} (< 0.5 expected for unbalance)",
        ),
    ]

    return FaultCandidate(
        fault_id=1,
        fault_name="Unbalance",
        fault_category="rotational",
        confidence=0.85,
        diagnosis_type="S",
        evidence=evidence,
    )


def _check_bent_shaft(features: dict[str, object]) -> FaultCandidate | None:
    """Fault 2 -- Bent Shaft.

    Conditions:
      - 1X amplitude is elevated (above noise floor, implicitly true when
        extracted as a detected peak).
      - 2X / 1X ratio > 0.5.

    Base confidence: 0.80.
    """
    amp_1x: float = features["1X_amplitude"]  # type: ignore[assignment]
    if amp_1x <= 1e-12:
        return None

    ratio: float = features["2X_to_1X_ratio"]  # type: ignore[assignment]
    if ratio <= 0.5:
        return None

    evidence = [
        _evidence(
            "1X_amplitude",
            amp_1x,
            (0.0, float("inf")),
            1.0,
            f"1X amplitude is {amp_1x:.4g}",
        ),
        _evidence(
            "2X_to_1X_ratio",
            ratio,
            (0.5, float("inf")),
            min(ratio, 1.0),
            f"2X/1X ratio is {ratio:.2f} (> 0.5 indicates bent shaft)",
        ),
    ]

    return FaultCandidate(
        fault_id=2,
        fault_name="Bent Shaft",
        fault_category="rotational",
        confidence=0.80,
        diagnosis_type="S",
        evidence=evidence,
    )


def _check_parallel_misalignment(
    features: dict[str, object],
) -> FaultCandidate | None:
    """Fault 3 -- Parallel Misalignment.

    Conditions:
      - 2X is the dominant harmonic.

    Base confidence: 0.80.
    """
    if not features["2X_is_dominant"]:
        return None

    amp_2x: float = features["2X_amplitude"]  # type: ignore[assignment]
    evidence = [
        _evidence(
            "2X_is_dominant",
            1.0,
            (1.0, 1.0),
            1.0,
            f"2X is dominant with amplitude {amp_2x:.4g}",
        ),
    ]

    return FaultCandidate(
        fault_id=3,
        fault_name="Parallel Misalignment",
        fault_category="rotational",
        confidence=0.80,
        diagnosis_type="S",
        evidence=evidence,
    )


def _check_angular_misalignment(
    features: dict[str, object],
) -> FaultCandidate | None:
    """Fault 9 -- Angular Misalignment.

    Conditions:
      - 1X amplitude is elevated.

    Without axial vibration data this is a *partial* diagnosis.  The
    confidence is kept at the base value but the evidence explicitly
    notes the limitation.

    Base confidence: 0.80.
    """
    amp_1x: float = features["1X_amplitude"]  # type: ignore[assignment]
    if amp_1x <= 1e-12:
        return None

    evidence = [
        _evidence(
            "1X_amplitude",
            amp_1x,
            (0.0, float("inf")),
            1.0,
            f"1X amplitude is {amp_1x:.4g} (elevated)",
        ),
        _evidence(
            "axial_data_available",
            0.0,
            (1.0, 1.0),
            0.0,
            "Axial vibration data not available -- diagnosis is partial",
        ),
    ]

    return FaultCandidate(
        fault_id=9,
        fault_name="Angular Misalignment",
        fault_category="rotational",
        confidence=0.80,
        diagnosis_type="S",
        evidence=evidence,
    )


def _check_looseness(features: dict[str, object]) -> FaultCandidate | None:
    """Fault 6 -- Mechanical Looseness.

    Conditions:
      - At least 5 harmonics of 1X are above the noise floor.
      - At least one sub-harmonic present: 0.5X, 1/3X, or 1/4X.

    Base confidence: 0.75.
    """
    harmonic_count: int = features["harmonic_count"]  # type: ignore[assignment]
    sub_half: bool = features["sub_harmonic_present"]  # type: ignore[assignment]
    sub_third: bool = features["sub_third_harmonic_present"]  # type: ignore[assignment]
    sub_quarter: bool = features["sub_quarter_harmonic_present"]  # type: ignore[assignment]

    any_sub = sub_half or sub_third or sub_quarter
    if harmonic_count < 5 or not any_sub:
        return None

    evidence = [
        _evidence(
            "harmonic_count",
            float(harmonic_count),
            (5.0, float("inf")),
            min(harmonic_count / 5.0, 1.0),
            f"{harmonic_count} harmonics above noise floor (>= 5 required)",
        ),
    ]

    if sub_half:
        evidence.append(
            _evidence(
                "sub_harmonic_present",
                1.0,
                (1.0, 1.0),
                1.0,
                "0.5X sub-harmonic detected",
            )
        )
    if sub_third:
        evidence.append(
            _evidence(
                "sub_third_harmonic_present",
                1.0,
                (1.0, 1.0),
                1.0,
                "1/3X sub-harmonic detected (shaft rub pattern)",
            )
        )
    if sub_quarter:
        evidence.append(
            _evidence(
                "sub_quarter_harmonic_present",
                1.0,
                (1.0, 1.0),
                1.0,
                "1/4X sub-harmonic detected (shaft rub pattern)",
            )
        )

    return FaultCandidate(
        fault_id=6,
        fault_name="Mechanical Looseness",
        fault_category="structural",
        confidence=0.75,
        diagnosis_type="S",
        evidence=evidence,
    )


def _check_oil_whirl_whip(features: dict[str, object]) -> FaultCandidate | None:
    """Faults 11/12 -- Oil Whirl / Whip (merged).

    Conditions:
      - A sub-synchronous peak exists in the 0.35X -- 0.50X range.

    Base confidence: 0.70.
    """
    if not features["sub_sync_peak_present"]:
        return None

    ratio: float = features["sub_sync_frequency_ratio"]  # type: ignore[assignment]
    evidence = [
        _evidence(
            "sub_sync_frequency_ratio",
            ratio,
            (0.35, 0.50),
            1.0,
            f"Sub-synchronous peak at {ratio:.2f}X shaft speed",
        ),
    ]

    return FaultCandidate(
        fault_id=11,
        fault_name="Oil Whirl / Whip",
        fault_category="journal_bearing",
        confidence=0.70,
        diagnosis_type="S",
        evidence=evidence,
        merged_with=[12],
    )


# Ordered list of all rule-check functions so ``analyze`` can iterate them.
_FAULT_RULES: list = [
    _check_unbalance,
    _check_bent_shaft,
    _check_parallel_misalignment,
    _check_angular_misalignment,
    _check_looseness,
    _check_oil_whirl_whip,
]


# ---------------------------------------------------------------------------
# Tier 1 Analyzer
# ---------------------------------------------------------------------------


class Tier1Analyzer:
    """RPM-based vibration fault analyzer (Tier 1).

    Extracts order-based features from the FFT spectrum using the known
    shaft speed and evaluates a set of deterministic fault rules.

    Implements the :class:`~vibfault.analyzers.protocol.Analyzer` protocol.
    """

    def prerequisites(self) -> list[str]:
        """Return the parameter names required by this analyzer."""
        return ["rpm"]

    def can_run(self, params: MachineParameters) -> bool:
        """Return ``True`` when a shaft speed is available."""
        return params.rpm is not None

    def analyze(
        self,
        signal: np.ndarray,
        params: MachineParameters,
    ) -> list[FaultCandidate]:
        """Run Tier 1 analysis on *signal*.

        Processing pipeline:

        1. Detrend and window the signal.
        2. Compute the single-sided FFT.
        3. Extract order-based features relative to shaft frequency.
        4. Evaluate each fault rule and collect candidates whose
           confidence exceeds :data:`_MIN_CONFIDENCE`.

        Parameters
        ----------
        signal : np.ndarray
            1-D acceleration time series.
        params : MachineParameters
            Machine configuration; ``params.rpm`` must not be ``None``.

        Returns
        -------
        list[FaultCandidate]
            Fault hypotheses with confidence > 0.3.
        """
        if params.rpm is None:
            logger.warning("Tier1Analyzer.analyze called without RPM; returning []")
            return []

        rpm: float = params.rpm

        # 1. Preprocessing
        processed = apply_window(detrend(signal))

        # 2. FFT
        freqs, amps = compute_fft(processed, params.sampling_rate)

        # 3. Order-based feature extraction
        features = extract_order_features(freqs, amps, rpm)

        # Store features on the instance for downstream inspection.
        self.features: dict[str, object] = features

        logger.info(
            "Tier 1 features | shaft_freq=%.2f Hz | 1X=%.4g | 2X=%.4g | "
            "2X/1X=%.3f | harmonics=%d | sub_sync=%s",
            features["shaft_freq"],
            features["1X_amplitude"],
            features["2X_amplitude"],
            features["2X_to_1X_ratio"],
            features["harmonic_count"],
            features["sub_sync_peak_present"],
        )

        # 4. Evaluate fault rules
        confidence_scale: float = (
            _AUTO_RPM_PENALTY if params.rpm_source == "auto_estimated" else 1.0
        )

        candidates: list[FaultCandidate] = []
        for rule_fn in _FAULT_RULES:
            candidate = rule_fn(features)
            if candidate is None:
                continue
            candidate.confidence *= confidence_scale
            if candidate.confidence > _MIN_CONFIDENCE:
                candidates.append(candidate)

        logger.info(
            "Tier 1 complete | %d candidate(s) emitted (rpm_source=%s, scale=%.2f)",
            len(candidates),
            params.rpm_source,
            confidence_scale,
        )

        return candidates
