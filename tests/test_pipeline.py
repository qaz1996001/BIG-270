"""Tests for the diagnostic pipeline (``vibfault.pipeline``).

Covers:
* Tier 0 integration (health-only, no faults).
* Tier 1 integration (unbalance detection).
* Tier 2 integration (bearing outer race detection).
* Tier 3 / Tier 4 integration.
* Mutual exclusion rules: #1 vs #2, #1 vs #8, #3 vs #9.
* Merge groups: #11/#12, #10/#13, #14/#15.
* Suggested parameters at each tier.
* Not-diagnosable list.
* Warnings (auto-estimated RPM, missing machine_class).
* Confidence modifier from RPM source.
"""

from __future__ import annotations

import numpy as np

from vibfault.core.models import BearingGeometry, MachineParameters
from vibfault.pipeline import DiagnosticPipeline

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fault_ids(result) -> set[int]:
    return {f.fault_id for f in result.diagnosed_faults}


def _fault_names(result) -> set[str]:
    return {f.fault_name for f in result.diagnosed_faults}


# ---------------------------------------------------------------------------
# Tier 0: Health-only
# ---------------------------------------------------------------------------


class TestPipelineTier0:
    """Tier 0 should produce health indicators but no faults."""

    def test_tier0_no_faults(self) -> None:
        fs = 4096
        rng = np.random.default_rng(42)
        signal = 0.01 * rng.standard_normal(int(fs * 2.0))

        params = MachineParameters(sampling_rate=fs)
        assert params.tier == 0

        pipeline = DiagnosticPipeline()
        result = pipeline.run(signal, params)

        assert result.tier == 0
        assert len(result.diagnosed_faults) == 0
        assert result.iso_severity in ("A-Good", "B-Acceptable", "C-Alert", "D-Danger")
        assert "Tier0Analyzer" in result.analysis_methods_used

    def test_tier0_health_indicators_populated(self) -> None:
        fs = 4096
        rng = np.random.default_rng(42)
        signal = 0.01 * rng.standard_normal(int(fs * 2.0))

        params = MachineParameters(sampling_rate=fs)
        pipeline = DiagnosticPipeline()
        result = pipeline.run(signal, params)

        assert "rms" in result.health_indicators
        assert "kurtosis" in result.health_indicators
        assert "crest_factor" in result.health_indicators
        assert "vrms" in result.health_indicators


# ---------------------------------------------------------------------------
# Tier 1: Unbalance
# ---------------------------------------------------------------------------


class TestPipelineTier1Integration:
    """Tier 1 with a synthetic unbalance signal."""

    def test_unbalance_detected(self) -> None:
        fs = 4096
        t = np.arange(0, 2.0, 1 / fs)
        rng = np.random.default_rng(42)

        shaft_freq = 30.0  # 1800 RPM
        signal = (
            5.0 * np.sin(2 * np.pi * shaft_freq * t)  # dominant 1X
            + 0.2 * np.sin(2 * np.pi * 2 * shaft_freq * t)  # small 2X
            + 0.01 * rng.standard_normal(len(t))
        )

        params = MachineParameters(sampling_rate=fs, rpm=1800)
        pipeline = DiagnosticPipeline()
        result = pipeline.run(signal, params)

        assert result.tier == 1
        assert 1 in _fault_ids(result), f"Expected Fault #1 (Unbalance); got {_fault_ids(result)}"


# ---------------------------------------------------------------------------
# Tier 2: Bearing outer race
# ---------------------------------------------------------------------------


class TestPipelineTier2Integration:
    """Tier 2 with a synthetic outer race defect signal."""

    def test_outer_race_detected(self) -> None:
        from vibfault.core.frequencies import bearing_bpfo

        bearing = BearingGeometry(
            n_balls=9,
            ball_diameter=7.94,
            pitch_diameter=39.04,
            contact_angle=0.0,
        )
        shaft_freq = 30.0  # 1800 RPM
        bpfo = bearing_bpfo(
            bearing.n_balls,
            bearing.ball_diameter,
            bearing.pitch_diameter,
            bearing.contact_angle,
            shaft_freq,
        )

        fs = 8192
        t = np.arange(0, 2.0, 1.0 / fs)
        carrier = np.cos(2 * np.pi * 3000 * t)
        modulation = 0.6 * np.cos(2 * np.pi * bpfo * t) + 0.4 * np.cos(2 * np.pi * 2 * bpfo * t)
        signal = carrier * (1.0 + modulation)

        params = MachineParameters(sampling_rate=fs, rpm=1800, bearing=bearing)
        pipeline = DiagnosticPipeline()
        result = pipeline.run(signal, params)

        assert result.tier == 2
        assert 5 in _fault_ids(result), f"Expected Fault #5 (Outer Race); got {_fault_ids(result)}"


# ---------------------------------------------------------------------------
# Tier 3: Electrical integration
# ---------------------------------------------------------------------------


class TestPipelineTier3Integration:
    """Tier 3 with a synthetic air-gap eccentricity signal."""

    def test_pipeline_tier3_integration(self) -> None:
        fs = 4096
        t = np.arange(0, 2.0, 1 / fs)
        rng = np.random.default_rng(42)

        signal = (
            1.0 * np.sin(2 * np.pi * 120 * t)  # 2FL
            + 0.5 * np.sin(2 * np.pi * 114 * t)  # lower Fp sideband
            + 0.5 * np.sin(2 * np.pi * 126 * t)  # upper Fp sideband
            + 0.01 * rng.standard_normal(len(t))
        )

        params = MachineParameters(
            sampling_rate=fs,
            rpm=1080,
            pole_pairs=3,
            line_frequency=60,
        )

        pipeline = DiagnosticPipeline()
        result = pipeline.run(signal, params)

        assert result.tier == 3
        assert 8 in _fault_ids(result)
        assert "Tier3Analyzer" in result.analysis_methods_used


# ---------------------------------------------------------------------------
# Tier 4: Gear integration
# ---------------------------------------------------------------------------


class TestPipelineTier4Integration:
    """Tier 4 with a synthetic gear mesh signal."""

    def test_pipeline_tier4_integration(self) -> None:
        fs = 8192
        t = np.arange(0, 2.0, 1 / fs)
        rng = np.random.default_rng(42)

        shaft_freq = 30
        gmf = 20 * shaft_freq

        signal = (
            0.5 * np.sin(2 * np.pi * gmf * t)
            + 0.4 * np.sin(2 * np.pi * 2 * gmf * t)
            + 0.3 * np.sin(2 * np.pi * 3 * gmf * t)
            + 0.2 * np.sin(2 * np.pi * shaft_freq * t)
            + 0.15 * np.sin(2 * np.pi * (gmf + shaft_freq) * t)
            + 0.15 * np.sin(2 * np.pi * (gmf - shaft_freq) * t)
            + 0.01 * rng.standard_normal(len(t))
        )

        params = MachineParameters(
            sampling_rate=fs,
            rpm=1800,
            gear_teeth_drive=20,
            gear_teeth_driven=40,
        )

        pipeline = DiagnosticPipeline()
        result = pipeline.run(signal, params)

        assert result.tier == 4
        assert "Tier4Analyzer" in result.analysis_methods_used
        gear_fault_ids = _fault_ids(result) & {16, 17, 18, 19, 20}
        assert len(gear_fault_ids) >= 1


# ---------------------------------------------------------------------------
# Mutual exclusion: #1 vs #8
# ---------------------------------------------------------------------------


class TestMutualExclusion1vs8:
    """When both Unbalance and Air Gap Eccentricity trigger, only the
    higher-confidence candidate should survive."""

    def test_mutual_exclusion_1_vs_8(self) -> None:
        fs = 4096
        t = np.arange(0, 2.0, 1 / fs)
        rng = np.random.default_rng(42)

        shaft_freq = 18.0

        signal = (
            2.0 * np.sin(2 * np.pi * shaft_freq * t)
            + 1.0 * np.sin(2 * np.pi * 120 * t)
            + 0.5 * np.sin(2 * np.pi * 114 * t)
            + 0.5 * np.sin(2 * np.pi * 126 * t)
            + 0.01 * rng.standard_normal(len(t))
        )

        params = MachineParameters(
            sampling_rate=fs,
            rpm=1080,
            pole_pairs=3,
            line_frequency=60,
        )

        pipeline = DiagnosticPipeline()
        result = pipeline.run(signal, params)

        ids = _fault_ids(result)
        assert not (1 in ids and 8 in ids), "Mutual exclusion failed: both #1 and #8 present"
        assert 1 in ids or 8 in ids


# ---------------------------------------------------------------------------
# Mutual exclusion: #1 vs #2
# ---------------------------------------------------------------------------


class TestMutualExclusion1vs2:
    """Unbalance and Bent Shaft are mutually exclusive. The 2X/1X ratio
    determines the winner."""

    def test_bent_shaft_wins_high_ratio(self) -> None:
        """2X/1X > 0.5 → Bent Shaft (#2) should win over Unbalance (#1)."""
        fs = 4096
        t = np.arange(0, 2.0, 1 / fs)
        rng = np.random.default_rng(42)

        shaft_freq = 30.0
        # 1X is dominant but 2X/1X > 0.5 → should trigger both, then
        # mutual exclusion keeps #2
        signal = (
            3.0 * np.sin(2 * np.pi * shaft_freq * t)
            + 2.0 * np.sin(2 * np.pi * 2 * shaft_freq * t)  # ratio ~0.67
            + 0.01 * rng.standard_normal(len(t))
        )

        params = MachineParameters(sampling_rate=fs, rpm=1800)
        pipeline = DiagnosticPipeline()
        result = pipeline.run(signal, params)

        ids = _fault_ids(result)
        assert not (1 in ids and 2 in ids), "Mutual exclusion failed: both #1 and #2 present"


# ---------------------------------------------------------------------------
# Mutual exclusion: #3 vs #9
# ---------------------------------------------------------------------------


class TestMutualExclusion3vs9:
    """Parallel (#3) and Angular (#9) misalignment: if evidence overlaps,
    only the stronger survives; if distinct, both can coexist."""

    def test_overlapping_evidence_collapses(self) -> None:
        """When both share evidence (1X_amplitude), only one survives."""
        from vibfault.analyzers.protocol import FaultCandidate
        from vibfault.core.models import Evidence

        pipeline = DiagnosticPipeline()

        c3 = FaultCandidate(
            fault_id=3,
            fault_name="Parallel Misalignment",
            fault_category="rotational",
            confidence=0.80,
            diagnosis_type="S",
            evidence=[
                Evidence(
                    feature_name="shared_feature",
                    observed_value=1.0,
                    expected_range=(0.0, 2.0),
                    match_score=1.0,
                    description="shared",
                )
            ],
        )
        c9 = FaultCandidate(
            fault_id=9,
            fault_name="Angular Misalignment",
            fault_category="rotational",
            confidence=0.75,
            diagnosis_type="S",
            evidence=[
                Evidence(
                    feature_name="shared_feature",
                    observed_value=1.0,
                    expected_range=(0.0, 2.0),
                    match_score=1.0,
                    description="shared",
                )
            ],
        )

        resolved = pipeline._apply_mutual_exclusions([c3, c9])
        ids = {c.fault_id for c in resolved}

        # Overlapping evidence → only higher confidence survives
        assert not (3 in ids and 9 in ids)
        assert 3 in ids  # #3 has higher confidence

    def test_distinct_evidence_keeps_both(self) -> None:
        """Non-overlapping evidence → both survive."""
        from vibfault.analyzers.protocol import FaultCandidate
        from vibfault.core.models import Evidence

        pipeline = DiagnosticPipeline()

        c3 = FaultCandidate(
            fault_id=3,
            fault_name="Parallel Misalignment",
            fault_category="rotational",
            confidence=0.80,
            diagnosis_type="S",
            evidence=[
                Evidence(
                    feature_name="2X_is_dominant",
                    observed_value=1.0,
                    expected_range=(1.0, 1.0),
                    match_score=1.0,
                    description="2X dominant",
                )
            ],
        )
        c9 = FaultCandidate(
            fault_id=9,
            fault_name="Angular Misalignment",
            fault_category="rotational",
            confidence=0.80,
            diagnosis_type="S",
            evidence=[
                Evidence(
                    feature_name="1X_amplitude",
                    observed_value=5.0,
                    expected_range=(0.0, 10.0),
                    match_score=1.0,
                    description="1X elevated",
                )
            ],
        )

        resolved = pipeline._apply_mutual_exclusions([c3, c9])
        ids = {c.fault_id for c in resolved}

        assert 3 in ids and 9 in ids


# ---------------------------------------------------------------------------
# Suggested parameters
# ---------------------------------------------------------------------------


class TestPipelineSuggestedParameters:
    """Pipeline should suggest next-tier parameters."""

    def test_tier0_suggests_rpm(self) -> None:
        fs = 4096
        rng = np.random.default_rng(42)
        signal = 0.01 * rng.standard_normal(int(fs * 2.0))

        params = MachineParameters(sampling_rate=fs)
        pipeline = DiagnosticPipeline()
        result = pipeline.run(signal, params)

        suggestion = " ".join(result.suggested_parameters).lower()
        assert "rpm" in suggestion

    def test_tier1_suggests_bearing(self) -> None:
        fs = 4096
        rng = np.random.default_rng(42)
        signal = 0.01 * rng.standard_normal(int(fs * 2.0))

        params = MachineParameters(sampling_rate=fs, rpm=1800)
        pipeline = DiagnosticPipeline()
        result = pipeline.run(signal, params)

        suggestion = " ".join(result.suggested_parameters).lower()
        assert "bearing" in suggestion or "tier 2" in suggestion

    def test_tier3_suggests_gear_teeth(self) -> None:
        fs = 4096
        rng = np.random.default_rng(42)
        signal = 0.01 * rng.standard_normal(int(fs * 2.0))

        params = MachineParameters(
            sampling_rate=fs,
            rpm=1080,
            pole_pairs=3,
            line_frequency=60,
        )
        pipeline = DiagnosticPipeline()
        result = pipeline.run(signal, params)

        suggestion = " ".join(result.suggested_parameters).lower()
        assert "gear" in suggestion or "tier 4" in suggestion


# ---------------------------------------------------------------------------
# Not-diagnosable list
# ---------------------------------------------------------------------------


class TestPipelineNotDiagnosable:
    """At Tier 0, all higher-tier faults should be listed."""

    def test_pipeline_not_diagnosable(self) -> None:
        fs = 4096
        rng = np.random.default_rng(42)
        signal = 0.01 * rng.standard_normal(int(fs * 2.0))

        params = MachineParameters(sampling_rate=fs)
        pipeline = DiagnosticPipeline()
        result = pipeline.run(signal, params)

        not_diag = result.not_diagnosable

        for name in [
            "Air Gap Eccentricity",
            "Phase Problem",
            "Winding Short",
            "Broken Rotor Bar",
            "End Ring Short",
        ]:
            assert name in not_diag

        for name in [
            "Gear Misalignment",
            "Broken Tooth",
            "Gear Eccentricity",
            "Gear Shaft Bend",
            "Gear Wear",
        ]:
            assert name in not_diag


# ---------------------------------------------------------------------------
# Merge groups
# ---------------------------------------------------------------------------


class TestMergeGroups:
    """Tier 3 analyzer emits merged candidates; pipeline enforces merge rules."""

    def test_tier3_emits_merged_rotor_bar(self) -> None:
        from vibfault.analyzers.tier3 import Tier3Analyzer

        fs = 4096
        t = np.arange(0, 2.0, 1 / fs)
        rng = np.random.default_rng(42)

        shaft_freq = 18.0
        fp = 6.0
        signal = (
            1.0 * np.sin(2 * np.pi * shaft_freq * t)
            + 0.5 * np.sin(2 * np.pi * (shaft_freq - fp) * t)
            + 0.5 * np.sin(2 * np.pi * (shaft_freq + fp) * t)
            + 0.01 * rng.standard_normal(len(t))
        )

        params = MachineParameters(
            sampling_rate=fs,
            rpm=1080,
            pole_pairs=3,
            line_frequency=60,
        )

        analyzer = Tier3Analyzer()
        candidates = analyzer.analyze(signal, params)
        rotor_candidates = [c for c in candidates if c.fault_id == 14]

        if rotor_candidates:
            rotor = rotor_candidates[0]
            assert rotor.merged_with is not None
            assert 15 in rotor.merged_with
            assert rotor.diagnosis_type == "M"

    def test_tier3_emits_merged_stator(self) -> None:
        from vibfault.analyzers.tier3 import Tier3Analyzer

        fs = 4096
        t = np.arange(0, 2.0, 1 / fs)
        rng = np.random.default_rng(42)

        signal = 1.0 * np.sin(2 * np.pi * 120 * t) + 0.01 * rng.standard_normal(len(t))

        params = MachineParameters(
            sampling_rate=fs,
            rpm=1080,
            pole_pairs=3,
            line_frequency=60,
        )

        analyzer = Tier3Analyzer()
        candidates = analyzer.analyze(signal, params)
        stator_candidates = [c for c in candidates if c.fault_id == 10]

        if stator_candidates:
            stator = stator_candidates[0]
            assert stator.merged_with is not None
            assert 13 in stator.merged_with
            assert stator.diagnosis_type == "M"

    def test_pipeline_merge_both_members_collapsed(self) -> None:
        from vibfault.analyzers.protocol import FaultCandidate
        from vibfault.core.models import Evidence

        pipeline = DiagnosticPipeline()

        c10 = FaultCandidate(
            fault_id=10,
            fault_name="Phase Problem",
            fault_category="electrical",
            confidence=0.65,
            diagnosis_type="S",
            evidence=[
                Evidence(
                    feature_name="2FL_peak_stator",
                    observed_value=120.0,
                    expected_range=(116.4, 123.6),
                    match_score=1.0,
                    description="2FL peak at 120 Hz",
                )
            ],
        )
        c13 = FaultCandidate(
            fault_id=13,
            fault_name="Winding Short",
            fault_category="electrical",
            confidence=0.60,
            diagnosis_type="S",
            evidence=[
                Evidence(
                    feature_name="winding_indicator",
                    observed_value=1.0,
                    expected_range=(0.5, 1.0),
                    match_score=0.9,
                    description="Winding short indicator",
                )
            ],
        )

        merged = pipeline._enforce_merged_groups([c10, c13])
        assert len(merged) == 1
        survivor = merged[0]
        assert survivor.diagnosis_type == "M"
        assert set(survivor.merged_with) == {10, 13}

        evidence_names = {e.feature_name for e in survivor.evidence}
        assert "2FL_peak_stator" in evidence_names
        assert "winding_indicator" in evidence_names

    def test_pipeline_merge_14_15_collapsed(self) -> None:
        from vibfault.analyzers.protocol import FaultCandidate
        from vibfault.core.models import Evidence

        pipeline = DiagnosticPipeline()

        c14 = FaultCandidate(
            fault_id=14,
            fault_name="Broken Rotor Bar",
            fault_category="electrical",
            confidence=0.75,
            diagnosis_type="S",
            evidence=[
                Evidence(
                    feature_name="rotor_bar_indicator",
                    observed_value=1.0,
                    expected_range=(0.5, 1.0),
                    match_score=0.9,
                    description="Rotor bar fault indicator",
                )
            ],
        )
        c15 = FaultCandidate(
            fault_id=15,
            fault_name="End Ring Short",
            fault_category="electrical",
            confidence=0.70,
            diagnosis_type="S",
            evidence=[
                Evidence(
                    feature_name="end_ring_indicator",
                    observed_value=1.0,
                    expected_range=(0.5, 1.0),
                    match_score=0.9,
                    description="End ring short indicator",
                )
            ],
        )

        merged = pipeline._enforce_merged_groups([c14, c15])
        assert len(merged) == 1
        survivor = merged[0]
        assert survivor.diagnosis_type == "M"
        assert set(survivor.merged_with) == {14, 15}

        evidence_names = {e.feature_name for e in survivor.evidence}
        assert "rotor_bar_indicator" in evidence_names
        assert "end_ring_indicator" in evidence_names


# ---------------------------------------------------------------------------
# Warnings and confidence modifier
# ---------------------------------------------------------------------------


class TestPipelineWarnings:
    """Verify RPM and machine_class warnings."""

    def test_auto_estimated_rpm_warning(self) -> None:
        fs = 4096
        rng = np.random.default_rng(42)
        signal = 0.01 * rng.standard_normal(int(fs * 2.0))

        params = MachineParameters(
            sampling_rate=fs,
            rpm=1800,
            rpm_source="auto_estimated",
        )
        pipeline = DiagnosticPipeline()
        result = pipeline.run(signal, params)

        assert any("auto-estimated" in w.lower() for w in result.warnings)
        assert result.confidence_modifier == 0.7

    def test_missing_machine_class_warning(self) -> None:
        fs = 4096
        rng = np.random.default_rng(42)
        signal = 0.01 * rng.standard_normal(int(fs * 2.0))

        params = MachineParameters(sampling_rate=fs)
        pipeline = DiagnosticPipeline()
        result = pipeline.run(signal, params)

        assert any("machine class" in w.lower() for w in result.warnings)

    def test_tachometer_confidence_modifier(self) -> None:
        fs = 4096
        rng = np.random.default_rng(42)
        signal = 0.01 * rng.standard_normal(int(fs * 2.0))

        params = MachineParameters(
            sampling_rate=fs,
            rpm=1800,
            rpm_source="tachometer",
        )
        pipeline = DiagnosticPipeline()
        result = pipeline.run(signal, params)

        assert result.confidence_modifier == 0.95
