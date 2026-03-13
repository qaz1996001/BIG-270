"""Tier 4 analyzer -- gear fault diagnosis.

Requires RPM, gear_teeth_drive, and gear_teeth_driven.  Analyses FFT spectrum,
cepstrum, and time-domain features for gear-mesh fault signatures.

Diagnosed faults
-----------------
=====  ========================  ==========================================
 ID    Name                      Key signature
=====  ========================  ==========================================
 16    Gear Misalignment         GMF + 2xGMF + asymmetric sidebands
 17    Broken Tooth              Kurtosis>4 / CF>6, GMF harmonics, cepstrum
 18    Gear Eccentricity         GMF +/- 1X symmetric sidebands + 1X elevated
 19    Gear Shaft Bend           1X + 2X elevated + GMF +/- 1X sidebands
 20    Gear Wear                 Broadband around GMF + many GMF harmonics
=====  ========================  ==========================================
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

from vibfault.analyzers._helpers import (
    check_sidebands,
    find_harmonics_in_spectrum,
    find_peak_near,
)
from vibfault.analyzers.protocol import FaultCandidate
from vibfault.core.frequencies import gear_mesh_freq
from vibfault.core.models import Evidence
from vibfault.core.preprocessing import (
    apply_window,
    compute_cepstrum,
    compute_fft,
    detrend,
    time_domain_features,
)

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
# Tier 4 Analyzer
# ---------------------------------------------------------------------------


class Tier4Analyzer:
    """Gear fault diagnosis via FFT, cepstrum, and time-domain analysis.

    Implements the :class:`~vibfault.analyzers.protocol.Analyzer` protocol.

    Requires:
        * RPM (shaft speed)
        * gear_teeth_drive (number of teeth on driving gear)
        * gear_teeth_driven (number of teeth on driven gear)
    """

    def prerequisites(self) -> list[str]:
        return ["rpm", "gear_teeth_drive", "gear_teeth_driven"]

    def can_run(self, params: MachineParameters) -> bool:
        return (
            params.rpm is not None
            and params.gear_teeth_drive is not None
            and params.gear_teeth_driven is not None
        )

    def analyze(
        self,
        signal: np.ndarray,
        params: MachineParameters,
    ) -> list[FaultCandidate]:
        """Run Tier 4 gear fault analysis.

        Parameters
        ----------
        signal : np.ndarray
            1-D acceleration signal.
        params : MachineParameters
            Must have rpm, gear_teeth_drive, and gear_teeth_driven set.

        Returns
        -------
        list[FaultCandidate]
            Gear fault candidates.
        """
        assert params.rpm is not None
        assert params.gear_teeth_drive is not None
        assert params.gear_teeth_driven is not None

        shaft_freq = params.rpm / 60.0
        gmf = gear_mesh_freq(params.gear_teeth_drive, shaft_freq)

        auto_estimated = params.rpm_source == "auto_estimated"
        tol = 0.05 if auto_estimated else 0.03
        confidence_scale = _AUTO_RPM_PENALTY if auto_estimated else 1.0

        logger.info(
            "Tier 4 gear frequencies: GMF=%.2f Hz (shaft=%.2f Hz, teeth=%d/%d)",
            gmf,
            shaft_freq,
            params.gear_teeth_drive,
            params.gear_teeth_driven,
        )

        # Compute FFT
        processed = apply_window(detrend(signal))
        freqs, amps = compute_fft(processed, params.sampling_rate)

        # Noise floor
        mean_amp = float(np.mean(amps))
        std_amp = float(np.std(amps))
        noise_floor = mean_amp + _NOISE_SIGMA * std_amp

        # Cepstrum
        quefrency, cepstrum = compute_cepstrum(signal, params.sampling_rate)

        # Time-domain features
        td_features = time_domain_features(signal)

        # GMF harmonics (shared across checks)
        gmf_harmonics = find_harmonics_in_spectrum(
            freqs, amps, gmf, max_harmonics=5, tolerance=tol,
        )

        candidates: list[FaultCandidate] = []

        # --- Fault #16: Gear Misalignment -------------------------------------
        c16 = self._check_gear_misalignment(
            freqs, amps, gmf, shaft_freq, gmf_harmonics, noise_floor,
            tol, confidence_scale,
        )
        if c16 is not None:
            candidates.append(c16)

        # --- Fault #17: Broken Tooth ------------------------------------------
        c17 = self._check_broken_tooth(
            freqs, amps, gmf, shaft_freq, gmf_harmonics, td_features,
            quefrency, cepstrum, noise_floor, tol, confidence_scale,
        )
        if c17 is not None:
            candidates.append(c17)

        # --- Fault #18: Gear Eccentricity -------------------------------------
        c18 = self._check_gear_eccentricity(
            freqs, amps, gmf, shaft_freq, gmf_harmonics, noise_floor,
            tol, confidence_scale,
        )
        if c18 is not None:
            candidates.append(c18)

        # --- Fault #19: Gear Shaft Bend ---------------------------------------
        c19 = self._check_gear_shaft_bend(
            freqs, amps, gmf, shaft_freq, noise_floor, tol, confidence_scale,
        )
        if c19 is not None:
            candidates.append(c19)

        # --- Fault #20: Gear Wear ---------------------------------------------
        c20 = self._check_gear_wear(
            freqs, amps, gmf, shaft_freq, gmf_harmonics, noise_floor,
            tol, confidence_scale,
        )
        if c20 is not None:
            candidates.append(c20)

        candidates.sort(key=lambda c: c.confidence, reverse=True)

        logger.info(
            "Tier 4 complete: %d gear fault candidate(s) detected.",
            len(candidates),
        )
        return candidates

    # ------------------------------------------------------------------
    # Fault-specific checks
    # ------------------------------------------------------------------

    @staticmethod
    def _check_gear_misalignment(
        freqs: np.ndarray,
        amps: np.ndarray,
        gmf: float,
        shaft_freq: float,
        gmf_harmonics: list[tuple[int, float, float]],
        noise_floor: float,
        tolerance: float,
        confidence_scale: float,
    ) -> FaultCandidate | None:
        """Fault 16: Gear Misalignment.

        Conditions:
            - GMF peak present
            - 2xGMF elevated
            - Sidebands around GMF asymmetric (>30% amplitude difference)
        """
        if not gmf_harmonics:
            return None

        # Need at least GMF fundamental
        gmf_fund = gmf_harmonics[0]

        # Check for 2xGMF
        has_2x_gmf = any(h[0] == 2 for h in gmf_harmonics)
        if not has_2x_gmf:
            return None

        # Check for asymmetric sidebands around GMF
        sidebands = check_sidebands(
            freqs, amps,
            centre_freq=gmf_fund[1],
            sideband_spacing=shaft_freq,
            tolerance=tolerance,
        )

        if len(sidebands) < 2:
            return None

        # Check asymmetry
        upper_amp = 0.0
        lower_amp = 0.0
        for label, _freq, amp in sidebands:
            if label.startswith("+"):
                upper_amp = max(upper_amp, amp)
            else:
                lower_amp = max(lower_amp, amp)

        max_sb = max(upper_amp, lower_amp)
        min_sb = min(upper_amp, lower_amp)
        if max_sb <= 0:
            return None
        asymmetry = (max_sb - min_sb) / max_sb
        if asymmetry < 0.30:
            return None

        evidence: list[Evidence] = [
            Evidence(
                feature_name="GMF_peak",
                observed_value=gmf_fund[1],
                expected_range=(gmf * (1 - tolerance), gmf * (1 + tolerance)),
                match_score=1.0,
                description=f"GMF at {gmf_fund[1]:.2f} Hz, amplitude {gmf_fund[2]:.4f}",
            ),
            Evidence(
                feature_name="2xGMF_present",
                observed_value=1.0,
                expected_range=(1.0, 1.0),
                match_score=1.0,
                description="2xGMF harmonic detected",
            ),
            Evidence(
                feature_name="sideband_asymmetry",
                observed_value=asymmetry,
                expected_range=(0.30, 1.0),
                match_score=min(asymmetry / 0.30, 1.0),
                description=(
                    f"Sideband asymmetry {asymmetry:.0%} "
                    f"(>30% indicates gear misalignment)"
                ),
            ),
        ]

        confidence = 0.80 * confidence_scale

        return FaultCandidate(
            fault_id=16,
            fault_name="Gear Misalignment",
            fault_category="gear",
            confidence=confidence,
            diagnosis_type="S",
            evidence=evidence,
        )

    @staticmethod
    def _check_broken_tooth(
        freqs: np.ndarray,
        amps: np.ndarray,
        gmf: float,
        shaft_freq: float,
        gmf_harmonics: list[tuple[int, float, float]],
        td_features: dict[str, float],
        quefrency: np.ndarray,
        cepstrum: np.ndarray,
        noise_floor: float,
        tolerance: float,
        confidence_scale: float,
    ) -> FaultCandidate | None:
        """Fault 17: Broken Tooth.

        Conditions:
            - Time-domain: kurtosis > 4.0 or crest_factor > 6.0
            - Multiple GMF harmonics (>=2)
            - Cepstrum rahmonic at 1/shaft_freq (gear rotation period)
        """
        kurtosis = td_features["kurtosis"]
        crest_factor = td_features["crest_factor"]

        impulsive = kurtosis > 4.0 or crest_factor > 6.0
        if not impulsive:
            return None

        if len(gmf_harmonics) < 2:
            return None

        # Check cepstrum for rahmonic at gear rotation period (1/shaft_freq)
        gear_period = 1.0 / shaft_freq if shaft_freq > 0 else 0.0
        rahmonic_found = False
        rahmonic_value = 0.0

        if gear_period > 0 and quefrency.size > 0:
            period_low = gear_period * (1.0 - tolerance)
            period_high = gear_period * (1.0 + tolerance)
            mask = (quefrency >= period_low) & (quefrency <= period_high)
            if np.any(mask):
                cepstrum_abs = np.abs(cepstrum)
                local_peak = float(np.max(cepstrum_abs[mask]))
                # Check if the rahmonic is significant
                cepstrum_median = float(np.median(cepstrum_abs[quefrency > 0]))
                if cepstrum_median > 0 and local_peak / cepstrum_median > 2.0:
                    rahmonic_found = True
                    rahmonic_value = local_peak

        evidence: list[Evidence] = [
            Evidence(
                feature_name="kurtosis",
                observed_value=kurtosis,
                expected_range=(4.0, float("inf")),
                match_score=min(kurtosis / 4.0, 1.0) if kurtosis > 4.0 else 0.5,
                description=f"Kurtosis={kurtosis:.2f} (impulsive signal)",
            ),
            Evidence(
                feature_name="crest_factor",
                observed_value=crest_factor,
                expected_range=(6.0, float("inf")),
                match_score=min(crest_factor / 6.0, 1.0) if crest_factor > 6.0 else 0.5,
                description=f"Crest factor={crest_factor:.2f}",
            ),
            Evidence(
                feature_name="GMF_harmonic_count",
                observed_value=float(len(gmf_harmonics)),
                expected_range=(2.0, float("inf")),
                match_score=min(len(gmf_harmonics) / 2.0, 1.0),
                description=f"{len(gmf_harmonics)} GMF harmonics detected",
            ),
        ]

        if rahmonic_found:
            evidence.append(
                Evidence(
                    feature_name="cepstrum_rahmonic",
                    observed_value=rahmonic_value,
                    expected_range=(0.0, float("inf")),
                    match_score=0.9,
                    description=(
                        f"Cepstrum rahmonic at gear rotation period "
                        f"({gear_period:.4f} s)"
                    ),
                )
            )

        confidence = 0.85 * confidence_scale
        if not rahmonic_found:
            confidence *= 0.85  # reduce if cepstrum doesn't confirm

        return FaultCandidate(
            fault_id=17,
            fault_name="Broken Tooth",
            fault_category="gear",
            confidence=confidence,
            diagnosis_type="S",
            evidence=evidence,
        )

    @staticmethod
    def _check_gear_eccentricity(
        freqs: np.ndarray,
        amps: np.ndarray,
        gmf: float,
        shaft_freq: float,
        gmf_harmonics: list[tuple[int, float, float]],
        noise_floor: float,
        tolerance: float,
        confidence_scale: float,
    ) -> FaultCandidate | None:
        """Fault 18: Gear Eccentricity.

        Conditions:
            - GMF +/- 1X sidebands (symmetric, both present)
            - 1X amplitude elevated
        """
        if not gmf_harmonics:
            return None

        gmf_fund = gmf_harmonics[0]

        # Check for symmetric 1X sidebands around GMF
        sidebands = check_sidebands(
            freqs, amps,
            centre_freq=gmf_fund[1],
            sideband_spacing=shaft_freq,
            tolerance=tolerance,
        )

        # Need both upper and lower sideband
        has_upper = any(label.startswith("+") for label, _, _ in sidebands)
        has_lower = any(label.startswith("-") for label, _, _ in sidebands)
        if not (has_upper and has_lower):
            return None

        # Check 1X is elevated
        peak_1x = find_peak_near(freqs, amps, shaft_freq, tolerance)
        if peak_1x is None or peak_1x[1] <= noise_floor:
            return None

        evidence: list[Evidence] = [
            Evidence(
                feature_name="GMF_1X_sidebands_symmetric",
                observed_value=float(len(sidebands)),
                expected_range=(2.0, float("inf")),
                match_score=1.0,
                description="Symmetric 1X sidebands around GMF detected",
            ),
            Evidence(
                feature_name="1X_elevated",
                observed_value=peak_1x[1],
                expected_range=(noise_floor, float("inf")),
                match_score=min(peak_1x[1] / noise_floor, 1.0),
                description=f"1X at {peak_1x[0]:.2f} Hz, amplitude {peak_1x[1]:.4f}",
            ),
        ]

        confidence = 0.75 * confidence_scale

        return FaultCandidate(
            fault_id=18,
            fault_name="Gear Eccentricity",
            fault_category="gear",
            confidence=confidence,
            diagnosis_type="S",
            evidence=evidence,
        )

    @staticmethod
    def _check_gear_shaft_bend(
        freqs: np.ndarray,
        amps: np.ndarray,
        gmf: float,
        shaft_freq: float,
        noise_floor: float,
        tolerance: float,
        confidence_scale: float,
    ) -> FaultCandidate | None:
        """Fault 19: Gear Shaft Bend.

        Conditions:
            - 1X + 2X both elevated above noise floor
            - GMF +/- 1X sidebands present
        """
        peak_1x = find_peak_near(freqs, amps, shaft_freq, tolerance)
        peak_2x = find_peak_near(freqs, amps, shaft_freq * 2.0, tolerance)

        if peak_1x is None or peak_1x[1] <= noise_floor:
            return None
        if peak_2x is None or peak_2x[1] <= noise_floor:
            return None

        # Check GMF sidebands
        peak_gmf = find_peak_near(freqs, amps, gmf, tolerance)
        if peak_gmf is None:
            return None

        sidebands = check_sidebands(
            freqs, amps,
            centre_freq=peak_gmf[0],
            sideband_spacing=shaft_freq,
            tolerance=tolerance,
        )

        if not sidebands:
            return None

        evidence: list[Evidence] = [
            Evidence(
                feature_name="1X_elevated",
                observed_value=peak_1x[1],
                expected_range=(noise_floor, float("inf")),
                match_score=min(peak_1x[1] / noise_floor, 1.0),
                description=f"1X elevated at {peak_1x[0]:.2f} Hz",
            ),
            Evidence(
                feature_name="2X_elevated",
                observed_value=peak_2x[1],
                expected_range=(noise_floor, float("inf")),
                match_score=min(peak_2x[1] / noise_floor, 1.0),
                description=f"2X elevated at {peak_2x[0]:.2f} Hz",
            ),
            Evidence(
                feature_name="GMF_1X_sidebands",
                observed_value=float(len(sidebands)),
                expected_range=(1.0, float("inf")),
                match_score=1.0,
                description=f"{len(sidebands)} sideband(s) around GMF",
            ),
        ]

        confidence = 0.70 * confidence_scale

        return FaultCandidate(
            fault_id=19,
            fault_name="Gear Shaft Bend",
            fault_category="gear",
            confidence=confidence,
            diagnosis_type="S",
            evidence=evidence,
        )

    @staticmethod
    def _check_gear_wear(
        freqs: np.ndarray,
        amps: np.ndarray,
        gmf: float,
        shaft_freq: float,
        gmf_harmonics: list[tuple[int, float, float]],
        noise_floor: float,
        tolerance: float,
        confidence_scale: float,
    ) -> FaultCandidate | None:
        """Fault 20: Gear Wear.

        Conditions:
            - Broadband energy around GMF region elevated (GMF +/- 5*shaft_freq)
            - Multiple GMF harmonics (>=3)
        """
        if len(gmf_harmonics) < 3:
            return None

        # Check broadband energy in the GMF region
        band_low = gmf - 5.0 * shaft_freq
        band_high = gmf + 5.0 * shaft_freq
        band_mask = (freqs >= band_low) & (freqs <= band_high)

        if not np.any(band_mask):
            return None

        band_energy = float(np.mean(amps[band_mask] ** 2))
        overall_energy = float(np.mean(amps ** 2))

        if overall_energy <= 0:
            return None

        energy_ratio = band_energy / overall_energy
        if energy_ratio < 2.0:  # band should have elevated energy
            return None

        evidence: list[Evidence] = [
            Evidence(
                feature_name="GMF_band_energy_ratio",
                observed_value=energy_ratio,
                expected_range=(2.0, float("inf")),
                match_score=min(energy_ratio / 2.0, 1.0),
                description=(
                    f"Broadband energy ratio around GMF: {energy_ratio:.2f}x "
                    f"(band: {band_low:.0f}-{band_high:.0f} Hz)"
                ),
            ),
            Evidence(
                feature_name="GMF_harmonic_count",
                observed_value=float(len(gmf_harmonics)),
                expected_range=(3.0, float("inf")),
                match_score=min(len(gmf_harmonics) / 3.0, 1.0),
                description=f"{len(gmf_harmonics)} GMF harmonics detected (>=3 required)",
            ),
        ]

        confidence = 0.65 * confidence_scale

        return FaultCandidate(
            fault_id=20,
            fault_name="Gear Wear",
            fault_category="gear",
            confidence=confidence,
            diagnosis_type="S",
            evidence=evidence,
        )
