"""Tests for frequency calculation functions in ``vibfault.core.frequencies``.

Covers:
* Bearing characteristic frequencies: BPFO, BPFI, BSF, FTF.
* Electrical frequencies: 2FL, synchronous, slip, pole-pass, RBPF.
* Gear frequencies: GMF, driven shaft frequency.
* Frequency matching utility: ``frequency_match``.
"""

import math

from pytest import approx

from vibfault.core.frequencies import (
    bearing_bpfi,
    bearing_bpfo,
    bearing_bsf,
    bearing_ftf,
    electrical_2fl,
    electrical_pole_pass_freq,
    electrical_rbpf,
    electrical_slip_freq,
    electrical_synchronous_freq,
    frequency_match,
    gear_driven_shaft_freq,
    gear_mesh_freq,
)

# ---------------------------------------------------------------------------
# Bearing characteristic frequencies
# ---------------------------------------------------------------------------

# Reference bearing: 6205 (approx)
# n_balls=9, ball_dia=7.94 mm, pitch_dia=39.04 mm, contact_angle=0°
# At shaft_freq=30 Hz (1800 RPM)

N_BALLS = 9
BALL_DIA = 7.94
PITCH_DIA = 39.04
CONTACT_ANGLE = 0.0
SHAFT_FREQ = 30.0
RATIO = BALL_DIA / PITCH_DIA  # ~0.2034


class TestBearingBPFO:
    """BPFO = (n/2) * f_r * (1 - d/D * cos(alpha))."""

    def test_zero_contact_angle(self) -> None:
        result = bearing_bpfo(N_BALLS, BALL_DIA, PITCH_DIA, 0.0, SHAFT_FREQ)
        expected = (N_BALLS / 2.0) * SHAFT_FREQ * (1.0 - RATIO)
        assert result == approx(expected, rel=1e-6)

    def test_with_contact_angle(self) -> None:
        angle = 15.0
        result = bearing_bpfo(N_BALLS, BALL_DIA, PITCH_DIA, angle, SHAFT_FREQ)
        expected = (N_BALLS / 2.0) * SHAFT_FREQ * (1.0 - RATIO * math.cos(math.radians(angle)))
        assert result == approx(expected, rel=1e-6)


class TestBearingBPFI:
    """BPFI = (n/2) * f_r * (1 + d/D * cos(alpha))."""

    def test_zero_contact_angle(self) -> None:
        result = bearing_bpfi(N_BALLS, BALL_DIA, PITCH_DIA, 0.0, SHAFT_FREQ)
        expected = (N_BALLS / 2.0) * SHAFT_FREQ * (1.0 + RATIO)
        assert result == approx(expected, rel=1e-6)

    def test_with_contact_angle(self) -> None:
        angle = 15.0
        result = bearing_bpfi(N_BALLS, BALL_DIA, PITCH_DIA, angle, SHAFT_FREQ)
        expected = (N_BALLS / 2.0) * SHAFT_FREQ * (1.0 + RATIO * math.cos(math.radians(angle)))
        assert result == approx(expected, rel=1e-6)


class TestBearingBSF:
    """BSF = (D/(2d)) * f_r * (1 - (d/D * cos(alpha))^2)."""

    def test_zero_contact_angle(self) -> None:
        result = bearing_bsf(BALL_DIA, PITCH_DIA, 0.0, SHAFT_FREQ)
        expected = (PITCH_DIA / (2 * BALL_DIA)) * SHAFT_FREQ * (1.0 - RATIO**2)
        assert result == approx(expected, rel=1e-6)

    def test_with_contact_angle(self) -> None:
        angle = 15.0
        result = bearing_bsf(BALL_DIA, PITCH_DIA, angle, SHAFT_FREQ)
        r_cos = RATIO * math.cos(math.radians(angle))
        expected = (PITCH_DIA / (2 * BALL_DIA)) * SHAFT_FREQ * (1.0 - r_cos**2)
        assert result == approx(expected, rel=1e-6)


class TestBearingFTF:
    """FTF = (f_r/2) * (1 - d/D * cos(alpha))."""

    def test_zero_contact_angle(self) -> None:
        result = bearing_ftf(BALL_DIA, PITCH_DIA, 0.0, SHAFT_FREQ)
        expected = (SHAFT_FREQ / 2.0) * (1.0 - RATIO)
        assert result == approx(expected, rel=1e-6)

    def test_with_contact_angle(self) -> None:
        angle = 15.0
        result = bearing_ftf(BALL_DIA, PITCH_DIA, angle, SHAFT_FREQ)
        expected = (SHAFT_FREQ / 2.0) * (1.0 - RATIO * math.cos(math.radians(angle)))
        assert result == approx(expected, rel=1e-6)


class TestBearingBPFOvsBPFI:
    """BPFO + BPFI should equal n * f_r (kinematic identity)."""

    def test_bpfo_plus_bpfi_equals_n_times_fr(self) -> None:
        for angle in [0.0, 10.0, 20.0, 30.0]:
            bpfo = bearing_bpfo(N_BALLS, BALL_DIA, PITCH_DIA, angle, SHAFT_FREQ)
            bpfi = bearing_bpfi(N_BALLS, BALL_DIA, PITCH_DIA, angle, SHAFT_FREQ)
            assert bpfo + bpfi == approx(N_BALLS * SHAFT_FREQ, rel=1e-10)


# ---------------------------------------------------------------------------
# Electrical frequencies
# ---------------------------------------------------------------------------


class TestElectrical2FL:
    """electrical_2fl should return 2 * line_freq."""

    def test_50hz(self) -> None:
        assert electrical_2fl(50.0) == approx(100.0)

    def test_60hz(self) -> None:
        assert electrical_2fl(60.0) == approx(120.0)


class TestElectricalSynchronousFreq:
    """electrical_synchronous_freq should return line_freq / pole_pairs."""

    def test_60hz_2_poles(self) -> None:
        assert electrical_synchronous_freq(60.0, 2) == approx(30.0)

    def test_50hz_3_poles(self) -> None:
        # 50 / 3 ≈ 16.667 Hz
        assert electrical_synchronous_freq(50.0, 3) == approx(50.0 / 3.0)


class TestElectricalSlipFreq:
    """electrical_slip_freq should return f_sync - f_r."""

    def test_60hz_2_poles_29_5hz_shaft(self) -> None:
        assert electrical_slip_freq(60.0, 2, 29.5) == approx(0.5)

    def test_50hz_3_poles(self) -> None:
        # f_sync = 50/3 ≈ 16.667; shaft = 16.0; slip = 0.667
        assert electrical_slip_freq(50.0, 3, 16.0) == approx(50.0 / 3.0 - 16.0)


class TestElectricalPolePassFreq:
    """electrical_pole_pass_freq should return pole_pairs * f_slip."""

    def test_60hz_2_poles_29_5hz_shaft(self) -> None:
        assert electrical_pole_pass_freq(60.0, 2, 29.5) == approx(1.0)


class TestElectricalRBPF:
    """electrical_rbpf should return n_bars * f_r."""

    def test_28_bars_29_5hz(self) -> None:
        assert electrical_rbpf(28, 29.5) == approx(826.0)

    def test_36_bars_30hz(self) -> None:
        assert electrical_rbpf(36, 30.0) == approx(1080.0)


# ---------------------------------------------------------------------------
# Gear frequencies
# ---------------------------------------------------------------------------


class TestGearMeshFreq:
    """gear_mesh_freq should return teeth * shaft_freq."""

    def test_20_teeth_30hz(self) -> None:
        assert gear_mesh_freq(20, 30.0) == approx(600.0)


class TestGearDrivenShaftFreq:
    """gear_driven_shaft_freq should return (Z_drive / Z_driven) * f_drive."""

    def test_20_40_teeth_30hz(self) -> None:
        assert gear_driven_shaft_freq(20, 40, 30.0) == approx(15.0)

    def test_equal_teeth(self) -> None:
        assert gear_driven_shaft_freq(30, 30, 25.0) == approx(25.0)


# ---------------------------------------------------------------------------
# Frequency match utility
# ---------------------------------------------------------------------------


class TestFrequencyMatch:
    """Verify tolerance-based frequency matching."""

    def test_exact_match(self) -> None:
        assert frequency_match(100.0, 100.0) is True

    def test_within_3_percent(self) -> None:
        # 102.9 is within 3% of 100
        assert frequency_match(102.9, 100.0) is True

    def test_outside_3_percent(self) -> None:
        # 103.1 is outside 3% of 100
        assert frequency_match(103.1, 100.0) is False

    def test_lower_bound(self) -> None:
        # 97.0 is within 3% of 100
        assert frequency_match(97.0, 100.0) is True
        # 96.9 is outside 3% of 100
        assert frequency_match(96.9, 100.0) is False

    def test_custom_tolerance(self) -> None:
        # 5% tolerance
        assert frequency_match(104.9, 100.0, tolerance=0.05) is True
        assert frequency_match(105.1, 100.0, tolerance=0.05) is False

    def test_1_percent_tolerance(self) -> None:
        assert frequency_match(100.9, 100.0, tolerance=0.01) is True
        assert frequency_match(101.1, 100.0, tolerance=0.01) is False
