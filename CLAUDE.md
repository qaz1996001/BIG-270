# CLAUDE.md — Parameter-Driven Adaptive Vibration Fault Classification System

> **Project Code**: BIG-270
> **Language**: Bilingual (English code/API, 繁體中文 docs/comments)
> **Status**: Tier 0-4 implemented (20/20 faults), 156 tests passing

---

## Project Overview

A parameter-driven vibration fault classification system that **adapts diagnostic depth based on available machine parameters**. Core philosophy: instead of failing when parameters are missing, the system gracefully degrades — diagnosing fewer faults at lower confidence with fewer inputs, and unlocking more specific diagnoses as more parameters are provided.

**20 fault types** across 6 categories: Rotor, Alignment, Bearing, Electrical, Fluid, Gear.

---

## Tier System (Core Architecture)

| Tier | Required Parameters | Diagnosable Faults | Status |
|------|--------------------|--------------------|--------|
| 0 | acceleration + sampling_rate | 0 (health assessment only) | Implemented |
| 1 | + rpm | 7 (5 specific + 1 merged group) | Implemented |
| 2 | + bearing_geometry | 10 (8 specific + 1 merged group) | Implemented |
| 3 | + pole_pairs + line_frequency | 15 (10 specific + 3 merged) | Implemented |
| 4 | + gear_teeth_drive + gear_teeth_driven | 20 (14 specific + 3 merged) | Implemented |
| 5 | + current_signal + critical_speed | 20 (full MCSA coverage) | Future |

**Key design**: Tier is a **derived property** from nullable fields — no mode flags, no `if tier ==` branches. Each analyzer checks its own prerequisites via `can_run()`.

---

## Source Layout

```
src/vibfault/
├── __init__.py
├── __main__.py
├── pipeline.py                    # Orchestration + conflict resolution
├── core/
│   ├── models.py                  # MachineParameters, DiagnosisResult, Evidence, etc.
│   ├── frequencies.py             # Bearing, electrical, gear frequency formulas
│   └── preprocessing.py           # detrend, apply_window, compute_fft, cepstrum, STFT, CWT, kurtogram, EMD
├── analyzers/
│   ├── protocol.py                # FaultCandidate dataclass + Analyzer protocol
│   ├── _helpers.py                # Shared: find_peak_near, find_harmonics, check_sidebands
│   ├── tier0.py                   # ISO 10816 health assessment
│   ├── tier1.py                   # Order analysis (6 faults)
│   ├── tier2.py                   # Envelope analysis (3 bearing faults)
│   ├── tier3.py                   # Electrical faults (5 faults in 3 groups)
│   └── tier4.py                   # Gear faults (5 faults)
└── rules/
    └── __init__.py

tests/
├── test_frequencies.py            # 27 tests — bearing + electrical + gear formulas + frequency_match
├── test_preprocessing.py          # 40 tests — detrend, window, FFT, envelope, cepstrum, STFT, CWT, kurtogram, EMD, features, vrms
├── test_tier0.py                  # 16 tests — ISO 10816 severity, health indicators, anomaly detection
├── test_tier1.py                  # 17 tests — all 6 fault rules + auto RPM penalty + can_run
├── test_tier2.py                  # 12 tests — inner/outer/ball defects + auto RPM + can_run
├── test_tier3.py                  # 6 tests — air gap, rotor bar, stator
├── test_tier4.py                  # 6 tests — 5 gear faults + can_run
└── test_pipeline.py               # 22 tests — Tier 0-4 integration, mutual exclusions, merge, warnings
```

### Key Document Roles

| Document | Role |
|----------|------|
| `claudedocs/brainstorm_*.md` | **Primary spec** — tier system, data structures, rule engine, pipeline architecture, all 20 fault rules |
| `claudedocs/research_*.md` | **Technical reference** — signal processing methods, diagnostic rules per fault, Python tooling, MATLAB validation, ML roadmap |
| `新增 文字文件.txt` | Canonical fault list (20 types, Chinese) |
| `*.pdf` | Academic reference on deep transfer learning for fault diagnosis |
| `*.docx` | Original client/internal specification |

---

## Design Philosophy

| Philosopher | Principle | Application |
|-------------|-----------|-------------|
| **Ken Thompson** | Bottom-up composable primitives | Tier 0 → Tier 5 layered; each analyzer is independent |
| **Donald Knuth** | Mathematical precision | All formulas specified with units; ±3% tolerance justified |
| **Linus Torvalds** | Data structures drive behavior | Nullable fields determine tier; no control flags |
| **Martin Fowler** | YAGNI + evolutionary design | Tiers 0-4 implemented; Tier 5 deferred until current_signal needed |

---

## Tech Stack

### Tooling
- **Package manager**: `uv` (fast Python package manager & project tool)
- **Linter**: `ruff` (fast Python linter & formatter)
- **Type checker**: `ty` (Rust-based Python type checker by Astral)
- **Testing**: `pytest`
- **Python**: 3.12+

### Core Dependencies
| Purpose | Package |
|---------|---------|
| FFT / spectral analysis | `numpy` (`numpy.fft`) |
| Signal processing | `scipy` (`scipy.signal`) — Hilbert, filters, welch |
| Wavelet transforms | `pywt` (PyWavelets) |
| Visualization | `matplotlib`, `plotly` |

### Future (ML)
| Purpose | Package |
|---------|---------|
| Traditional ML | `scikit-learn`, `xgboost`, `lightgbm` |
| Deep Learning | `pytorch` |
| Datasets | CWRU, Paderborn, MFPT, PHM2009 |

---

## Development Commands

```bash
# Install / sync
uv sync                        # Sync all dependencies

# Code quality
uv run ruff check src/ tests/  # Lint
uv run ruff format src/ tests/ # Format
uv run ruff check --fix .      # Auto-fix lint issues

# Tests
uv run pytest                  # Run all 141 tests
uv run pytest tests/test_tier3.py -v  # Run specific test file

# Run
uv run python -m vibfault      # Run main module
```

---

## Bilingual Context

- **Code**: English identifiers, docstrings, comments
- **Design docs** (`claudedocs/`): 繁體中文 with English technical terms
- **Fault names**: Bilingual (e.g., "Unbalance 不平衡")
- **User-facing output**: Should support both languages

---

## Architecture Notes

### Data Flow
```
Signal → Preprocessing → [Tier 0..N Analyzers in parallel] → Conflict Resolution → Result Assembly
```

### Key Data Structures
- `MachineParameters` — nullable fields, tier is `@property`; includes `n_bars` for RBPF
- `BearingGeometry` — n_balls, ball_diameter, pitch_diameter, contact_angle
- `DiagnosisResult` — ISO severity, health indicators, fault list, suggestions
- `FaultDiagnosis` — fault_id, confidence, evidence list, diagnosis_type (S/P/M/C)
- `FaultCandidate` — intermediate result from each analyzer, merged by pipeline

### Analyzer Protocol
Each analyzer implements: `prerequisites()`, `can_run(params)`, `analyze(signal, params)`

### Conflict Resolution
- **Mutual exclusions**: #1/#2 (Unbalance/Bent Shaft), #3/#9 (Parallel/Angular Misalignment), #1/#8 (Unbalance/Air Gap Eccentricity)
- **Merged groups**: #11/#12 (Oil Whirl/Whip), #10/#13 (Phase/Winding), #14/#15 (Rotor Bar/End Ring)

---

## Conventions

- Frequency tolerance: ±3% default (justified by slip variation, FFT resolution, manufacturing tolerance); ±5% for auto-estimated RPM
- Confidence: 0.0–1.0 float; modifiers for RPM source (auto=×0.7, tachometer=×0.95)
- ISO 10816: Default to Class II when machine_class not provided
- Minimum confidence to report: 0.3
- Sideband detection: requires amplitude ≥1% of carrier peak (noise guard)
- Stator discriminator: only checks 1X sidebands when 1X is above noise floor

---

## 20 Fault Catalog

| ID | Name | Category | Tier | Type |
|----|------|----------|------|------|
| 1 | Unbalance | Rotor | 1 | S |
| 2 | Bent Shaft | Rotor | 1 | S |
| 3 | Parallel Misalignment | Alignment | 1 | S |
| 4 | Inner Race Defect | Bearing | 2 | S |
| 5 | Outer Race Defect | Bearing | 2 | S |
| 6 | Mechanical Looseness | Structural | 1 | S |
| 7 | Ball Defect | Bearing | 2 | S |
| 8 | Air Gap Eccentricity | Electrical | 3 | S |
| 9 | Angular Misalignment | Alignment | 1 | S |
| 10 | Phase Problem | Electrical | 3 | M (with #13) |
| 11 | Oil Whirl | Fluid | 1 | M (with #12) |
| 12 | Oil Whip | Fluid | 1 | M (with #11) |
| 13 | Winding Short | Electrical | 3 | M (with #10) |
| 14 | Broken Rotor Bar | Electrical | 3 | M (with #15) |
| 15 | End Ring Short | Electrical | 3 | M (with #14) |
| 16 | Gear Misalignment | Gear | 4 | S |
| 17 | Broken Tooth | Gear | 4 | S |
| 18 | Gear Eccentricity | Gear | 4 | S |
| 19 | Gear Shaft Bend | Gear | 4 | S |
| 20 | Gear Wear | Gear | 4 | S |
