"""Tier 3 analyzer -- electrical fault diagnosis.

Requires RPM, pole_pairs, and line_frequency.  Analyses the FFT spectrum
for electromagnetic signatures characteristic of induction-motor faults.

Diagnosed faults
-----------------
=====  ================================  =========================================
 ID    Name                              Key spectral signature
=====  ================================  =========================================
 8     Air Gap Eccentricity              2FL peak + pole-pass (Fp) sidebands
 14/15 Broken Rotor Bar / End Ring       1X +/- Fp sidebands (merged)
 10/13 Stator Electrical (Phase/Winding) 2FL elevated, NO 1X +/- Fp sidebands
=====  ================================  =========================================
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

from vibfault.analyzers._helpers import check_sidebands, find_peak_near
from vibfault.analyzers.protocol import FaultCandidate
from vibfault.core.frequencies import (
    electrical_2fl,
    electrical_pole_pass_freq,
    electrical_rbpf,
)
from vibfault.core.models import Evidence
from vibfault.core.preprocessing import apply_window, compute_fft, detrend

if TYPE_CHECKING:
    from vibfault.core.models import MachineParameters

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MIN_CONFIDENCE: float = 0.3
_AUTO_RPM_PENALTY: float = 0.7
_NOISE_SIGMA: float = 3.0


# ---------------------------------------------------------------------------
# Tier 3 Analyzer
# ---------------------------------------------------------------------------


class Tier3Analyzer:
    """Electrical fault diagnosis via FFT spectrum analysis.

    Implements the :class:`~vibfault.analyzers.protocol.Analyzer` protocol.

    Requires:
        * RPM (shaft speed)
        * pole_pairs (number of motor pole pairs)
        * line_frequency (AC supply frequency, e.g. 50 or 60 Hz)
    """

    def prerequisites(self) -> list[str]:
        return ["rpm", "pole_pairs", "line_frequency"]

    def can_run(self, params: MachineParameters) -> bool:
        return (
            params.rpm is not None
            and params.pole_pairs is not None
            and params.line_frequency is not None
        )

    def analyze(
        self,
        signal: np.ndarray,
        params: MachineParameters,
    ) -> list[FaultCandidate]:
        """Run Tier 3 electrical fault analysis.

        Parameters
        ----------
        signal : np.ndarray
            1-D acceleration signal.
        params : MachineParameters
            Must have rpm, pole_pairs, and line_frequency set.

        Returns
        -------
        list[FaultCandidate]
            Electrical fault candidates.
        """
        assert params.rpm is not None
        assert params.pole_pairs is not None
        assert params.line_frequency is not None

        shaft_freq = params.rpm / 60.0
        line_freq = params.line_frequency
        pole_pairs = params.pole_pairs

        auto_estimated = params.rpm_source == "auto_estimated"
        tol = 0.05 if auto_estimated else 0.03
        confidence_scale = _AUTO_RPM_PENALTY if auto_estimated else 1.0

        # Characteristic frequencies
        f_2fl = electrical_2fl(line_freq)
        f_pole_pass = electrical_pole_pass_freq(line_freq, pole_pairs, shaft_freq)

        logger.info(
            "Tier 3 electrical frequencies: 2FL=%.2f Hz, Fp=%.4f Hz "
            "(shaft=%.2f Hz, line=%.1f Hz, poles=%d)",
            f_2fl,
            f_pole_pass,
            shaft_freq,
            line_freq,
            pole_pairs,
        )

        # Compute FFT
        processed = apply_window(detrend(signal))
        freqs, amps = compute_fft(processed, params.sampling_rate)

        # Noise floor
        mean_amp = float(np.mean(amps))
        std_amp = float(np.std(amps))
        noise_floor = mean_amp + _NOISE_SIGMA * std_amp

        candidates: list[FaultCandidate] = []

        # --- Fault #8: Air Gap Eccentricity -----------------------------------
        c8 = self._check_air_gap_eccentricity(
            freqs, amps, f_2fl, f_pole_pass, noise_floor, tol, confidence_scale
        )
        if c8 is not None:
            candidates.append(c8)

        # --- Fault #14/#15: Broken Rotor Bar / End Ring (merged) ---------------
        c14 = self._check_broken_rotor_bar(
            freqs,
            amps,
            shaft_freq,
            f_pole_pass,
            params.n_bars,
            noise_floor,
            tol,
            confidence_scale,
        )
        if c14 is not None:
            candidates.append(c14)

        # --- Fault #10/#13: Stator Electrical (merged) -------------------------
        # Only emit if rotor-bar was NOT detected (discriminator)
        has_rotor_fault = c14 is not None
        c10 = self._check_stator_electrical(
            freqs, amps, f_2fl, shaft_freq, f_pole_pass, noise_floor,
            tol, confidence_scale, has_rotor_fault,
        )
        if c10 is not None:
            candidates.append(c10)

        candidates.sort(key=lambda c: c.confidence, reverse=True)

        logger.info(
            "Tier 3 complete: %d electrical fault candidate(s) detected.",
            len(candidates),
        )
        return candidates

    # ------------------------------------------------------------------
    # Fault-specific checks
    # ------------------------------------------------------------------

    @staticmethod
    def _check_air_gap_eccentricity(
        freqs: np.ndarray,
        amps: np.ndarray,
        f_2fl: float,
        f_pole_pass: float,
        noise_floor: float,
        tolerance: float,
        confidence_scale: float,
    ) -> FaultCandidate | None:
        """Fault 8: Air Gap Eccentricity.

        Conditions:
            - 2FL peak present and above noise floor
            - Pole-pass (Fp) sidebands around 2FL
        """
        peak_2fl = find_peak_near(freqs, amps, f_2fl, tolerance)
        if peak_2fl is None or peak_2fl[1] <= noise_floor:
            return None

        # Look for Fp sidebands around 2FL
        fp_sidebands = check_sidebands(
            freqs,
            amps,
            centre_freq=peak_2fl[0],
            sideband_spacing=f_pole_pass,
            tolerance=tolerance,
            min_prominence_ratio=1.5,
        )

        # Filter noise-level sidebands: must be at least 1% of 2FL amplitude
        min_sb_amp = 0.01 * peak_2fl[1]
        fp_sidebands = [(lbl, f, a) for lbl, f, a in fp_sidebands if a >= min_sb_amp]

        if not fp_sidebands:
            return None

        evidence: list[Evidence] = [
            Evidence(
                feature_name="2FL_peak",
                observed_value=peak_2fl[0],
                expected_range=(f_2fl * (1 - tolerance), f_2fl * (1 + tolerance)),
                match_score=1.0 - abs(peak_2fl[0] - f_2fl) / f_2fl,
                description=(
                    f"2FL peak at {peak_2fl[0]:.2f} Hz "
                    f"(expected {f_2fl:.2f} Hz), amplitude {peak_2fl[1]:.4f}"
                ),
            ),
        ]

        for sb_label, sb_freq, sb_amp in fp_sidebands:
            evidence.append(
                Evidence(
                    feature_name=f"2FL_Fp_sideband_{sb_label}",
                    observed_value=sb_freq,
                    expected_range=(
                        peak_2fl[0] - f_pole_pass * 1.1,
                        peak_2fl[0] + f_pole_pass * 1.1,
                    ),
                    match_score=0.9,
                    description=(
                        f"Fp sideband ({sb_label}) at {sb_freq:.2f} Hz "
                        f"around 2FL, amplitude {sb_amp:.4f}"
                    ),
                )
            )

        confidence = 0.80 * confidence_scale

        return FaultCandidate(
            fault_id=8,
            fault_name="Air Gap Eccentricity",
            fault_category="electrical",
            confidence=confidence,
            diagnosis_type="S",
            evidence=evidence,
        )

    @staticmethod
    def _check_broken_rotor_bar(
        freqs: np.ndarray,
        amps: np.ndarray,
        shaft_freq: float,
        f_pole_pass: float,
        n_bars: int | None,
        noise_floor: float,
        tolerance: float,
        confidence_scale: float,
    ) -> FaultCandidate | None:
        """Faults 14/15: Broken Rotor Bar / End Ring (merged).

        Conditions:
            - 1X +/- Fp sidebands present (pole-pass sidebands around shaft freq)
            - Optional: RBPF sidebands if n_bars provided (boosts confidence)
        """
        # Check for 1X peak first
        peak_1x = find_peak_near(freqs, amps, shaft_freq, tolerance)
        if peak_1x is None or peak_1x[1] <= noise_floor:
            return None

        # Look for Fp sidebands around 1X
        fp_sidebands_1x = check_sidebands(
            freqs,
            amps,
            centre_freq=peak_1x[0],
            sideband_spacing=f_pole_pass,
            tolerance=tolerance,
            min_prominence_ratio=1.5,
        )

        if not fp_sidebands_1x:
            return None

        evidence: list[Evidence] = []
        for sb_label, sb_freq, sb_amp in fp_sidebands_1x:
            evidence.append(
                Evidence(
                    feature_name=f"1X_Fp_sideband_{sb_label}",
                    observed_value=sb_freq,
                    expected_range=(
                        peak_1x[0] - f_pole_pass * 1.1,
                        peak_1x[0] + f_pole_pass * 1.1,
                    ),
                    match_score=0.9,
                    description=(
                        f"Fp sideband ({sb_label}) at {sb_freq:.2f} Hz "
                        f"around 1X, amplitude {sb_amp:.4f}"
                    ),
                )
            )

        confidence = 0.75

        # Optional enhancement: RBPF sidebands
        if n_bars is not None:
            rbpf = electrical_rbpf(n_bars, shaft_freq)
            peak_rbpf = find_peak_near(freqs, amps, rbpf, tolerance)
            if peak_rbpf is not None and peak_rbpf[1] > noise_floor:
                confidence = 0.80
                evidence.append(
                    Evidence(
                        feature_name="RBPF_peak",
                        observed_value=peak_rbpf[0],
                        expected_range=(
                            rbpf * (1 - tolerance),
                            rbpf * (1 + tolerance),
                        ),
                        match_score=1.0 - abs(peak_rbpf[0] - rbpf) / rbpf,
                        description=(
                            f"RBPF peak at {peak_rbpf[0]:.2f} Hz "
                            f"(expected {rbpf:.2f} Hz), amplitude {peak_rbpf[1]:.4f}"
                        ),
                    )
                )

        confidence *= confidence_scale

        return FaultCandidate(
            fault_id=14,
            fault_name="Broken Rotor Bar / End Ring",
            fault_category="electrical",
            confidence=confidence,
            diagnosis_type="M",
            evidence=evidence,
            merged_with=[15],
        )

    @staticmethod
    def _check_stator_electrical(
        freqs: np.ndarray,
        amps: np.ndarray,
        f_2fl: float,
        shaft_freq: float,
        f_pole_pass: float,
        noise_floor: float,
        tolerance: float,
        confidence_scale: float,
        has_rotor_fault: bool,
    ) -> FaultCandidate | None:
        """Faults 10/13: Stator Electrical -- Phase Problem / Winding Short (merged).

        Conditions:
            - 2FL peak elevated above noise floor
            - Absence of 1X +/- Fp sidebands (discriminator from rotor faults)
        """
        # If rotor fault was already detected, the 2FL peak is more likely
        # attributable to the rotor issue; skip stator diagnosis.
        if has_rotor_fault:
            return None

        peak_2fl = find_peak_near(freqs, amps, f_2fl, tolerance)
        if peak_2fl is None or peak_2fl[1] <= noise_floor:
            return None

        # Discriminator: check that there are NO prominent Fp sidebands around 1X
        # Only meaningful when 1X itself is above the noise floor.
        peak_1x = find_peak_near(freqs, amps, shaft_freq, tolerance)
        if peak_1x is not None and peak_1x[1] > noise_floor:
            fp_sidebands_1x = check_sidebands(
                freqs,
                amps,
                centre_freq=peak_1x[0],
                sideband_spacing=f_pole_pass,
                tolerance=tolerance,
                min_prominence_ratio=1.5,
            )
            if fp_sidebands_1x:
                # Fp sidebands around 1X suggest rotor fault, not stator
                return None

        evidence: list[Evidence] = [
            Evidence(
                feature_name="2FL_peak_stator",
                observed_value=peak_2fl[0],
                expected_range=(f_2fl * (1 - tolerance), f_2fl * (1 + tolerance)),
                match_score=1.0 - abs(peak_2fl[0] - f_2fl) / f_2fl,
                description=(
                    f"2FL peak at {peak_2fl[0]:.2f} Hz "
                    f"(expected {f_2fl:.2f} Hz), amplitude {peak_2fl[1]:.4f}"
                ),
            ),
            Evidence(
                feature_name="no_1X_Fp_sidebands",
                observed_value=0.0,
                expected_range=(0.0, 0.0),
                match_score=1.0,
                description="No Fp sidebands around 1X (rules out rotor bar fault)",
            ),
        ]

        confidence = 0.65 * confidence_scale

        return FaultCandidate(
            fault_id=10,
            fault_name="Stator Electrical (Phase/Winding)",
            fault_category="electrical",
            confidence=confidence,
            diagnosis_type="M",
            evidence=evidence,
            merged_with=[13],
        )
