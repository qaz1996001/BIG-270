"""Bearing characteristic frequency calculations.

Implements the standard kinematic equations for rolling-element bearing
defect frequencies:

* **BPFO** -- Ball Pass Frequency, Outer Race
* **BPFI** -- Ball Pass Frequency, Inner Race
* **BSF**  -- Ball Spin Frequency
* **FTF**  -- Fundamental Train (cage) Frequency

All geometry dimensions are in millimetres; the contact angle is specified
in degrees and converted to radians internally.  The shaft rotational
frequency (*shaft_freq_hz*) is in Hz.

Reference: Harris, T. A. & Kotzalas, M. N., *Rolling Bearing Analysis*,
5th ed., CRC Press, 2006.
"""

from __future__ import annotations

import math

# ---------------------------------------------------------------------------
# Characteristic frequencies
# ---------------------------------------------------------------------------


def bearing_bpfo(
    n_balls: int,
    ball_dia: float,
    pitch_dia: float,
    contact_angle_deg: float,
    shaft_freq_hz: float,
) -> float:
    """Ball Pass Frequency, Outer Race.

    BPFO = (n / 2) * f_r * (1 - (d / D) * cos(alpha))

    Parameters
    ----------
    n_balls : int
        Number of rolling elements.
    ball_dia : float
        Rolling-element (ball) diameter in mm.
    pitch_dia : float
        Bearing pitch diameter in mm.
    contact_angle_deg : float
        Contact angle in degrees.
    shaft_freq_hz : float
        Shaft rotational frequency in Hz.

    Returns
    -------
    float
        BPFO in Hz.
    """
    alpha = math.radians(contact_angle_deg)
    ratio = ball_dia / pitch_dia
    return (n_balls / 2.0) * shaft_freq_hz * (1.0 - ratio * math.cos(alpha))


def bearing_bpfi(
    n_balls: int,
    ball_dia: float,
    pitch_dia: float,
    contact_angle_deg: float,
    shaft_freq_hz: float,
) -> float:
    """Ball Pass Frequency, Inner Race.

    BPFI = (n / 2) * f_r * (1 + (d / D) * cos(alpha))

    Parameters
    ----------
    n_balls : int
        Number of rolling elements.
    ball_dia : float
        Rolling-element (ball) diameter in mm.
    pitch_dia : float
        Bearing pitch diameter in mm.
    contact_angle_deg : float
        Contact angle in degrees.
    shaft_freq_hz : float
        Shaft rotational frequency in Hz.

    Returns
    -------
    float
        BPFI in Hz.
    """
    alpha = math.radians(contact_angle_deg)
    ratio = ball_dia / pitch_dia
    return (n_balls / 2.0) * shaft_freq_hz * (1.0 + ratio * math.cos(alpha))


def bearing_bsf(
    ball_dia: float,
    pitch_dia: float,
    contact_angle_deg: float,
    shaft_freq_hz: float,
) -> float:
    """Ball Spin Frequency.

    BSF = (D / (2 * d)) * f_r * (1 - ((d / D) * cos(alpha))^2)

    Parameters
    ----------
    ball_dia : float
        Rolling-element (ball) diameter in mm.
    pitch_dia : float
        Bearing pitch diameter in mm.
    contact_angle_deg : float
        Contact angle in degrees.
    shaft_freq_hz : float
        Shaft rotational frequency in Hz.

    Returns
    -------
    float
        BSF in Hz.
    """
    alpha = math.radians(contact_angle_deg)
    ratio = ball_dia / pitch_dia
    return (pitch_dia / (2.0 * ball_dia)) * shaft_freq_hz * (1.0 - (ratio * math.cos(alpha)) ** 2)


def bearing_ftf(
    ball_dia: float,
    pitch_dia: float,
    contact_angle_deg: float,
    shaft_freq_hz: float,
) -> float:
    """Fundamental Train (cage) Frequency.

    FTF = (f_r / 2) * (1 - (d / D) * cos(alpha))

    Parameters
    ----------
    ball_dia : float
        Rolling-element (ball) diameter in mm.
    pitch_dia : float
        Bearing pitch diameter in mm.
    contact_angle_deg : float
        Contact angle in degrees.
    shaft_freq_hz : float
        Shaft rotational frequency in Hz.

    Returns
    -------
    float
        FTF in Hz.
    """
    alpha = math.radians(contact_angle_deg)
    ratio = ball_dia / pitch_dia
    return (shaft_freq_hz / 2.0) * (1.0 - ratio * math.cos(alpha))


# ---------------------------------------------------------------------------
# Frequency matching utility
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Electrical characteristic frequencies
# ---------------------------------------------------------------------------


def electrical_2fl(line_freq: float) -> float:
    """Twice line frequency (2FL).

    The dominant spectral component associated with electromagnetic forces
    in AC machines.

    Parameters
    ----------
    line_freq : float
        AC supply (mains) frequency in Hz (e.g. 50 or 60).

    Returns
    -------
    float
        2FL in Hz.
    """
    return 2.0 * line_freq


def electrical_synchronous_freq(line_freq: float, pole_pairs: int) -> float:
    """Synchronous (rotating field) frequency.

    f_sync = f_line / pole_pairs

    Parameters
    ----------
    line_freq : float
        AC supply frequency in Hz.
    pole_pairs : int
        Number of pole pairs.

    Returns
    -------
    float
        Synchronous frequency in Hz.
    """
    return line_freq / pole_pairs


def electrical_slip_freq(
    line_freq: float,
    pole_pairs: int,
    shaft_freq: float,
) -> float:
    """Slip frequency of an induction motor.

    f_slip = f_sync - f_r

    Parameters
    ----------
    line_freq : float
        AC supply frequency in Hz.
    pole_pairs : int
        Number of pole pairs.
    shaft_freq : float
        Shaft rotational frequency in Hz.

    Returns
    -------
    float
        Slip frequency in Hz.
    """
    f_sync = electrical_synchronous_freq(line_freq, pole_pairs)
    return f_sync - shaft_freq


def electrical_pole_pass_freq(
    line_freq: float,
    pole_pairs: int,
    shaft_freq: float,
) -> float:
    """Pole-pass frequency.

    Fp = pole_pairs * f_slip

    Parameters
    ----------
    line_freq : float
        AC supply frequency in Hz.
    pole_pairs : int
        Number of pole pairs.
    shaft_freq : float
        Shaft rotational frequency in Hz.

    Returns
    -------
    float
        Pole-pass frequency in Hz.
    """
    f_slip = electrical_slip_freq(line_freq, pole_pairs, shaft_freq)
    return pole_pairs * f_slip


def electrical_rbpf(n_bars: int, shaft_freq: float) -> float:
    """Rotor Bar Pass Frequency.

    RBPF = n_bars * f_r

    Parameters
    ----------
    n_bars : int
        Number of rotor bars.
    shaft_freq : float
        Shaft rotational frequency in Hz.

    Returns
    -------
    float
        RBPF in Hz.
    """
    return n_bars * shaft_freq


# ---------------------------------------------------------------------------
# Gear characteristic frequencies
# ---------------------------------------------------------------------------


def gear_mesh_freq(teeth: int, shaft_freq: float) -> float:
    """Gear Mesh Frequency.

    GMF = Z * f_r

    Parameters
    ----------
    teeth : int
        Number of teeth on the gear mounted on the shaft.
    shaft_freq : float
        Rotational frequency of the shaft carrying the gear, in Hz.

    Returns
    -------
    float
        GMF in Hz.
    """
    return teeth * shaft_freq


def gear_driven_shaft_freq(
    drive_teeth: int,
    driven_teeth: int,
    drive_shaft_freq: float,
) -> float:
    """Calculate driven shaft frequency from gear ratio.

    f_driven = (Z_drive / Z_driven) * f_drive

    Parameters
    ----------
    drive_teeth : int
        Number of teeth on the driving gear.
    driven_teeth : int
        Number of teeth on the driven gear.
    drive_shaft_freq : float
        Rotational frequency of the driving shaft in Hz.

    Returns
    -------
    float
        Driven shaft frequency in Hz.
    """
    return (drive_teeth / driven_teeth) * drive_shaft_freq


# ---------------------------------------------------------------------------
# Frequency matching utility
# ---------------------------------------------------------------------------


def frequency_match(
    observed: float,
    expected: float,
    tolerance: float = 0.03,
) -> bool:
    """Check whether *observed* matches *expected* within a relative tolerance.

    The match band is ``[expected * (1 - tolerance), expected * (1 + tolerance)]``.

    Parameters
    ----------
    observed : float
        Measured frequency in Hz.
    expected : float
        Predicted (theoretical) frequency in Hz.
    tolerance : float, optional
        Relative tolerance (default ``0.03``, i.e. +/-3 %).

    Returns
    -------
    bool
        ``True`` if *observed* lies within the tolerance band.
    """
    lower = expected * (1.0 - tolerance)
    upper = expected * (1.0 + tolerance)
    return lower <= observed <= upper
