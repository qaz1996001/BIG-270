"""Tests for electrical and gear frequency functions.

Covers the following functions in ``vibfault.core.frequencies``:

* ``electrical_2fl``
* ``electrical_synchronous_freq``
* ``electrical_slip_freq``
* ``electrical_pole_pass_freq``
* ``electrical_rbpf``
* ``gear_mesh_freq``
* ``gear_driven_shaft_freq``
"""

from pytest import approx

from vibfault.core.frequencies import (
    electrical_2fl,
    electrical_pole_pass_freq,
    electrical_rbpf,
    electrical_slip_freq,
    electrical_synchronous_freq,
    gear_driven_shaft_freq,
    gear_mesh_freq,
)

# ---------------------------------------------------------------------------
# Twice line frequency (2FL)
# ---------------------------------------------------------------------------


class TestElectrical2FL:
    """electrical_2fl should return 2 * line_freq."""

    def test_50hz(self) -> None:
        assert electrical_2fl(50.0) == approx(100.0)

    def test_60hz(self) -> None:
        assert electrical_2fl(60.0) == approx(120.0)


# ---------------------------------------------------------------------------
# Synchronous frequency
# ---------------------------------------------------------------------------


class TestElectricalSynchronousFreq:
    """electrical_synchronous_freq should return line_freq / pole_pairs."""

    def test_60hz_2_poles(self) -> None:
        # 60 Hz / 2 pole pairs = 30 Hz
        assert electrical_synchronous_freq(60.0, 2) == approx(30.0)


# ---------------------------------------------------------------------------
# Slip frequency
# ---------------------------------------------------------------------------


class TestElectricalSlipFreq:
    """electrical_slip_freq should return f_sync - f_r."""

    def test_60hz_2_poles_29_5hz_shaft(self) -> None:
        # f_sync = 60 / 2 = 30 Hz; f_slip = 30 - 29.5 = 0.5 Hz
        assert electrical_slip_freq(60.0, 2, 29.5) == approx(0.5)


# ---------------------------------------------------------------------------
# Pole-pass frequency
# ---------------------------------------------------------------------------


class TestElectricalPolePassFreq:
    """electrical_pole_pass_freq should return pole_pairs * f_slip."""

    def test_60hz_2_poles_29_5hz_shaft(self) -> None:
        # f_slip = 0.5 Hz; Fp = 2 * 0.5 = 1.0 Hz
        assert electrical_pole_pass_freq(60.0, 2, 29.5) == approx(1.0)


# ---------------------------------------------------------------------------
# Rotor Bar Pass Frequency
# ---------------------------------------------------------------------------


class TestElectricalRBPF:
    """electrical_rbpf should return n_bars * f_r."""

    def test_28_bars_29_5hz(self) -> None:
        # RBPF = 28 * 29.5 = 826.0 Hz
        assert electrical_rbpf(28, 29.5) == approx(826.0)


# ---------------------------------------------------------------------------
# Gear Mesh Frequency
# ---------------------------------------------------------------------------


class TestGearMeshFreq:
    """gear_mesh_freq should return teeth * shaft_freq."""

    def test_20_teeth_30hz(self) -> None:
        # GMF = 20 * 30 = 600 Hz
        assert gear_mesh_freq(20, 30.0) == approx(600.0)


# ---------------------------------------------------------------------------
# Driven Shaft Frequency
# ---------------------------------------------------------------------------


class TestGearDrivenShaftFreq:
    """gear_driven_shaft_freq should return (Z_drive / Z_driven) * f_drive."""

    def test_20_40_teeth_30hz(self) -> None:
        # f_driven = (20 / 40) * 30 = 15.0 Hz
        assert gear_driven_shaft_freq(20, 40, 30.0) == approx(15.0)
