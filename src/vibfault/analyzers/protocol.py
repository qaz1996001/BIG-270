"""Analyzer protocol and fault candidate data structures.

Defines the contract that every vibration fault analyzer must satisfy,
along with the canonical output type returned by each analyzer tier.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import numpy as np

    from vibfault.core.models import Evidence, MachineParameters


@dataclass
class FaultCandidate:
    """A single fault hypothesis produced by an analyzer.

    Attributes:
        fault_id: Unique numeric identifier for this fault type.
        fault_name: Human-readable fault label (e.g. "Unbalance").
        fault_category: Broad grouping (e.g. "rotational", "structural").
        confidence: Degree of belief in this diagnosis, 0.0 -- 1.0.
        diagnosis_type: Classification methodology used:
            "S" = spectral, "P" = pattern, "M" = model, "C" = composite.
        evidence: Supporting evidence objects that justify the diagnosis.
        merged_with: IDs of other candidates that were merged into this one
            during consensus or deduplication steps.
    """

    fault_id: int
    fault_name: str
    fault_category: str
    confidence: float
    diagnosis_type: str
    evidence: list[Evidence] = field(default_factory=list)
    merged_with: list[int] | None = None


class Analyzer(Protocol):
    """Protocol every analyzer tier must implement.

    ``prerequisites`` declares what :class:`MachineParameters` fields the
    analyzer needs beyond the bare minimum (acceleration array + sampling
    rate).  ``can_run`` performs a runtime check so the orchestrator can
    skip analyzers whose requirements are not met.  ``analyze`` does the
    actual work and returns zero or more :class:`FaultCandidate` objects.
    """

    def prerequisites(self) -> list[str]:
        """Return parameter names required by this analyzer."""
        ...

    def can_run(self, params: MachineParameters) -> bool:
        """Return *True* if *params* satisfies all prerequisites."""
        ...

    def analyze(
        self,
        signal: np.ndarray,
        params: MachineParameters,
    ) -> list[FaultCandidate]:
        """Run the analysis and return fault candidates."""
        ...
