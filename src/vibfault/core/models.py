"""Core data structures for the vibration fault classification system."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime


@dataclass
class BearingGeometry:
    """Physical geometry of a rolling-element bearing."""

    n_balls: int
    ball_diameter: float  # mm
    pitch_diameter: float  # mm
    contact_angle: float  # degrees


@dataclass
class MachineParameters:
    """Machine instrumentation and configuration parameters.

    The ``tier`` property is derived from which optional fields are populated,
    following the progressive enrichment model (Tier 0-5).
    """

    # Tier 0 -- always required
    sampling_rate: float  # Hz

    # Tier 1
    rpm: float | None = None
    rpm_source: str | None = None  # "manual" | "tachometer" | "auto_estimated"

    # Tier 2
    bearing: BearingGeometry | None = None
    bearing_model: str | None = None

    # Tier 3
    pole_pairs: int | None = None
    line_frequency: float | None = None  # Hz
    n_bars: int | None = None  # rotor bars (enhances Tier 3 diagnosis)

    # Tier 4
    gear_teeth_drive: int | None = None
    gear_teeth_driven: int | None = None

    # Tier 5
    critical_speed: float | None = None  # RPM

    # Classification metadata (not tier-gated)
    machine_class: str | None = None  # "I" | "II" | "III" | "IV"
    foundation_type: str | None = None  # "rigid" | "flexible"

    @property
    def tier(self) -> int:
        """Return the highest tier whose requirements are fully satisfied."""
        if self.critical_speed is not None:
            return 5
        if self.gear_teeth_drive is not None and self.gear_teeth_driven is not None:
            return 4
        if self.pole_pairs is not None and self.line_frequency is not None:
            return 3
        if self.bearing is not None:
            return 2
        if self.rpm is not None:
            return 1
        return 0


@dataclass
class Evidence:
    """A single piece of diagnostic evidence linking a spectral/time-domain
    feature to a fault hypothesis."""

    feature_name: str
    observed_value: float
    expected_range: tuple[float, float]
    match_score: float  # 0-1
    description: str


@dataclass
class FaultDiagnosis:
    """Diagnosis result for a single fault mode."""

    fault_id: int  # 1-20
    fault_name: str
    fault_category: str
    diagnosis_type: str  # "S" | "P" | "M" | "C"
    confidence: float  # 0-1
    evidence: list[Evidence] = field(default_factory=list)
    merged_with: list[int] | None = None


@dataclass
class DiagnosisResult:
    """Complete output of a diagnostic analysis run."""

    tier: int
    parameters: MachineParameters
    timestamp: datetime
    iso_severity: str  # "A-Good" | "B-Acceptable" | "C-Alert" | "D-Danger"
    iso_rms_velocity: float  # mm/s
    health_indicators: dict[str, float] = field(default_factory=dict)
    diagnosed_faults: list[FaultDiagnosis] = field(default_factory=list)
    not_diagnosable: list[str] = field(default_factory=list)
    suggested_parameters: list[str] = field(default_factory=list)
    rpm_source: str | None = None
    confidence_modifier: float = 1.0
    analysis_methods_used: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Rule-engine primitives
# ---------------------------------------------------------------------------


@dataclass
class Condition:
    """A single predicate evaluated against an extracted feature value."""

    feature: str
    operator: str
    threshold: float | tuple[float, float] | bool
    tolerance: float = 0.03
    description: str = ""


@dataclass
class DiagnosticRule:
    """Declarative rule mapping spectral/time-domain conditions to a fault."""

    fault_id: int
    fault_name: str
    min_tier: int
    required_features: list[str]
    conditions: list[Condition]
    weight: float
    confidence_base: float
    confidence_modifiers: dict[str, float] = field(default_factory=dict)
