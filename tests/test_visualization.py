"""Tests for ``vibfault.visualization``.

Smoke tests that each plotting function runs without error and returns
a ``matplotlib.axes.Axes`` instance.  Uses the ``Agg`` backend so no
windows are opened.
"""

from __future__ import annotations

import matplotlib
import numpy as np

matplotlib.use("Agg")

from matplotlib.axes import Axes  # noqa: E402

from vibfault.core.models import (  # noqa: E402
    DiagnosisResult,
    FaultDiagnosis,
    MachineParameters,
)
from vibfault.visualization import (  # noqa: E402
    plot_cepstrum,
    plot_diagnosis_summary,
    plot_envelope_spectrum,
    plot_spectrum,
    plot_time_waveform,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

FS = 1000.0
N = 1024
T = np.arange(N) / FS
SIGNAL = np.sin(2 * np.pi * 50 * T)
FREQS = np.linspace(0, FS / 2, N // 2 + 1)
AMPS = np.abs(np.fft.rfft(SIGNAL)) * 2 / N


# ---------------------------------------------------------------------------
# plot_spectrum
# ---------------------------------------------------------------------------


class TestPlotSpectrum:
    def test_returns_axes(self) -> None:
        ax = plot_spectrum(FREQS, AMPS)
        assert isinstance(ax, Axes)

    def test_with_markers(self) -> None:
        ax = plot_spectrum(FREQS, AMPS, markers={"1X": 50.0, "2X": 100.0})
        assert isinstance(ax, Axes)
        # Markers produce vertical lines
        assert len(ax.lines) >= 3  # data + 2 markers

    def test_with_xlim(self) -> None:
        ax = plot_spectrum(FREQS, AMPS, xlim=(0, 200))
        assert ax.get_xlim()[1] <= 201

    def test_draws_on_provided_axes(self) -> None:
        import matplotlib.pyplot as plt

        fig, provided_ax = plt.subplots()
        result = plot_spectrum(FREQS, AMPS, ax=provided_ax)
        assert result is provided_ax
        plt.close(fig)


# ---------------------------------------------------------------------------
# plot_envelope_spectrum
# ---------------------------------------------------------------------------


class TestPlotEnvelopeSpectrum:
    def test_returns_axes(self) -> None:
        ax = plot_envelope_spectrum(FREQS, AMPS)
        assert isinstance(ax, Axes)

    def test_default_title(self) -> None:
        ax = plot_envelope_spectrum(FREQS, AMPS)
        assert "Envelope" in ax.get_title()


# ---------------------------------------------------------------------------
# plot_cepstrum
# ---------------------------------------------------------------------------


class TestPlotCepstrum:
    def test_returns_axes(self) -> None:
        quefrency = np.arange(N) / FS
        cepstrum = np.random.default_rng(42).standard_normal(N)
        ax = plot_cepstrum(quefrency, cepstrum)
        assert isinstance(ax, Axes)
        assert "Cepstrum" in ax.get_title()

    def test_with_markers(self) -> None:
        quefrency = np.arange(N) / FS
        cepstrum = np.random.default_rng(42).standard_normal(N)
        ax = plot_cepstrum(quefrency, cepstrum, markers={"gear period": 0.01})
        assert isinstance(ax, Axes)


# ---------------------------------------------------------------------------
# plot_time_waveform
# ---------------------------------------------------------------------------


class TestPlotTimeWaveform:
    def test_returns_axes(self) -> None:
        ax = plot_time_waveform(SIGNAL, FS)
        assert isinstance(ax, Axes)
        assert "Time" in ax.get_title()

    def test_xlim(self) -> None:
        ax = plot_time_waveform(SIGNAL, FS, xlim=(0, 0.1))
        assert ax.get_xlim()[1] <= 0.11


# ---------------------------------------------------------------------------
# plot_diagnosis_summary
# ---------------------------------------------------------------------------


def _make_result(faults: list[FaultDiagnosis] | None = None) -> DiagnosisResult:
    """Helper to build a minimal DiagnosisResult."""
    from datetime import UTC, datetime

    return DiagnosisResult(
        tier=1,
        parameters=MachineParameters(sampling_rate=1000.0, rpm=1800.0),
        timestamp=datetime.now(UTC),
        iso_severity="B-Acceptable",
        iso_rms_velocity=2.5,
        diagnosed_faults=faults or [],
    )


class TestPlotDiagnosisSummary:
    def test_no_faults(self) -> None:
        result = _make_result()
        ax = plot_diagnosis_summary(result)
        assert isinstance(ax, Axes)

    def test_with_faults(self) -> None:
        faults = [
            FaultDiagnosis(
                fault_id=1,
                fault_name="Unbalance",
                fault_category="Rotor",
                diagnosis_type="S",
                confidence=0.85,
            ),
            FaultDiagnosis(
                fault_id=5,
                fault_name="Outer Race Defect",
                fault_category="Bearing",
                diagnosis_type="S",
                confidence=0.65,
            ),
        ]
        result = _make_result(faults)
        ax = plot_diagnosis_summary(result)
        assert isinstance(ax, Axes)
        # Two horizontal bars
        assert len(ax.patches) == 2
