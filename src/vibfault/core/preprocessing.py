"""Signal preprocessing functions for vibration fault classification.

Pure-function API for detrending, filtering, spectral analysis, envelope
analysis, cepstrum, time-frequency analysis, EMD, kurtogram, and
time-domain feature extraction.  All functions operate on 1-D NumPy
arrays and return NumPy arrays or plain Python scalars/dicts.

Typical usage (accelerometer data at 25.6 kHz)::

    sig = detrend(raw)
    sig = bandpass_filter(sig, fs=25600, low=10, high=10000)
    freqs, amps = compute_fft(sig, fs=25600)
    features = time_domain_features(sig)
    v_rms = velocity_rms(sig, fs=25600)
"""

from __future__ import annotations

import numpy as np
import numpy.fft as fft
from scipy import stats as sp_stats
from scipy.signal import (
    butter,
    filtfilt,
    get_window,
    hilbert,
    welch,
)
from scipy.signal import (
    detrend as _scipy_detrend,
)
from scipy.signal import (
    stft as _scipy_stft,
)

# ---------------------------------------------------------------------------
# Trend removal
# ---------------------------------------------------------------------------


def detrend(signal: np.ndarray) -> np.ndarray:
    """Remove DC offset and linear trend from *signal*.

    Delegates to :func:`scipy.signal.detrend` with ``type='linear'``, which
    subtracts the least-squares fit of a straight line from the data.

    Parameters
    ----------
    signal : np.ndarray
        1-D time-domain signal.

    Returns
    -------
    np.ndarray
        Detrended signal with the same length as the input.

    Raises
    ------
    ValueError
        If *signal* is not 1-D.
    """
    signal = np.asarray(signal, dtype=np.float64)
    if signal.ndim != 1:
        raise ValueError(f"Expected 1-D signal, got shape {signal.shape}")
    return _scipy_detrend(signal, type="linear")


# ---------------------------------------------------------------------------
# Windowing
# ---------------------------------------------------------------------------


def apply_window(signal: np.ndarray, window: str = "hann") -> np.ndarray:
    """Apply a symmetric window function to *signal*.

    Parameters
    ----------
    signal : np.ndarray
        1-D time-domain signal.
    window : str, optional
        Window name accepted by :func:`scipy.signal.get_window`
        (e.g. ``"hann"``, ``"hamming"``, ``"blackman"``, ``"kaiser"``).
        Defaults to ``"hann"``.

    Returns
    -------
    np.ndarray
        Windowed signal (element-wise product of *signal* and the window).
    """
    signal = np.asarray(signal, dtype=np.float64)
    if signal.ndim != 1:
        raise ValueError(f"Expected 1-D signal, got shape {signal.shape}")
    w = get_window(window, signal.size, fftbins=False)
    return signal * w


# ---------------------------------------------------------------------------
# Butterworth bandpass filter
# ---------------------------------------------------------------------------


def bandpass_filter(
    signal: np.ndarray,
    fs: float,
    low: float,
    high: float,
    order: int = 5,
) -> np.ndarray:
    """Zero-phase Butterworth bandpass filter.

    Parameters
    ----------
    signal : np.ndarray
        1-D time-domain signal.
    fs : float
        Sampling frequency in Hz.
    low : float
        Lower cutoff frequency in Hz.
    high : float
        Upper cutoff frequency in Hz.
    order : int, optional
        Filter order (default ``5``).

    Returns
    -------
    np.ndarray
        Bandpass-filtered signal with zero phase distortion.

    Raises
    ------
    ValueError
        If *low* >= *high* or if cutoff frequencies exceed the Nyquist limit.
    """
    signal = np.asarray(signal, dtype=np.float64)
    if signal.ndim != 1:
        raise ValueError(f"Expected 1-D signal, got shape {signal.shape}")

    nyquist = fs / 2.0
    if low >= high:
        raise ValueError(f"low ({low}) must be less than high ({high})")
    if high >= nyquist:
        raise ValueError(f"high cutoff ({high} Hz) must be below Nyquist ({nyquist} Hz)")
    if low <= 0:
        raise ValueError(f"low cutoff ({low} Hz) must be positive")

    b, a = butter(order, [low / nyquist, high / nyquist], btype="band")
    return filtfilt(b, a, signal)


# ---------------------------------------------------------------------------
# FFT
# ---------------------------------------------------------------------------


def compute_fft(
    signal: np.ndarray,
    fs: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute the single-sided FFT amplitude spectrum.

    Uses :func:`numpy.fft.rfft` and normalises by the signal length so that
    spectral amplitudes correspond to the peak amplitudes of sine components.

    Parameters
    ----------
    signal : np.ndarray
        1-D time-domain signal.
    fs : float
        Sampling frequency in Hz.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        ``(frequencies, amplitudes)`` where *frequencies* is in Hz and
        *amplitudes* is the single-sided peak amplitude spectrum.
    """
    signal = np.asarray(signal, dtype=np.float64)
    if signal.ndim != 1:
        raise ValueError(f"Expected 1-D signal, got shape {signal.shape}")

    n = signal.size
    spectrum = fft.rfft(signal)
    amplitudes = np.abs(spectrum) * (2.0 / n)
    # DC component should not be doubled
    amplitudes[0] /= 2.0
    # Nyquist bin (present when n is even) should not be doubled either
    if n % 2 == 0:
        amplitudes[-1] /= 2.0

    frequencies = fft.rfftfreq(n, d=1.0 / fs)
    return frequencies, amplitudes


# ---------------------------------------------------------------------------
# Power spectral density
# ---------------------------------------------------------------------------


def compute_psd(
    signal: np.ndarray,
    fs: float,
    nperseg: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Estimate the power spectral density using Welch's method.

    Parameters
    ----------
    signal : np.ndarray
        1-D time-domain signal.
    fs : float
        Sampling frequency in Hz.
    nperseg : int or None, optional
        Length of each segment for Welch averaging.  ``None`` (default) lets
        :func:`scipy.signal.welch` choose automatically (256 samples).

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        ``(frequencies, psd)`` where *psd* has units of ``signal_unit**2/Hz``.
    """
    signal = np.asarray(signal, dtype=np.float64)
    if signal.ndim != 1:
        raise ValueError(f"Expected 1-D signal, got shape {signal.shape}")

    kwargs: dict[str, object] = {"fs": fs}
    if nperseg is not None:
        kwargs["nperseg"] = nperseg

    frequencies, psd = welch(signal, **kwargs)
    return frequencies, psd


# ---------------------------------------------------------------------------
# Envelope analysis
# ---------------------------------------------------------------------------


def compute_envelope(
    signal: np.ndarray,
    fs: float,
    band: tuple[float, float] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Envelope (demodulation) analysis for bearing fault detection.

    The processing chain is:

    1. Optional bandpass filtering to isolate a resonance band.
    2. Analytic signal via the Hilbert transform.
    3. Envelope = absolute value of the analytic signal.
    4. Single-sided FFT of the envelope to reveal fault frequencies.

    Parameters
    ----------
    signal : np.ndarray
        1-D time-domain signal (typically acceleration).
    fs : float
        Sampling frequency in Hz.
    band : tuple[float, float] or None, optional
        ``(low, high)`` cutoff frequencies in Hz for an optional bandpass
        pre-filter.  ``None`` skips filtering.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        ``(envelope_frequencies, envelope_amplitudes)`` -- the FFT amplitude
        spectrum of the time-domain envelope.
    """
    signal = np.asarray(signal, dtype=np.float64)
    if signal.ndim != 1:
        raise ValueError(f"Expected 1-D signal, got shape {signal.shape}")

    if band is not None:
        signal = bandpass_filter(signal, fs, low=band[0], high=band[1])

    analytic = hilbert(signal)
    envelope = np.abs(analytic)

    # Remove DC from the envelope before taking its spectrum
    envelope = envelope - np.mean(envelope)

    return compute_fft(envelope, fs)


# ---------------------------------------------------------------------------
# Cepstrum analysis
# ---------------------------------------------------------------------------


def compute_cepstrum(
    signal: np.ndarray,
    fs: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute the real cepstrum of *signal*.

    The processing chain is:

    1. Compute FFT.
    2. Take the log of the squared magnitude (power cepstrum pathway).
    3. Compute the IFFT of the log-power spectrum.

    The result highlights periodicities in the frequency domain, making it
    useful for detecting repetitive sidebands (e.g. gear faults).

    Parameters
    ----------
    signal : np.ndarray
        1-D time-domain signal.
    fs : float
        Sampling frequency in Hz.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        ``(quefrency, cepstrum)`` where *quefrency* is in seconds and
        *cepstrum* is the real cepstrum values.
    """
    signal = np.asarray(signal, dtype=np.float64)
    if signal.ndim != 1:
        raise ValueError(f"Expected 1-D signal, got shape {signal.shape}")

    n = signal.size
    spectrum = fft.fft(signal)
    log_power = np.log(np.abs(spectrum) ** 2 + 1e-30)  # avoid log(0)
    cepstrum = np.real(fft.ifft(log_power))

    quefrency = np.arange(n) / fs
    return quefrency, cepstrum


# ---------------------------------------------------------------------------
# Time-domain statistical features
# ---------------------------------------------------------------------------


def time_domain_features(signal: np.ndarray) -> dict[str, float]:
    """Compute standard time-domain vibration features.

    Parameters
    ----------
    signal : np.ndarray
        1-D time-domain signal.

    Returns
    -------
    dict[str, float]
        Dictionary with the following keys:

        * ``rms`` -- root mean square
        * ``peak`` -- maximum absolute value
        * ``peak_to_peak`` -- max - min
        * ``crest_factor`` -- peak / rms
        * ``kurtosis`` -- excess kurtosis (Fisher definition, normal = 0)
        * ``skewness`` -- sample skewness
    """
    signal = np.asarray(signal, dtype=np.float64)
    if signal.ndim != 1:
        raise ValueError(f"Expected 1-D signal, got shape {signal.shape}")

    rms = float(np.sqrt(np.mean(signal**2)))
    peak = float(np.max(np.abs(signal)))
    peak_to_peak = float(np.max(signal) - np.min(signal))
    crest_factor = peak / rms if rms > 0.0 else 0.0

    return {
        "rms": rms,
        "peak": peak,
        "peak_to_peak": peak_to_peak,
        "crest_factor": crest_factor,
        "kurtosis": float(sp_stats.kurtosis(signal, fisher=True)),
        "skewness": float(sp_stats.skew(signal)),
    }


# ---------------------------------------------------------------------------
# Acceleration -> velocity RMS (ISO 10816)
# ---------------------------------------------------------------------------


def velocity_rms(signal: np.ndarray, fs: float) -> float:
    """Convert acceleration to velocity via frequency-domain integration and
    return the RMS velocity in mm/s.

    Integration of acceleration to velocity in the frequency domain is
    performed by dividing each spectral component by ``j * 2 * pi * f``.
    The DC component (0 Hz) is discarded to avoid division by zero.

    The result is the broadband RMS velocity suitable for ISO 10816 severity
    assessment.

    Parameters
    ----------
    signal : np.ndarray
        1-D acceleration signal in m/s^2.
    fs : float
        Sampling frequency in Hz.

    Returns
    -------
    float
        RMS velocity in mm/s.

    Notes
    -----
    ISO 10816 typically evaluates velocity RMS in the 10-1000 Hz band.
    Apply :func:`bandpass_filter` to the acceleration signal **before**
    calling this function if band-limited assessment is required.
    """
    signal = np.asarray(signal, dtype=np.float64)
    if signal.ndim != 1:
        raise ValueError(f"Expected 1-D signal, got shape {signal.shape}")

    n = signal.size
    accel_spectrum = fft.rfft(signal)
    frequencies = fft.rfftfreq(n, d=1.0 / fs)

    # Build the integration operator: divide by j*2*pi*f for f > 0
    omega = 2.0 * np.pi * frequencies
    # Avoid division by zero at DC
    omega[0] = 1.0  # placeholder; DC bin will be zeroed out

    velocity_spectrum = accel_spectrum / (1j * omega)
    # Zero the DC component (integration constant is unknown)
    velocity_spectrum[0] = 0.0

    # Back to time domain
    velocity = fft.irfft(velocity_spectrum, n=n)

    # RMS in m/s -> mm/s
    rms = float(np.sqrt(np.mean(velocity**2))) * 1000.0
    return rms


# ---------------------------------------------------------------------------
# Short-Time Fourier Transform (STFT)
# ---------------------------------------------------------------------------


def compute_stft(
    signal: np.ndarray,
    fs: float,
    nperseg: int = 256,
    noverlap: int | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute the Short-Time Fourier Transform magnitude.

    Wraps :func:`scipy.signal.stft` and returns the magnitude (not complex)
    spectrogram.

    Parameters
    ----------
    signal : np.ndarray
        1-D time-domain signal.
    fs : float
        Sampling frequency in Hz.
    nperseg : int, optional
        Length of each STFT segment (default ``256``).
    noverlap : int or None, optional
        Number of overlapping samples between segments.  ``None`` (default)
        uses ``nperseg // 2``.

    Returns
    -------
    tuple[np.ndarray, np.ndarray, np.ndarray]
        ``(times, frequencies, magnitude)`` where *magnitude* has shape
        ``(n_frequencies, n_times)``.
    """
    signal = np.asarray(signal, dtype=np.float64)
    if signal.ndim != 1:
        raise ValueError(f"Expected 1-D signal, got shape {signal.shape}")

    if noverlap is None:
        noverlap = nperseg // 2

    frequencies, times, zxx = _scipy_stft(
        signal,
        fs=fs,
        nperseg=nperseg,
        noverlap=noverlap,
    )
    return times, frequencies, np.abs(zxx)


# ---------------------------------------------------------------------------
# Continuous Wavelet Transform (CWT)
# ---------------------------------------------------------------------------


def compute_cwt(
    signal: np.ndarray,
    fs: float,
    wavelet: str = "morl",
    num_freqs: int = 64,
    freq_range: tuple[float, float] | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute the Continuous Wavelet Transform.

    Wraps :func:`pywt.cwt` and maps wavelet scales to physical frequencies.

    Parameters
    ----------
    signal : np.ndarray
        1-D time-domain signal.
    fs : float
        Sampling frequency in Hz.
    wavelet : str, optional
        Wavelet name accepted by PyWavelets (default ``"morl"`` for Morlet).
    num_freqs : int, optional
        Number of frequency bins (default ``64``).
    freq_range : tuple[float, float] or None, optional
        ``(low, high)`` frequency range in Hz.  ``None`` defaults to
        ``(1.0, fs / 2)``.

    Returns
    -------
    tuple[np.ndarray, np.ndarray, np.ndarray]
        ``(times, frequencies, coefficients)`` where *coefficients* is the
        magnitude matrix with shape ``(num_freqs, signal_length)``.
    """
    import pywt

    signal = np.asarray(signal, dtype=np.float64)
    if signal.ndim != 1:
        raise ValueError(f"Expected 1-D signal, got shape {signal.shape}")

    if freq_range is None:
        freq_range = (1.0, fs / 2.0)

    # Map desired frequencies to wavelet scales
    central_freq = pywt.central_frequency(wavelet)
    frequencies = np.linspace(freq_range[1], freq_range[0], num_freqs)
    scales = central_freq * fs / frequencies

    coefficients, _ = pywt.cwt(signal, scales, wavelet, sampling_period=1.0 / fs)

    times = np.arange(signal.size) / fs
    return times, frequencies, np.abs(coefficients)


# ---------------------------------------------------------------------------
# Spectral Kurtosis & Kurtogram
# ---------------------------------------------------------------------------


def compute_spectral_kurtosis(
    signal: np.ndarray,
    fs: float,
    band: tuple[float, float],
) -> float:
    """Compute the spectral kurtosis of *signal* in a given frequency band.

    The spectral kurtosis is the kurtosis of the envelope of the
    bandpass-filtered signal.  High values indicate impulsive content
    (e.g. bearing faults) concentrated in that frequency band.

    Parameters
    ----------
    signal : np.ndarray
        1-D time-domain signal.
    fs : float
        Sampling frequency in Hz.
    band : tuple[float, float]
        ``(low, high)`` cutoff frequencies in Hz.

    Returns
    -------
    float
        Spectral kurtosis value (excess kurtosis, Fisher definition).
    """
    signal = np.asarray(signal, dtype=np.float64)
    if signal.ndim != 1:
        raise ValueError(f"Expected 1-D signal, got shape {signal.shape}")

    filtered = bandpass_filter(signal, fs, low=band[0], high=band[1])
    envelope = np.abs(hilbert(filtered))
    return float(sp_stats.kurtosis(envelope, fisher=True))


def compute_kurtogram(
    signal: np.ndarray,
    fs: float,
    levels: int = 6,
) -> tuple[float, float, float]:
    """Compute the fast kurtogram to find the optimal demodulation band.

    Searches a dyadic grid of center-frequency / bandwidth combinations
    to find the frequency band with the highest spectral kurtosis.  This
    band is optimal for envelope analysis of impulsive faults (bearings).

    Parameters
    ----------
    signal : np.ndarray
        1-D time-domain signal.
    fs : float
        Sampling frequency in Hz.
    levels : int, optional
        Number of decomposition levels (default ``6``).  Each level doubles
        the frequency resolution, producing ``2^level`` bands at the finest
        level.

    Returns
    -------
    tuple[float, float, float]
        ``(center_freq, bandwidth, max_kurtosis)`` — the center frequency
        and bandwidth (both in Hz) of the band with the highest spectral
        kurtosis, along with the kurtosis value itself.
    """
    signal = np.asarray(signal, dtype=np.float64)
    if signal.ndim != 1:
        raise ValueError(f"Expected 1-D signal, got shape {signal.shape}")

    nyquist = fs / 2.0
    best_center = nyquist / 2.0
    best_bw = nyquist
    best_kurt = -np.inf

    for level in range(1, levels + 1):
        n_bands = 2**level
        bw = nyquist / n_bands

        for i in range(n_bands):
            low = i * bw
            high = (i + 1) * bw

            # Skip degenerate bands
            if low < 1.0:
                low = 1.0
            if high <= low or high >= nyquist:
                continue

            try:
                kurt = compute_spectral_kurtosis(signal, fs, band=(low, high))
            except (ValueError, RuntimeWarning):
                continue

            if kurt > best_kurt:
                best_kurt = kurt
                best_center = (low + high) / 2.0
                best_bw = high - low

    return (best_center, best_bw, float(best_kurt))


# ---------------------------------------------------------------------------
# Empirical Mode Decomposition (EMD)
# ---------------------------------------------------------------------------


def compute_emd(
    signal: np.ndarray,
    max_imfs: int | None = None,
) -> list[np.ndarray]:
    """Decompose *signal* into Intrinsic Mode Functions via EMD.

    Wraps the ``EMD`` class from the ``emd-signal`` package.  The returned
    IMFs are ordered from highest frequency to lowest.

    Parameters
    ----------
    signal : np.ndarray
        1-D time-domain signal.
    max_imfs : int or None, optional
        Maximum number of IMFs to extract.  ``None`` lets the algorithm
        decide when to stop.

    Returns
    -------
    list[np.ndarray]
        List of 1-D arrays, each an Intrinsic Mode Function.  The residual
        is included as the last element.
    """
    from PyEMD import EMD as _EMD

    signal = np.asarray(signal, dtype=np.float64)
    if signal.ndim != 1:
        raise ValueError(f"Expected 1-D signal, got shape {signal.shape}")

    emd = _EMD()
    if max_imfs is not None:
        emd.MAX_ITERATION = 1000
        imfs = emd.emd(signal, max_imf=max_imfs)
    else:
        imfs = emd.emd(signal)

    # emd.emd() returns a 2-D array (n_imfs, signal_length)
    return [imfs[i] for i in range(imfs.shape[0])]
