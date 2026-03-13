# vibfault

Parameter-Driven Adaptive Vibration Fault Classification System.

Diagnoses **20 fault types** across 6 categories (Rotor, Alignment, Bearing, Electrical, Fluid, Gear) with adaptive depth based on available machine parameters. Instead of failing when parameters are missing, the system gracefully degrades -- diagnosing fewer faults at lower confidence with fewer inputs, and unlocking more specific diagnoses as more parameters are provided.

## Tier System

| Tier | Additional Parameters | Diagnosable Faults | Methods |
|------|-----------------------|--------------------|---------|
| 0 | acceleration + sampling_rate | Health assessment (ISO 10816) | Time-domain statistics |
| 1 | + rpm | 7 faults (rotor, alignment, fluid) | FFT order analysis |
| 2 | + bearing_geometry | 10 faults (+ bearing defects) | Envelope analysis |
| 3 | + pole_pairs + line_frequency | 15 faults (+ electrical) | 2FL / sideband analysis |
| 4 | + gear_teeth | 20 faults (+ gear defects) | GMF analysis + cepstrum |

Tier is a **derived property** from nullable fields -- no mode flags, no branching. Each analyzer self-gates via `can_run()`.

## Quick Start

```bash
# Install
uv sync

# Run tests
uv run pytest

# Lint
uv run ruff check src/ tests/
```

## Usage

```python
import numpy as np
from vibfault.core.models import MachineParameters
from vibfault.pipeline import DiagnosticPipeline

# Provide whatever parameters you have
params = MachineParameters(
    sampling_rate=4096.0,
    rpm=1800.0,
    pole_pairs=2,
    line_frequency=60.0,
)

# Load or generate signal
signal = np.random.default_rng(42).standard_normal(8192)

# Run diagnosis -- pipeline auto-selects applicable analyzers
pipeline = DiagnosticPipeline()
result = pipeline.run(signal, params)

print(f"Tier: {result.tier}")
print(f"ISO Severity: {result.iso_severity}")
for fault in result.diagnosed_faults:
    print(f"  #{fault.fault_id} {fault.fault_name}: {fault.confidence:.0%}")
print(f"Not diagnosable: {result.not_diagnosable}")
print(f"Suggestions: {result.suggested_parameters}")
```

## Architecture

```
Signal --> Preprocessing --> [Tier 0..4 Analyzers] --> Conflict Resolution --> DiagnosisResult
                                    |
                          Each analyzer self-gates
                          via can_run(params)
```

### Analyzers

| Analyzer | Faults | Key Technique |
|----------|--------|---------------|
| Tier0Analyzer | Health only | RMS, kurtosis, crest factor, ISO 10816 |
| Tier1Analyzer | #1-3, #6, #9, #11/#12 | FFT peak ratios at 1X, 2X, 0.5X, sub-harmonics |
| Tier2Analyzer | #4, #5, #7 | Envelope spectrum at BPFO, BPFI, BSF |
| Tier3Analyzer | #8, #10/#13, #14/#15 | 2FL peak, pole-pass sidebands, RBPF |
| Tier4Analyzer | #16-#20 | GMF harmonics, cepstrum, broadband energy |

### Conflict Resolution

- **Mutual exclusions**: #1/#2 (Unbalance vs Bent Shaft), #3/#9 (Parallel vs Angular Misalignment), #1/#8 (Unbalance vs Air Gap Eccentricity)
- **Merged groups**: #11/#12, #10/#13, #14/#15 -- merged when both conditions present

## Tests

40 tests across 7 files:

```bash
uv run pytest -v
```

| File | Tests | Coverage |
|------|-------|----------|
| test_frequencies.py | 8 | Electrical + gear frequency formulas |
| test_preprocessing.py | 3 | Cepstrum computation |
| test_tier1.py | 4 | Looseness sub-harmonics (0.5X, 1/3X, 1/4X) |
| test_tier2.py | 3 | BSF classic + sideband-only detection |
| test_tier3.py | 6 | Air gap, rotor bar (+RBPF), stator, can_run |
| test_tier4.py | 6 | All 5 gear faults + can_run |
| test_pipeline.py | 10 | Integration, mutual exclusion, merge groups |

## Tech Stack

- **Python** 3.12+
- **numpy** -- FFT, spectral analysis
- **scipy** -- Hilbert transform, filters, Welch PSD
- **PyWavelets** -- Wavelet transforms
- **uv** -- Package management
- **ruff** -- Linting + formatting
- **pytest** -- Testing

## License

MIT
