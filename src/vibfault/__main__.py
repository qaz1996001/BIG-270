"""Entry point for vibfault CLI.

Supports:
* CSV input (1-column acceleration data).
* WAV input (uses first channel).
* JSON structured output.
* Interactive parameter specification via CLI flags.

Usage examples::

    # Minimal (Tier 0): health assessment only
    vibfault data.csv --sampling-rate 25600

    # Tier 1: add RPM
    vibfault data.csv --sampling-rate 25600 --rpm 1800

    # Tier 2: add bearing geometry
    vibfault data.csv --sampling-rate 25600 --rpm 1800 \\
        --bearing-n-balls 9 --bearing-ball-dia 7.94 \\
        --bearing-pitch-dia 39.04 --bearing-contact-angle 0

    # JSON output
    vibfault data.csv --sampling-rate 25600 --rpm 1800 --json
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

from vibfault.core.models import BearingGeometry, MachineParameters
from vibfault.pipeline import DiagnosticPipeline


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="vibfault",
        description=(
            "Parameter-Driven Adaptive Vibration Fault Classification System. "
            "Provide a signal file and machine parameters; the system automatically "
            "determines diagnostic depth based on available parameters."
        ),
    )

    # --- Input file ---
    parser.add_argument(
        "input_file",
        nargs="?",
        help="Path to signal file (CSV or WAV). If omitted, runs in info mode.",
    )

    # --- Tier 0 (always required with file) ---
    parser.add_argument(
        "--sampling-rate",
        "-fs",
        type=float,
        default=None,
        help="Sampling rate in Hz (required for CSV input; auto-detected for WAV).",
    )

    # --- Tier 1 ---
    parser.add_argument("--rpm", type=float, default=None, help="Shaft speed in RPM.")
    parser.add_argument(
        "--rpm-source",
        choices=["manual", "tachometer", "auto_estimated"],
        default="manual",
        help="How RPM was obtained (default: manual).",
    )

    # --- Tier 2: bearing geometry ---
    parser.add_argument(
        "--bearing-n-balls",
        type=int,
        default=None,
        help="Number of rolling elements.",
    )
    parser.add_argument(
        "--bearing-ball-dia",
        type=float,
        default=None,
        help="Ball diameter (mm).",
    )
    parser.add_argument(
        "--bearing-pitch-dia",
        type=float,
        default=None,
        help="Pitch diameter (mm).",
    )
    parser.add_argument(
        "--bearing-contact-angle",
        type=float,
        default=0.0,
        help="Contact angle (degrees, default 0).",
    )

    # --- Tier 3: electrical ---
    parser.add_argument("--pole-pairs", type=int, default=None, help="Number of pole pairs.")
    parser.add_argument(
        "--line-frequency",
        type=float,
        default=None,
        help="AC supply frequency (Hz).",
    )
    parser.add_argument("--n-bars", type=int, default=None, help="Number of rotor bars.")

    # --- Tier 4: gear ---
    parser.add_argument("--gear-teeth-drive", type=int, default=None, help="Teeth on driving gear.")
    parser.add_argument("--gear-teeth-driven", type=int, default=None, help="Teeth on driven gear.")

    # --- Classification metadata ---
    parser.add_argument(
        "--machine-class",
        choices=["I", "II", "III", "IV"],
        default=None,
        help="ISO 10816 machine class (default: II).",
    )

    # --- Output format ---
    parser.add_argument("--json", action="store_true", help="Output results as JSON.")

    return parser.parse_args(argv)


def _load_signal(path: Path, sampling_rate: float | None) -> tuple[np.ndarray, float]:
    """Load a signal from a CSV or WAV file.

    Returns (signal_array, sampling_rate).
    """
    suffix = path.suffix.lower()

    if suffix == ".wav":
        from scipy.io import wavfile

        fs_wav, data = wavfile.read(path)
        if data.ndim > 1:
            data = data[:, 0]  # first channel
        signal = data.astype(np.float64)
        # Normalise int16/int32 WAV to [-1, 1]
        if data.dtype in (np.int16, np.int32):
            signal = signal / np.iinfo(data.dtype).max
        fs = float(fs_wav)
        if sampling_rate is not None and sampling_rate != fs:
            print(
                f"Warning: --sampling-rate={sampling_rate} overrides WAV header rate={fs}",
                file=sys.stderr,
            )
            fs = sampling_rate
        return signal, fs

    # Default: CSV (single column of floats)
    if sampling_rate is None:
        print("Error: --sampling-rate is required for CSV input.", file=sys.stderr)
        sys.exit(1)

    values: list[float] = []
    with open(path, newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue
            try:
                values.append(float(row[0]))
            except ValueError:
                continue  # skip header rows
    if not values:
        print(f"Error: no numeric data found in {path}", file=sys.stderr)
        sys.exit(1)

    return np.array(values, dtype=np.float64), sampling_rate


def _build_params(args: argparse.Namespace, sampling_rate: float) -> MachineParameters:
    """Construct MachineParameters from CLI args."""
    bearing = None
    bearing_fields = [args.bearing_n_balls, args.bearing_ball_dia, args.bearing_pitch_dia]
    if all(v is not None for v in bearing_fields):
        bearing = BearingGeometry(
            n_balls=args.bearing_n_balls,
            ball_diameter=args.bearing_ball_dia,
            pitch_diameter=args.bearing_pitch_dia,
            contact_angle=args.bearing_contact_angle,
        )

    return MachineParameters(
        sampling_rate=sampling_rate,
        rpm=args.rpm,
        rpm_source=args.rpm_source if args.rpm is not None else None,
        bearing=bearing,
        pole_pairs=args.pole_pairs,
        line_frequency=args.line_frequency,
        n_bars=args.n_bars,
        gear_teeth_drive=args.gear_teeth_drive,
        gear_teeth_driven=args.gear_teeth_driven,
        machine_class=args.machine_class,
    )


def _format_text(result) -> str:
    """Format DiagnosisResult as human-readable text."""
    lines: list[str] = []
    lines.append(f"VibFault Diagnostic Report — Tier {result.tier}")
    lines.append("=" * 50)
    lines.append(f"ISO 10816 Severity : {result.iso_severity}")
    lines.append(f"Velocity RMS       : {result.iso_rms_velocity:.3f} mm/s")
    lines.append("")

    hi = result.health_indicators
    if hi:
        lines.append("Health Indicators:")
        for key, val in hi.items():
            lines.append(f"  {key:15s}: {val:.4f}")
        lines.append("")

    if result.diagnosed_faults:
        lines.append(f"Diagnosed Faults ({len(result.diagnosed_faults)}):")
        for f in result.diagnosed_faults:
            merged = f" [merged: {f.merged_with}]" if f.merged_with else ""
            lines.append(
                f"  #{f.fault_id:2d} {f.fault_name:30s} "
                f"conf={f.confidence:.2f} type={f.diagnosis_type}{merged}"
            )
            for ev in f.evidence:
                lines.append(f"       - {ev.description}")
    else:
        lines.append("No specific faults diagnosed at current tier.")

    if result.not_diagnosable:
        lines.append("")
        lines.append(f"Not diagnosable at Tier {result.tier} ({len(result.not_diagnosable)}):")
        for name in result.not_diagnosable:
            lines.append(f"  - {name}")

    if result.suggested_parameters:
        lines.append("")
        lines.append("Suggestions:")
        for s in result.suggested_parameters:
            lines.append(f"  -> {s}")

    if result.warnings:
        lines.append("")
        lines.append("Warnings:")
        for w in result.warnings:
            lines.append(f"  ! {w}")

    lines.append("")
    lines.append(f"Analysis methods: {', '.join(result.analysis_methods_used)}")
    return "\n".join(lines)


def _format_json(result) -> str:
    """Format DiagnosisResult as JSON string."""
    data = {
        "tier": result.tier,
        "iso_severity": result.iso_severity,
        "iso_rms_velocity": result.iso_rms_velocity,
        "health_indicators": result.health_indicators,
        "diagnosed_faults": [
            {
                "fault_id": f.fault_id,
                "fault_name": f.fault_name,
                "fault_category": f.fault_category,
                "diagnosis_type": f.diagnosis_type,
                "confidence": round(f.confidence, 4),
                "merged_with": f.merged_with,
                "evidence": [
                    {
                        "feature_name": e.feature_name,
                        "observed_value": round(e.observed_value, 6),
                        "expected_range": [
                            round(e.expected_range[0], 6),
                            round(e.expected_range[1], 6),
                        ],
                        "match_score": round(e.match_score, 4),
                        "description": e.description,
                    }
                    for e in f.evidence
                ],
            }
            for f in result.diagnosed_faults
        ],
        "not_diagnosable": result.not_diagnosable,
        "suggested_parameters": result.suggested_parameters,
        "warnings": result.warnings,
        "confidence_modifier": result.confidence_modifier,
        "analysis_methods_used": result.analysis_methods_used,
        "timestamp": result.timestamp.isoformat(),
    }
    return json.dumps(data, indent=2, ensure_ascii=False)


def main(argv: list[str] | None = None) -> None:
    """Run vibfault diagnostic pipeline from CLI."""
    args = _parse_args(argv)

    # Info mode: no input file
    if args.input_file is None:
        params = MachineParameters(sampling_rate=args.sampling_rate or 10000.0)
        print(f"VibFault v0.2.0 — Tier {params.tier} diagnostic ready")
        print(f"Current tier: {params.tier}")
        print("Provide an input file (CSV or WAV) to run diagnostics.")
        print("\nUsage: vibfault <signal.csv> --sampling-rate <Hz> [options]")
        print("       vibfault <signal.wav> [options]")
        print("\nRun 'vibfault --help' for full options.")
        return

    # Load signal
    path = Path(args.input_file)
    if not path.exists():
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    signal, fs = _load_signal(path, args.sampling_rate)
    params = _build_params(args, fs)

    duration = len(signal) / fs
    print(
        f"Loaded {len(signal)} samples at {fs:.0f} Hz (duration: {duration:.2f}s)",
        file=sys.stderr,
    )
    print(f"Parameters: Tier {params.tier}", file=sys.stderr)

    # Run pipeline
    pipeline = DiagnosticPipeline()
    result = pipeline.run(signal, params)

    # Output
    if args.json:
        print(_format_json(result))
    else:
        print(_format_text(result))


if __name__ == "__main__":
    main()
