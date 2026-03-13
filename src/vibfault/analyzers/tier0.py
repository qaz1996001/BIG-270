"""Tier 0 analyzer -- baseline health assessment.

Always runs because it requires only the acceleration signal and a
sampling rate.  Produces no fault candidates itself; instead it computes
health indicators that downstream tiers can consume:

* ISO 10816 vibration-severity zone (via velocity RMS).
* Time-domain statistics: RMS, kurtosis, crest factor.
* Raw FFT with basic anomaly flagging for unusual peaks.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from vibfault.core.preprocessing import compute_fft, time_domain_features, velocity_rms

if TYPE_CHECKING:
    from vibfault.analyzers.protocol import FaultCandidate
    from vibfault.core.models import MachineParameters

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ISO 10816 velocity-RMS thresholds (mm/s) per machine class.
# Each tuple is (upper_A, upper_B, upper_C).  Anything above upper_C is zone D.
# ---------------------------------------------------------------------------
_ISO_10816_THRESHOLDS: dict[str, tuple[float, float, float]] = {
    "I": (0.71, 1.8, 4.5),
    "II": (1.12, 2.8, 7.1),
    "III": (1.12, 2.8, 7.1),
    "IV": (1.12, 2.8, 7.1),
}


@dataclass
class HealthIndicators:
    """Container for Tier-0 health metrics.

    Attributes:
        rms: Root-mean-square of the acceleration signal (g or m/s^2).
        kurtosis: Kurtosis of the acceleration signal.
        crest_factor: Peak / RMS ratio.
        vrms: Velocity RMS (mm/s) used for ISO 10816 assessment.
        iso_zone: ISO 10816 severity zone string, e.g. ``"B-Acceptable"``.
        fft_freqs: Frequency axis of the computed FFT (Hz).
        fft_magnitude: Magnitude spectrum corresponding to *fft_freqs*.
        anomalous_peaks: Indices into *fft_freqs* that exceed the anomaly
            threshold relative to the median spectral level.
    """

    rms: float
    kurtosis: float
    crest_factor: float
    vrms: float
    iso_zone: str
    fft_freqs: np.ndarray
    fft_magnitude: np.ndarray
    anomalous_peaks: np.ndarray


class Tier0Analyzer:
    """Tier 0: Health assessment using time-domain statistics and raw FFT.

    Always runs -- requires only acceleration + sampling_rate.

    Provides:
    - ISO 10816 severity assessment (via velocity RMS).
    - Time-domain health indicators (RMS, kurtosis, crest factor).
    - Raw FFT anomaly detection (flag unusual peaks).
    """

    # Peaks whose magnitude exceeds ``_ANOMALY_SIGMA`` standard deviations
    # above the mean spectral level are flagged as anomalous.
    _ANOMALY_SIGMA: float = 3.0

    # ------------------------------------------------------------------
    # Protocol methods
    # ------------------------------------------------------------------

    def prerequisites(self) -> list[str]:
        """Tier 0 only needs the sampling rate (always present)."""
        return ["sampling_rate"]

    def can_run(self, params: MachineParameters) -> bool:
        """Always runnable -- sampling_rate is a mandatory parameter."""
        return True

    def analyze(
        self,
        signal: np.ndarray,
        params: MachineParameters,
    ) -> list[FaultCandidate]:
        """Compute health indicators and return an empty fault list.

        The computed :class:`HealthIndicators` are stored on the instance
        as ``self.health`` so that higher tiers or the orchestrator can
        inspect them after the call.

        Returns:
            An empty list -- Tier 0 does not emit fault candidates.
        """
        indicators = self._compute_health(signal, params)
        self.health: HealthIndicators = indicators

        logger.info(
            "Tier 0 complete | RMS=%.4f | Kurtosis=%.2f | CF=%.2f | "
            "vRMS=%.3f mm/s | ISO zone=%s | anomalous peaks=%d",
            indicators.rms,
            indicators.kurtosis,
            indicators.crest_factor,
            indicators.vrms,
            indicators.iso_zone,
            len(indicators.anomalous_peaks),
        )

        return []

    # ------------------------------------------------------------------
    # ISO 10816 severity assessment
    # ------------------------------------------------------------------

    @staticmethod
    def assess_iso_severity(
        vel_rms: float,
        machine_class: str = "II",
    ) -> str:
        """Map a velocity RMS value to an ISO 10816 severity zone.

        Args:
            vel_rms: Overall velocity RMS in mm/s.
            machine_class: ISO 10816 machine group as a Roman-numeral
                string (``"I"``, ``"II"``, ``"III"``, or ``"IV"``).

        Returns:
            A string of the form ``"<zone>-<label>"``, e.g.
            ``"B-Acceptable"``.

        Raises:
            ValueError: If *machine_class* is not recognised.
        """
        thresholds = _ISO_10816_THRESHOLDS.get(machine_class)
        if thresholds is None:
            raise ValueError(
                f"Unknown ISO 10816 machine class {machine_class!r}. "
                f"Expected one of {sorted(_ISO_10816_THRESHOLDS)}."
            )

        upper_a, upper_b, upper_c = thresholds

        if vel_rms <= upper_a:
            return "A-Good"
        if vel_rms <= upper_b:
            return "B-Acceptable"
        if vel_rms <= upper_c:
            return "C-Alert"
        return "D-Danger"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_health(
        self,
        signal: np.ndarray,
        params: MachineParameters,
    ) -> HealthIndicators:
        """Run all Tier-0 computations and bundle the results."""
        sampling_rate: float = params.sampling_rate

        # Time-domain features ------------------------------------------------
        td = time_domain_features(signal)
        rms: float = td["rms"]
        kurtosis: float = td["kurtosis"]
        crest_factor: float = td["crest_factor"]

        # Velocity RMS & ISO zone ---------------------------------------------
        vrms = velocity_rms(signal, sampling_rate)
        machine_class: str = getattr(params, "machine_class", "II") or "II"
        iso_zone = self.assess_iso_severity(vrms, machine_class)

        # FFT & anomaly detection ----------------------------------------------
        fft_freqs, fft_magnitude = compute_fft(signal, sampling_rate)
        anomalous_peaks = self._detect_anomalous_peaks(fft_magnitude)

        return HealthIndicators(
            rms=rms,
            kurtosis=kurtosis,
            crest_factor=crest_factor,
            vrms=vrms,
            iso_zone=iso_zone,
            fft_freqs=fft_freqs,
            fft_magnitude=fft_magnitude,
            anomalous_peaks=anomalous_peaks,
        )

    def _detect_anomalous_peaks(self, magnitude: np.ndarray) -> np.ndarray:
        """Return indices of spectral bins that exceed the anomaly threshold.

        A bin is flagged when its magnitude is more than
        ``_ANOMALY_SIGMA`` standard deviations above the mean level.
        """
        if magnitude.size == 0:
            return np.array([], dtype=np.intp)

        mean = np.mean(magnitude)
        std = np.std(magnitude)

        if std < 1e-12:
            return np.array([], dtype=np.intp)

        threshold = mean + self._ANOMALY_SIGMA * std
        return np.flatnonzero(magnitude > threshold)
