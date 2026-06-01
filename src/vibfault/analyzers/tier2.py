"""Tier 2 analyzer -- bearing fault diagnosis.

Requires bearing geometry (or a bearing model lookup) in addition to RPM.
Uses envelope (demodulation) analysis to detect characteristic defect
frequencies:

* **Fault 4** -- Inner Race defect (BPFI)
* **Fault 5** -- Outer Race defect (BPFO)
* **Fault 7** -- Ball (rolling element) defect (BSF)

Confidence is reduced when the RPM source is ``"auto_estimated"`` because
the characteristic-frequency calculations are sensitive to shaft speed
accuracy.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

from vibfault.analyzers._helpers import check_sidebands, find_harmonics_in_spectrum
from vibfault.analyzers.protocol import FaultCandidate
from vibfault.core.frequencies import (
    bearing_bpfi,
    bearing_bpfo,
    bearing_bsf,
    bearing_ftf,
)
from vibfault.core.models import BearingGeometry, Evidence
from vibfault.core.preprocessing import (
    apply_window,
    compute_envelope,
    compute_kurtogram,
    detrend,
)

if TYPE_CHECKING:
    from vibfault.core.models import MachineParameters

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tier 2 Analyzer
# ---------------------------------------------------------------------------


class Tier2Analyzer:
    """Bearing fault diagnosis via envelope spectrum analysis.

    Implements the :class:`~vibfault.analyzers.protocol.Analyzer` protocol.

    Requires:
        * RPM (shaft speed) -- from manual entry, tachometer, or auto-estimation.
        * Bearing geometry -- explicit :class:`BearingGeometry` or a model string
          that can be resolved to one.

    Produces :class:`FaultCandidate` objects for inner-race, outer-race,
    and ball defects when characteristic frequency peaks are detected in
    the envelope spectrum.
    """

    # ------------------------------------------------------------------
    # Protocol methods
    # ------------------------------------------------------------------

    def prerequisites(self) -> list[str]:
        """Tier 2 requires RPM and bearing geometry."""
        return ["rpm", "bearing"]

    def can_run(self, params: MachineParameters) -> bool:
        """Return ``True`` if RPM and bearing information are available."""
        return params.rpm is not None and (
            params.bearing is not None or params.bearing_model is not None
        )

    def analyze(
        self,
        signal: np.ndarray,
        params: MachineParameters,
    ) -> list[FaultCandidate]:
        """Run envelope-based bearing fault analysis.

        Parameters
        ----------
        signal : np.ndarray
            1-D acceleration signal.
        params : MachineParameters
            Machine parameters including RPM and bearing geometry.

        Returns
        -------
        list[FaultCandidate]
            Zero or more bearing-fault candidates ranked by confidence.
        """
        # ------------------------------------------------------------------
        # 1. Derive shaft frequency and tolerance settings
        # ------------------------------------------------------------------
        assert params.rpm is not None  # guaranteed by can_run
        shaft_freq = params.rpm / 60.0

        auto_estimated = params.rpm_source == "auto_estimated"
        tol = 0.05 if auto_estimated else 0.03
        confidence_modifier = 0.7 if auto_estimated else 1.0

        # ------------------------------------------------------------------
        # 2. Resolve bearing geometry
        # ------------------------------------------------------------------
        bearing = self._resolve_bearing(params)
        if bearing is None:
            logger.warning("Could not resolve bearing geometry; skipping Tier 2.")
            return []

        # ------------------------------------------------------------------
        # 3. Calculate characteristic frequencies
        # ------------------------------------------------------------------
        bpfi = bearing_bpfi(
            bearing.n_balls,
            bearing.ball_diameter,
            bearing.pitch_diameter,
            bearing.contact_angle,
            shaft_freq,
        )
        bpfo = bearing_bpfo(
            bearing.n_balls,
            bearing.ball_diameter,
            bearing.pitch_diameter,
            bearing.contact_angle,
            shaft_freq,
        )
        bsf = bearing_bsf(
            bearing.ball_diameter,
            bearing.pitch_diameter,
            bearing.contact_angle,
            shaft_freq,
        )
        ftf = bearing_ftf(
            bearing.ball_diameter,
            bearing.pitch_diameter,
            bearing.contact_angle,
            shaft_freq,
        )

        logger.info(
            "Bearing characteristic frequencies: BPFI=%.2f Hz, BPFO=%.2f Hz, "
            "BSF=%.2f Hz, FTF=%.2f Hz  (shaft=%.2f Hz, tol=%.0f%%)",
            bpfi,
            bpfo,
            bsf,
            ftf,
            shaft_freq,
            tol * 100,
        )

        # ------------------------------------------------------------------
        # 4. Compute envelope spectrum (with optional kurtogram band selection)
        # ------------------------------------------------------------------
        preprocessed = detrend(signal)
        preprocessed = apply_window(preprocessed)

        # Optionally use kurtogram to auto-select optimal demodulation band.
        # Only activated when signal is long enough AND kurtosis is strongly
        # elevated (>5.0), indicating genuine impulsive content like bearing
        # defects.  A full-band envelope is always computed as the primary
        # analysis path; the kurtogram band is used as a secondary refinement.
        env_freqs, env_amps = compute_envelope(preprocessed, params.sampling_rate)

        min_samples_kurtogram = 4096
        if preprocessed.size >= min_samples_kurtogram:
            try:
                center, bw, kurt = compute_kurtogram(
                    preprocessed,
                    params.sampling_rate,
                    levels=6,
                )
                if kurt > 5.0:
                    kurto_band = (
                        max(1.0, center - bw / 2.0),
                        center + bw / 2.0,
                    )
                    logger.info(
                        "Kurtogram selected band: %.1f-%.1f Hz (kurtosis=%.2f)",
                        kurto_band[0],
                        kurto_band[1],
                        kurt,
                    )
                    # Use kurtogram-band envelope only if it has stronger peaks
                    kb_freqs, kb_amps = compute_envelope(
                        preprocessed,
                        params.sampling_rate,
                        band=kurto_band,
                    )
                    if np.max(kb_amps) > np.max(env_amps):
                        env_freqs, env_amps = kb_freqs, kb_amps
            except (ValueError, RuntimeError):
                logger.debug("Kurtogram failed; using full-band envelope.")

        # ------------------------------------------------------------------
        # 5. Search for fault signatures
        # ------------------------------------------------------------------
        candidates: list[FaultCandidate] = []

        # --- Fault 4: Inner Race (BPFI) ----------------------------------
        inner_candidate = self._check_inner_race(
            env_freqs,
            env_amps,
            bpfi,
            shaft_freq,
            tol,
            confidence_modifier,
        )
        if inner_candidate is not None:
            candidates.append(inner_candidate)

        # --- Fault 5: Outer Race (BPFO) ----------------------------------
        outer_candidate = self._check_outer_race(
            env_freqs,
            env_amps,
            bpfo,
            shaft_freq,
            tol,
            confidence_modifier,
        )
        if outer_candidate is not None:
            candidates.append(outer_candidate)

        # --- Fault 7: Ball Defect (BSF) ----------------------------------
        ball_candidate = self._check_ball_defect(
            env_freqs,
            env_amps,
            bsf,
            ftf,
            tol,
            confidence_modifier,
        )
        if ball_candidate is not None:
            candidates.append(ball_candidate)

        # Sort by descending confidence
        candidates.sort(key=lambda c: c.confidence, reverse=True)

        logger.info(
            "Tier 2 complete: %d bearing fault candidate(s) detected.",
            len(candidates),
        )
        return candidates

    # ------------------------------------------------------------------
    # Fault-specific checks
    # ------------------------------------------------------------------

    def _check_inner_race(
        self,
        freqs: np.ndarray,
        amps: np.ndarray,
        bpfi: float,
        shaft_freq: float,
        tolerance: float,
        confidence_modifier: float,
    ) -> FaultCandidate | None:
        """Fault 4: Inner Race defect (BPFI).

        Conditions:
            - BPFI peak present in envelope spectrum
            - At least 2 harmonics of BPFI detected
            - 1X sidebands (shaft frequency) around BPFI
        """
        harmonics = find_harmonics_in_spectrum(
            freqs,
            amps,
            bpfi,
            max_harmonics=5,
            tolerance=tolerance,
        )
        if not harmonics:
            return None

        # Need at least the fundamental + 1 additional harmonic (>=2 total)
        if len(harmonics) < 2:
            return None

        # Check for 1X sidebands around the BPFI fundamental
        fund_harm = harmonics[0]  # (harmonic_number, freq, amp)
        sidebands = check_sidebands(
            freqs,
            amps,
            centre_freq=fund_harm[1],
            sideband_spacing=shaft_freq,
            tolerance=tolerance,
        )

        if not sidebands:
            return None

        # Build evidence
        evidence: list[Evidence] = []
        for h_num, h_freq, h_amp in harmonics:
            expected_freq = h_num * bpfi
            evidence.append(
                Evidence(
                    feature_name=f"BPFI_{h_num}X",
                    observed_value=h_freq,
                    expected_range=(
                        expected_freq * (1.0 - tolerance),
                        expected_freq * (1.0 + tolerance),
                    ),
                    match_score=1.0 - abs(h_freq - expected_freq) / expected_freq,
                    description=(
                        f"BPFI harmonic {h_num}X at {h_freq:.2f} Hz "
                        f"(expected {expected_freq:.2f} Hz), amplitude {h_amp:.4f}"
                    ),
                )
            )

        for sb_label, sb_freq, sb_amp in sidebands:
            evidence.append(
                Evidence(
                    feature_name=f"BPFI_sideband_{sb_label}",
                    observed_value=sb_freq,
                    expected_range=(
                        fund_harm[1] - shaft_freq * 1.1,
                        fund_harm[1] + shaft_freq * 1.1,
                    ),
                    match_score=0.9,
                    description=(
                        f"1X sideband ({sb_label}) at {sb_freq:.2f} Hz "
                        f"around BPFI, amplitude {sb_amp:.4f}"
                    ),
                )
            )

        confidence = 0.85 * confidence_modifier

        logger.debug(
            "Fault 4 (Inner Race): %d harmonics, %d sidebands, conf=%.3f",
            len(harmonics),
            len(sidebands),
            confidence,
        )

        return FaultCandidate(
            fault_id=4,
            fault_name="Inner Race Defect (BPFI)",
            fault_category="bearing",
            confidence=confidence,
            diagnosis_type="S",
            evidence=evidence,
        )

    def _check_outer_race(
        self,
        freqs: np.ndarray,
        amps: np.ndarray,
        bpfo: float,
        shaft_freq: float,
        tolerance: float,
        confidence_modifier: float,
    ) -> FaultCandidate | None:
        """Fault 5: Outer Race defect (BPFO).

        Conditions:
            - BPFO peak present in envelope spectrum
            - At least 2 harmonics of BPFO detected
            - Typically NO prominent 1X sidebands (distinguishes from inner race)
        """
        harmonics = find_harmonics_in_spectrum(
            freqs,
            amps,
            bpfo,
            max_harmonics=5,
            tolerance=tolerance,
        )
        if not harmonics:
            return None

        if len(harmonics) < 2:
            return None

        # Check for absence of prominent 1X sidebands (outer race hallmark).
        # We still check, but if sidebands ARE present, we reduce confidence.
        fund_harm = harmonics[0]
        sidebands = check_sidebands(
            freqs,
            amps,
            centre_freq=fund_harm[1],
            sideband_spacing=shaft_freq,
            tolerance=tolerance,
        )

        # Build evidence
        evidence: list[Evidence] = []
        for h_num, h_freq, h_amp in harmonics:
            expected_freq = h_num * bpfo
            evidence.append(
                Evidence(
                    feature_name=f"BPFO_{h_num}X",
                    observed_value=h_freq,
                    expected_range=(
                        expected_freq * (1.0 - tolerance),
                        expected_freq * (1.0 + tolerance),
                    ),
                    match_score=1.0 - abs(h_freq - expected_freq) / expected_freq,
                    description=(
                        f"BPFO harmonic {h_num}X at {h_freq:.2f} Hz "
                        f"(expected {expected_freq:.2f} Hz), amplitude {h_amp:.4f}"
                    ),
                )
            )

        confidence = 0.85 * confidence_modifier

        # Outer race faults typically lack prominent sidebands.
        # If sidebands are found, reduce confidence slightly as this is
        # more characteristic of inner-race faults.
        if sidebands:
            sideband_penalty = 0.10
            confidence *= 1.0 - sideband_penalty
            for sb_label, sb_freq, sb_amp in sidebands:
                evidence.append(
                    Evidence(
                        feature_name=f"BPFO_unexpected_sideband_{sb_label}",
                        observed_value=sb_freq,
                        expected_range=(
                            fund_harm[1] - shaft_freq * 1.1,
                            fund_harm[1] + shaft_freq * 1.1,
                        ),
                        match_score=0.5,
                        description=(
                            f"Unexpected 1X sideband ({sb_label}) at {sb_freq:.2f} Hz "
                            f"around BPFO (reduces BPFO confidence), amplitude {sb_amp:.4f}"
                        ),
                    )
                )

        logger.debug(
            "Fault 5 (Outer Race): %d harmonics, %d sidebands, conf=%.3f",
            len(harmonics),
            len(sidebands),
            confidence,
        )

        return FaultCandidate(
            fault_id=5,
            fault_name="Outer Race Defect (BPFO)",
            fault_category="bearing",
            confidence=confidence,
            diagnosis_type="S",
            evidence=evidence,
        )

    def _check_ball_defect(
        self,
        freqs: np.ndarray,
        amps: np.ndarray,
        bsf: float,
        ftf: float,
        tolerance: float,
        confidence_modifier: float,
    ) -> FaultCandidate | None:
        """Fault 7: Ball (rolling element) defect (BSF).

        Two detection paths:
            1. Classic: BSF harmonics + FTF sidebands -> confidence 0.70
            2. Sideband-only: BSF fundamental (relaxed) + FTF sidebands,
               no harmonics required -> confidence 0.55
               (PPTX spec: BSF is "No Harmonics, Yes Sidebands")
        """
        harmonics = find_harmonics_in_spectrum(
            freqs,
            amps,
            bsf,
            max_harmonics=3,
            tolerance=tolerance,
        )

        # Try to find BSF fundamental even with relaxed prominence
        bsf_peak = None
        if harmonics:
            bsf_peak = harmonics[0]
        else:
            # Relaxed search: look for BSF fundamental with lower prominence
            relaxed_harmonics = find_harmonics_in_spectrum(
                freqs,
                amps,
                bsf,
                max_harmonics=1,
                tolerance=tolerance,
                min_prominence_ratio=1.5,
            )
            if relaxed_harmonics:
                bsf_peak = relaxed_harmonics[0]

        if bsf_peak is None:
            return None

        # Check for FTF sidebands around the BSF fundamental
        ftf_sidebands = check_sidebands(
            freqs,
            amps,
            centre_freq=bsf_peak[1],
            sideband_spacing=ftf,
            tolerance=tolerance,
        )

        if not ftf_sidebands:
            return None

        # Determine detection path
        has_harmonics = len(harmonics) >= 2
        sideband_only = not has_harmonics

        # Build evidence
        evidence: list[Evidence] = []
        detected_harmonics = harmonics if harmonics else [bsf_peak]
        for h_num, h_freq, h_amp in detected_harmonics:
            expected_freq = h_num * bsf
            evidence.append(
                Evidence(
                    feature_name=f"BSF_{h_num}X",
                    observed_value=h_freq,
                    expected_range=(
                        expected_freq * (1.0 - tolerance),
                        expected_freq * (1.0 + tolerance),
                    ),
                    match_score=1.0 - abs(h_freq - expected_freq) / expected_freq,
                    description=(
                        f"BSF harmonic {h_num}X at {h_freq:.2f} Hz "
                        f"(expected {expected_freq:.2f} Hz), amplitude {h_amp:.4f}"
                    ),
                )
            )

        for sb_label, sb_freq, sb_amp in ftf_sidebands:
            evidence.append(
                Evidence(
                    feature_name=f"BSF_FTF_sideband_{sb_label}",
                    observed_value=sb_freq,
                    expected_range=(
                        bsf_peak[1] - ftf * 1.1,
                        bsf_peak[1] + ftf * 1.1,
                    ),
                    match_score=0.9,
                    description=(
                        f"FTF sideband ({sb_label}) at {sb_freq:.2f} Hz "
                        f"around BSF, amplitude {sb_amp:.4f}"
                    ),
                )
            )

        if sideband_only:
            evidence.append(
                Evidence(
                    feature_name="BSF_sideband_only",
                    observed_value=1.0,
                    expected_range=(0.0, 1.0),
                    match_score=0.7,
                    description="Sideband-only detection pattern (no BSF harmonics)",
                )
            )

        # Classic path: 0.70, sideband-only: 0.55
        confidence = (0.55 if sideband_only else 0.70) * confidence_modifier

        logger.debug(
            "Fault 7 (Ball Defect): %d harmonics, %d FTF sidebands, sideband_only=%s, conf=%.3f",
            len(harmonics),
            len(ftf_sidebands),
            sideband_only,
            confidence,
        )

        return FaultCandidate(
            fault_id=7,
            fault_name="Ball Defect (BSF)",
            fault_category="bearing",
            confidence=confidence,
            diagnosis_type="S",
            evidence=evidence,
        )

    # ------------------------------------------------------------------
    # Bearing resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_bearing(params: MachineParameters) -> BearingGeometry | None:
        """Return the bearing geometry from *params*, resolving model lookups.

        If ``params.bearing`` is already populated, it is returned directly.
        If only ``params.bearing_model`` is set, a lookup is attempted (currently
        a placeholder that logs a warning and returns ``None``).

        Returns
        -------
        BearingGeometry or None
            Resolved geometry, or ``None`` if resolution failed.
        """
        if params.bearing is not None:
            return params.bearing

        if params.bearing_model is not None:
            # TODO: implement bearing model database lookup
            logger.warning(
                "Bearing model lookup for %r is not yet implemented.",
                params.bearing_model,
            )
            return None

        return None
