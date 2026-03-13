"""Main diagnostic pipeline that orchestrates all analyzers and resolves conflicts.

The pipeline follows a data-driven design: all analyzers that CAN run WILL run.
There is no if-else tier branching. Each analyzer self-gates via ``can_run()``,
and the pipeline collects all fault candidates, resolves conflicts, and
assembles the final :class:`DiagnosisResult`.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from vibfault.analyzers.tier0 import Tier0Analyzer
from vibfault.analyzers.tier1 import Tier1Analyzer
from vibfault.analyzers.tier2 import Tier2Analyzer
from vibfault.analyzers.tier3 import Tier3Analyzer
from vibfault.analyzers.tier4 import Tier4Analyzer
from vibfault.core.models import (
    DiagnosisResult,
    FaultDiagnosis,
    MachineParameters,
)
from vibfault.core.preprocessing import apply_window, detrend

if TYPE_CHECKING:
    import numpy as np

    from vibfault.analyzers.protocol import FaultCandidate
    from vibfault.analyzers.tier0 import HealthIndicators

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Complete 20-fault catalog
# ---------------------------------------------------------------------------

_FAULT_CATALOG: list[dict[str, str | int]] = [
    {"fault_id": 1, "fault_name": "Unbalance", "fault_category": "Rotor", "min_tier": 1},
    {"fault_id": 2, "fault_name": "Bent Shaft", "fault_category": "Rotor", "min_tier": 1},
    {
        "fault_id": 3,
        "fault_name": "Parallel Misalignment",
        "fault_category": "Alignment",
        "min_tier": 1,
    },
    {"fault_id": 4, "fault_name": "Inner Race Defect", "fault_category": "Bearing", "min_tier": 2},
    {"fault_id": 5, "fault_name": "Outer Race Defect", "fault_category": "Bearing", "min_tier": 2},
    {
        "fault_id": 6,
        "fault_name": "Mechanical Looseness",
        "fault_category": "Structural",
        "min_tier": 1,
    },
    {"fault_id": 7, "fault_name": "Ball Defect", "fault_category": "Bearing", "min_tier": 2},
    {
        "fault_id": 8,
        "fault_name": "Air Gap Eccentricity",
        "fault_category": "Electrical",
        "min_tier": 3,
    },
    {
        "fault_id": 9,
        "fault_name": "Angular Misalignment",
        "fault_category": "Alignment",
        "min_tier": 1,
    },
    {"fault_id": 10, "fault_name": "Phase Problem", "fault_category": "Electrical", "min_tier": 3},
    {"fault_id": 11, "fault_name": "Oil Whirl", "fault_category": "Fluid", "min_tier": 1},
    {"fault_id": 12, "fault_name": "Oil Whip", "fault_category": "Fluid", "min_tier": 1},
    {"fault_id": 13, "fault_name": "Winding Short", "fault_category": "Electrical", "min_tier": 3},
    {
        "fault_id": 14,
        "fault_name": "Broken Rotor Bar",
        "fault_category": "Electrical",
        "min_tier": 3,
    },
    {"fault_id": 15, "fault_name": "End Ring Short", "fault_category": "Electrical", "min_tier": 3},
    {"fault_id": 16, "fault_name": "Gear Misalignment", "fault_category": "Gear", "min_tier": 4},
    {"fault_id": 17, "fault_name": "Broken Tooth", "fault_category": "Gear", "min_tier": 4},
    {"fault_id": 18, "fault_name": "Gear Eccentricity", "fault_category": "Gear", "min_tier": 4},
    {"fault_id": 19, "fault_name": "Gear Shaft Bend", "fault_category": "Gear", "min_tier": 4},
    {"fault_id": 20, "fault_name": "Gear Wear", "fault_category": "Gear", "min_tier": 4},
]

# Minimum confidence to include a fault in the diagnosed list.
_MIN_CONFIDENCE: float = 0.3

# Suggested-parameter messages indexed by tier.
_TIER_SUGGESTIONS: dict[int, str] = {
    0: "Provide rpm to unlock Tier 1 (5 additional faults)",
    1: "Provide bearing_model or bearing geometry to unlock Tier 2 (3 additional faults)",
    2: "Provide pole_pairs and line_frequency to unlock Tier 3 (4 additional faults)",
    3: "Provide gear_teeth_drive and gear_teeth_driven to unlock Tier 4 (5 additional faults)",
    4: "Provide critical_speed to unlock Tier 5 (full 20-fault coverage)",
}


class DiagnosticPipeline:
    """Orchestrates all analyzers and assembles results.

    Design: all analyzers that CAN run WILL run.  No if-else tier branching.
    Each analyzer self-gates via ``can_run()``.
    """

    def __init__(self) -> None:
        self.analyzers = [
            Tier0Analyzer(),
            Tier1Analyzer(),
            Tier2Analyzer(),
            Tier3Analyzer(),
            Tier4Analyzer(),
        ]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, signal: np.ndarray, params: MachineParameters) -> DiagnosisResult:
        """Execute the full diagnostic pipeline.

        Args:
            signal: 1-D acceleration signal (m/s^2).
            params: Machine parameters that gate which analyzers can run.

        Returns:
            A fully assembled :class:`DiagnosisResult`.
        """
        # 1. Preprocess signal
        processed = apply_window(detrend(signal))

        # 2. Run all applicable analyzers
        all_candidates: list[FaultCandidate] = []
        methods_used: list[str] = []
        health: HealthIndicators | None = None

        for analyzer in self.analyzers:
            if analyzer.can_run(params):
                candidates = analyzer.analyze(processed, params)
                all_candidates.extend(candidates)
                methods_used.append(type(analyzer).__name__)
                # Capture Tier0 health indicators
                if isinstance(analyzer, Tier0Analyzer):
                    health = analyzer.health

        logger.info(
            "Pipeline collected %d candidates from %s",
            len(all_candidates),
            methods_used,
        )

        # 3. Resolve conflicts
        resolved = self._resolve_conflicts(all_candidates)

        # 4. Assemble result
        return self._assemble_result(resolved, params, health, methods_used)

    # ------------------------------------------------------------------
    # Conflict resolution
    # ------------------------------------------------------------------

    def _resolve_conflicts(
        self,
        candidates: list[FaultCandidate],
    ) -> list[FaultCandidate]:
        """Apply mutual exclusion, deduplication, and merge rules.

        Processing order:
            1. Deduplicate: group by fault_id, keep highest confidence and
               merge evidence from all sources.
            2. Apply mutual-exclusion rules for known conflicting pairs.
            3. Handle merged groups (11/12 stay merged).
            4. Drop candidates below the minimum confidence threshold.
        """
        if not candidates:
            return []

        # --- Step 1: Deduplicate by fault_id ---------------------------------
        deduped = self._deduplicate(candidates)

        # --- Step 2: Mutual exclusion ----------------------------------------
        resolved = self._apply_mutual_exclusions(deduped)

        # --- Step 3: Enforce merged groups -----------------------------------
        resolved = self._enforce_merged_groups(resolved)

        # --- Step 4: Confidence gate -----------------------------------------
        resolved = [c for c in resolved if c.confidence >= _MIN_CONFIDENCE]

        return resolved

    @staticmethod
    def _deduplicate(candidates: list[FaultCandidate]) -> list[FaultCandidate]:
        """Group by fault_id; keep the highest-confidence entry and merge evidence."""
        groups: dict[int, list[FaultCandidate]] = defaultdict(list)
        for c in candidates:
            groups[c.fault_id].append(c)

        result: list[FaultCandidate] = []
        for _fault_id, group in groups.items():
            # Sort descending by confidence; take the best as the base.
            group.sort(key=lambda c: c.confidence, reverse=True)
            best = group[0]

            # Merge evidence from lower-confidence duplicates.
            if len(group) > 1:
                seen_features: set[str] = {e.feature_name for e in best.evidence}
                for other in group[1:]:
                    for ev in other.evidence:
                        if ev.feature_name not in seen_features:
                            best.evidence.append(ev)
                            seen_features.add(ev.feature_name)

            result.append(best)
        return result

    @staticmethod
    def _apply_mutual_exclusions(
        candidates: list[FaultCandidate],
    ) -> list[FaultCandidate]:
        """Resolve mutually exclusive fault pairs.

        Rules:
            * #1 (Unbalance) vs #2 (Bent Shaft):
                Use the ``2X_to_1X_ratio`` evidence.  If ratio > 0.5 keep #2,
                otherwise keep #1.  If no ratio evidence exists, keep the
                higher-confidence candidate.
            * #3 (Parallel Misalignment) vs #9 (Angular Misalignment):
                Keep both when they have distinct evidence; otherwise keep the
                higher-confidence candidate.
        """
        by_id: dict[int, FaultCandidate] = {c.fault_id: c for c in candidates}

        # --- #1 vs #2 -------------------------------------------------------
        if 1 in by_id and 2 in by_id:
            ratio = _find_evidence_value(by_id[2], "2X_to_1X_ratio")
            if ratio is not None:
                if ratio > 0.5:
                    del by_id[1]
                else:
                    del by_id[2]
            else:
                # Fall back to highest confidence
                loser = 1 if by_id[1].confidence < by_id[2].confidence else 2
                del by_id[loser]

        # --- #1 vs #8 -------------------------------------------------------
        # Unbalance vs Air Gap Eccentricity: with electrical params, if
        # 2FL sidebands point to air gap, prefer #8 over #1.
        if 1 in by_id and 8 in by_id:
            if by_id[8].confidence >= by_id[1].confidence:
                del by_id[1]
            else:
                del by_id[8]

        # --- #3 vs #9 -------------------------------------------------------
        if 3 in by_id and 9 in by_id:
            ev_3 = {e.feature_name for e in by_id[3].evidence}
            ev_9 = {e.feature_name for e in by_id[9].evidence}
            if ev_3 & ev_9:
                # Overlapping evidence -- keep the stronger candidate only
                loser = 3 if by_id[3].confidence < by_id[9].confidence else 9
                del by_id[loser]
            # else: distinct evidence, keep both

        return list(by_id.values())

    @staticmethod
    def _enforce_merged_groups(
        candidates: list[FaultCandidate],
    ) -> list[FaultCandidate]:
        """Ensure merged-group faults are reported correctly.

        Merge groups (at Tier 1-4):
            * #11 (Oil Whirl) + #12 (Oil Whip) --> single merged candidate.
            * #10 (Phase Problem) + #13 (Winding Short) --> merged at Tier 3.
            * #14 (Broken Rotor Bar) + #15 (End Ring Short) --> merged at Tier 3.

        If both members of a merge group are present, they are collapsed into a
        single :class:`FaultCandidate` with ``diagnosis_type="M"`` and the
        ``merged_with`` field populated.
        """
        by_id: dict[int, FaultCandidate] = {c.fault_id: c for c in candidates}

        merge_groups: list[tuple[int, int]] = [
            (11, 12),
            (10, 13),
            (14, 15),
        ]

        for id_a, id_b in merge_groups:
            if id_a in by_id and id_b in by_id:
                a, b = by_id[id_a], by_id[id_b]
                # Keep the higher-confidence entry as the primary.
                primary, secondary = (a, b) if a.confidence >= b.confidence else (b, a)
                primary.diagnosis_type = "M"
                primary.merged_with = [primary.fault_id, secondary.fault_id]

                # Merge evidence
                seen: set[str] = {e.feature_name for e in primary.evidence}
                for ev in secondary.evidence:
                    if ev.feature_name not in seen:
                        primary.evidence.append(ev)
                        seen.add(ev.feature_name)

                by_id[primary.fault_id] = primary
                del by_id[secondary.fault_id]

        return list(by_id.values())

    # ------------------------------------------------------------------
    # Result assembly
    # ------------------------------------------------------------------

    def _assemble_result(
        self,
        candidates: list[FaultCandidate],
        params: MachineParameters,
        health: HealthIndicators | None,
        methods_used: list[str],
    ) -> DiagnosisResult:
        """Build the final :class:`DiagnosisResult`.

        Args:
            candidates: Conflict-resolved fault candidates.
            params: Original machine parameters.
            health: Tier-0 health indicators (may be ``None`` if Tier0 did
                not run, though in practice it always does).
            methods_used: Names of analyzer classes that ran.

        Returns:
            Fully populated :class:`DiagnosisResult`.
        """
        tier = params.tier

        # --- Convert candidates to FaultDiagnosis objects --------------------
        diagnosed: list[FaultDiagnosis] = sorted(
            (self._candidate_to_diagnosis(c) for c in candidates),
            key=lambda d: d.confidence,
            reverse=True,
        )

        # --- Health indicators dict ------------------------------------------
        health_indicators: dict[str, float] = {}
        iso_severity = "B-Acceptable"
        iso_rms_velocity = 0.0

        if health is not None:
            health_indicators = {
                "rms": health.rms,
                "kurtosis": health.kurtosis,
                "crest_factor": health.crest_factor,
                "vrms": health.vrms,
            }
            iso_severity = health.iso_zone
            iso_rms_velocity = health.vrms

        # --- Not diagnosable list -------------------------------------------
        diagnosed_ids = {d.fault_id for d in diagnosed}
        # Also include merged partner ids
        for d in diagnosed:
            if d.merged_with:
                diagnosed_ids.update(d.merged_with)

        not_diagnosable = [
            f["fault_name"]
            for f in _FAULT_CATALOG
            if f["fault_id"] not in diagnosed_ids and f["min_tier"] > tier
        ]

        # --- Suggested parameters for next tier ------------------------------
        suggested_parameters: list[str] = []
        if tier in _TIER_SUGGESTIONS:
            suggested_parameters.append(_TIER_SUGGESTIONS[tier])

        # --- Warnings --------------------------------------------------------
        warnings: list[str] = []
        if params.rpm_source == "auto_estimated":
            warnings.append(
                "RPM was auto-estimated from FFT; "
                "confidence of RPM-dependent diagnoses reduced by 30%."
            )
        if params.machine_class is None:
            warnings.append(
                "Machine class not provided; defaulting to Class II for ISO 10816 assessment."
            )

        # --- Confidence modifier from RPM source ----------------------------
        confidence_modifier = 1.0
        if params.rpm_source == "auto_estimated":
            confidence_modifier = 0.7
        elif params.rpm_source == "tachometer":
            confidence_modifier = 0.95

        return DiagnosisResult(
            tier=tier,
            parameters=params,
            timestamp=datetime.now(UTC),
            iso_severity=iso_severity,
            iso_rms_velocity=iso_rms_velocity,
            health_indicators=health_indicators,
            diagnosed_faults=diagnosed,
            not_diagnosable=not_diagnosable,
            suggested_parameters=suggested_parameters,
            rpm_source=params.rpm_source,
            confidence_modifier=confidence_modifier,
            analysis_methods_used=methods_used,
            warnings=warnings,
        )

    @staticmethod
    def _candidate_to_diagnosis(candidate: FaultCandidate) -> FaultDiagnosis:
        """Convert a :class:`FaultCandidate` into a :class:`FaultDiagnosis`."""
        return FaultDiagnosis(
            fault_id=candidate.fault_id,
            fault_name=candidate.fault_name,
            fault_category=candidate.fault_category,
            diagnosis_type=candidate.diagnosis_type,
            confidence=candidate.confidence,
            evidence=list(candidate.evidence),
            merged_with=candidate.merged_with,
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _find_evidence_value(
    candidate: FaultCandidate,
    feature_name: str,
) -> float | None:
    """Return the ``observed_value`` from the first evidence entry matching
    *feature_name*, or ``None`` if not found.
    """
    for ev in candidate.evidence:
        if ev.feature_name == feature_name:
            return ev.observed_value
    return None
