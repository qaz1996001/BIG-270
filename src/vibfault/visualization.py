"""Visualization functions for vibration fault diagnosis.

Each function draws exactly one type of plot.  All accept an optional
``ax`` parameter: when ``None`` a new figure is created; when an
:class:`~matplotlib.axes.Axes` is passed the drawing goes there,
allowing the caller to compose subplots freely.

Every function returns the :class:`~matplotlib.axes.Axes` it drew on.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import matplotlib

matplotlib.use("Agg")  # non-interactive backend; safe for CLI / tests

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

if TYPE_CHECKING:
    from matplotlib.axes import Axes

    from vibfault.core.models import DiagnosisResult


# ---------------------------------------------------------------------------
# Spectrum (FFT amplitude)
# ---------------------------------------------------------------------------


def plot_spectrum(
    freqs: np.ndarray,
    amps: np.ndarray,
    *,
    markers: dict[str, float] | None = None,
    title: str = "FFT Spectrum",
    xlim: tuple[float, float] | None = None,
    ax: Axes | None = None,
) -> Axes:
    """Plot a single-sided FFT amplitude spectrum.

    Parameters
    ----------
    freqs : np.ndarray
        Frequency axis (Hz).
    amps : np.ndarray
        Amplitude values.
    markers : dict[str, float] or None
        Labelled vertical lines at specific frequencies.
        Keys are labels, values are frequencies in Hz.
    title : str
        Plot title.
    xlim : tuple[float, float] or None
        X-axis limits ``(low, high)`` in Hz.
    ax : Axes or None
        Matplotlib axes to draw on.  ``None`` creates a new figure.

    Returns
    -------
    Axes
        The axes containing the plot.
    """
    if ax is None:
        _, ax = plt.subplots(figsize=(10, 4))

    ax.plot(freqs, amps, linewidth=0.5)
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("Amplitude")
    ax.set_title(title)

    if xlim is not None:
        ax.set_xlim(xlim)

    if markers:
        for label, freq in markers.items():
            ax.axvline(freq, color="red", linestyle="--", linewidth=0.8, alpha=0.7)
            ax.text(
                freq,
                ax.get_ylim()[1] * 0.9,
                f" {label}",
                color="red",
                fontsize=8,
                verticalalignment="top",
            )

    ax.grid(True, alpha=0.3)
    return ax


# ---------------------------------------------------------------------------
# Envelope spectrum
# ---------------------------------------------------------------------------


def plot_envelope_spectrum(
    freqs: np.ndarray,
    amps: np.ndarray,
    *,
    markers: dict[str, float] | None = None,
    title: str = "Envelope Spectrum",
    xlim: tuple[float, float] | None = None,
    ax: Axes | None = None,
) -> Axes:
    """Plot an envelope spectrum with optional fault-frequency markers.

    Same interface as :func:`plot_spectrum` but with a default title
    appropriate for envelope analysis output.
    """
    return plot_spectrum(
        freqs,
        amps,
        markers=markers,
        title=title,
        xlim=xlim,
        ax=ax,
    )


# ---------------------------------------------------------------------------
# Cepstrum
# ---------------------------------------------------------------------------


def plot_cepstrum(
    quefrency: np.ndarray,
    cepstrum: np.ndarray,
    *,
    markers: dict[str, float] | None = None,
    title: str = "Cepstrum",
    xlim: tuple[float, float] | None = None,
    ax: Axes | None = None,
) -> Axes:
    """Plot a cepstrum (quefrency domain).

    Parameters
    ----------
    quefrency : np.ndarray
        Quefrency axis (seconds).
    cepstrum : np.ndarray
        Cepstrum values.
    markers : dict[str, float] or None
        Labelled vertical lines.  Keys are labels, values are quefrencies (s).
    title : str
        Plot title.
    xlim : tuple[float, float] or None
        X-axis limits ``(low, high)`` in seconds.
    ax : Axes or None
        Matplotlib axes.
    """
    if ax is None:
        _, ax = plt.subplots(figsize=(10, 4))

    ax.plot(quefrency, cepstrum, linewidth=0.5)
    ax.set_xlabel("Quefrency (s)")
    ax.set_ylabel("Amplitude")
    ax.set_title(title)

    if xlim is not None:
        ax.set_xlim(xlim)

    if markers:
        for label, q in markers.items():
            ax.axvline(q, color="red", linestyle="--", linewidth=0.8, alpha=0.7)
            ax.text(
                q,
                ax.get_ylim()[1] * 0.9,
                f" {label}",
                color="red",
                fontsize=8,
                verticalalignment="top",
            )

    ax.grid(True, alpha=0.3)
    return ax


# ---------------------------------------------------------------------------
# Time waveform
# ---------------------------------------------------------------------------


def plot_time_waveform(
    signal: np.ndarray,
    fs: float,
    *,
    title: str = "Time Waveform",
    xlim: tuple[float, float] | None = None,
    ax: Axes | None = None,
) -> Axes:
    """Plot a time-domain vibration waveform.

    Parameters
    ----------
    signal : np.ndarray
        1-D time-domain signal.
    fs : float
        Sampling frequency in Hz.
    title : str
        Plot title.
    xlim : tuple[float, float] or None
        X-axis limits ``(low, high)`` in seconds.
    ax : Axes or None
        Matplotlib axes.
    """
    if ax is None:
        _, ax = plt.subplots(figsize=(10, 3))

    t = np.arange(signal.size) / fs
    ax.plot(t, signal, linewidth=0.4)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Amplitude")
    ax.set_title(title)

    if xlim is not None:
        ax.set_xlim(xlim)

    ax.grid(True, alpha=0.3)
    return ax


# ---------------------------------------------------------------------------
# Diagnosis summary
# ---------------------------------------------------------------------------


def plot_diagnosis_summary(
    result: DiagnosisResult,
    *,
    ax: Axes | None = None,
) -> Axes:
    """Plot a horizontal bar chart summarizing diagnosed faults and confidence.

    Parameters
    ----------
    result : DiagnosisResult
        Output of :meth:`DiagnosticPipeline.run`.
    ax : Axes or None
        Matplotlib axes.
    """
    if ax is None:
        _, ax = plt.subplots(figsize=(8, max(3, len(result.diagnosed_faults) * 0.5 + 1)))

    faults = sorted(result.diagnosed_faults, key=lambda f: f.confidence)

    if not faults:
        ax.text(
            0.5,
            0.5,
            "No faults diagnosed",
            ha="center",
            va="center",
            fontsize=12,
            transform=ax.transAxes,
        )
        ax.set_title(f"Diagnosis Summary (Tier {result.tier})")
        return ax

    names = [f"#{f.fault_id} {f.fault_name}" for f in faults]
    confidences = [f.confidence for f in faults]

    colors = []
    for c in confidences:
        if c >= 0.8:
            colors.append("#d32f2f")
        elif c >= 0.6:
            colors.append("#f57c00")
        else:
            colors.append("#fbc02d")

    y_pos = range(len(names))
    ax.barh(y_pos, confidences, color=colors, edgecolor="none", height=0.6)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(names, fontsize=9)
    ax.set_xlabel("Confidence")
    ax.set_xlim(0, 1.0)
    ax.set_title(f"Diagnosis Summary (Tier {result.tier}) — ISO: {result.iso_severity}")

    for i, c in enumerate(confidences):
        ax.text(c + 0.02, i, f"{c:.2f}", va="center", fontsize=8)

    ax.grid(True, axis="x", alpha=0.3)
    return ax
