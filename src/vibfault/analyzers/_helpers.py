"""Shared spectral-analysis helpers used across multiple analyzer tiers.

Functions in this module were originally defined in ``tier1`` and ``tier2``
and are now centralised to avoid cross-tier coupling.
"""

from __future__ import annotations

import numpy as np

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_TOLERANCE: float = 0.03
"""Fractional tolerance (+/-3 %) for frequency peak searches."""


# ---------------------------------------------------------------------------
# Peak search near a target frequency
# ---------------------------------------------------------------------------


def find_peak_near(
    freqs: np.ndarray,
    amps: np.ndarray,
    target_freq: float,
    tolerance: float = DEFAULT_TOLERANCE,
) -> tuple[float, float] | None:
    """Find the highest spectral peak within *tolerance* of *target_freq*.

    Parameters
    ----------
    freqs : np.ndarray
        Frequency axis (Hz).
    amps : np.ndarray
        Corresponding amplitude values.
    target_freq : float
        Centre frequency to search around (Hz).
    tolerance : float
        Fractional tolerance -- the search window is
        ``[target * (1 - tol), target * (1 + tol)]``.

    Returns
    -------
    tuple[float, float] | None
        ``(actual_frequency, amplitude)`` of the highest peak inside the
        window, or ``None`` if no spectral bin falls within the window.
    """
    low = target_freq * (1.0 - tolerance)
    high = target_freq * (1.0 + tolerance)
    mask = (freqs >= low) & (freqs <= high)
    if not np.any(mask):
        return None
    idx = np.argmax(amps[mask])
    local_freqs = freqs[mask]
    local_amps = amps[mask]
    return float(local_freqs[idx]), float(local_amps[idx])


# ---------------------------------------------------------------------------
# Harmonic series search
# ---------------------------------------------------------------------------


def find_harmonics_in_spectrum(
    freqs: np.ndarray,
    amps: np.ndarray,
    fundamental: float,
    max_harmonics: int = 5,
    tolerance: float = 0.03,
    min_prominence_ratio: float = 3.0,
) -> list[tuple[int, float, float]]:
    """Search for harmonics of *fundamental* in a frequency spectrum.

    For each harmonic order *n* (1 through *max_harmonics*), the routine
    locates the highest amplitude bin within the tolerance band around
    ``n * fundamental``.  A harmonic is accepted only when its amplitude
    exceeds the local noise floor by at least *min_prominence_ratio*.

    Returns
    -------
    list[tuple[int, float, float]]
        Each entry is ``(harmonic_number, actual_frequency_hz, amplitude)``.
    """
    if freqs.size == 0 or amps.size == 0:
        return []

    freq_resolution = float(freqs[1] - freqs[0]) if freqs.size > 1 else 1.0
    results: list[tuple[int, float, float]] = []

    for n in range(1, max_harmonics + 1):
        target = n * fundamental
        lower = target * (1.0 - tolerance)
        upper = target * (1.0 + tolerance)

        mask = (freqs >= lower) & (freqs <= upper)
        if not np.any(mask):
            continue

        band_indices = np.flatnonzero(mask)
        best_idx = band_indices[int(np.argmax(amps[band_indices]))]
        peak_amp = float(amps[best_idx])
        peak_freq = float(freqs[best_idx])

        # Estimate local noise floor from a neighbourhood around the peak,
        # excluding the peak's own tolerance band.
        noise_half_width = max(20, int(round((upper - lower) / freq_resolution)) + 10)
        centre_idx = best_idx
        noise_lo = max(0, centre_idx - noise_half_width)
        noise_hi = min(len(amps), centre_idx + noise_half_width + 1)
        noise_region = np.concatenate(
            [
                amps[noise_lo : band_indices[0]],
                amps[band_indices[-1] + 1 : noise_hi],
            ]
        )

        noise_floor = 0.0 if noise_region.size == 0 else float(np.median(noise_region))

        if noise_floor <= 0.0:
            if peak_amp > 0.0:
                results.append((n, peak_freq, peak_amp))
        elif peak_amp / noise_floor >= min_prominence_ratio:
            results.append((n, peak_freq, peak_amp))

    return results


# ---------------------------------------------------------------------------
# Sideband detection
# ---------------------------------------------------------------------------


def check_sidebands(
    freqs: np.ndarray,
    amps: np.ndarray,
    centre_freq: float,
    sideband_spacing: float,
    tolerance: float = 0.03,
    min_prominence_ratio: float = 2.0,
) -> list[tuple[str, float, float]]:
    """Check for sidebands around *centre_freq* at +/- *sideband_spacing*.

    Returns
    -------
    list[tuple[str, float, float]]
        Each entry is ``(label, actual_freq, amplitude)`` where *label* is
        e.g. ``"+1"`` or ``"-1"``.
    """
    found: list[tuple[str, float, float]] = []

    for sign, label_prefix in [(1, "+"), (-1, "-")]:
        target = centre_freq + sign * sideband_spacing
        if target <= 0.0:
            continue

        lower = target * (1.0 - tolerance)
        upper = target * (1.0 + tolerance)
        mask = (freqs >= lower) & (freqs <= upper)
        if not np.any(mask):
            continue

        band_indices = np.flatnonzero(mask)
        best_idx = band_indices[int(np.argmax(amps[band_indices]))]
        peak_amp = float(amps[best_idx])
        peak_freq = float(freqs[best_idx])

        # Quick local noise estimate
        noise_lo = max(0, best_idx - 20)
        noise_hi = min(len(amps), best_idx + 21)
        noise_region = np.concatenate(
            [
                amps[noise_lo : band_indices[0]],
                amps[band_indices[-1] + 1 : noise_hi],
            ]
        )
        noise_floor = float(np.median(noise_region)) if noise_region.size > 0 else 0.0

        if noise_floor <= 0.0:
            if peak_amp > 0.0:
                found.append((f"{label_prefix}1", peak_freq, peak_amp))
        elif peak_amp / noise_floor >= min_prominence_ratio:
            found.append((f"{label_prefix}1", peak_freq, peak_amp))

    return found
