"""Tests for the diagnostic pipeline (``vibfault.pipeline``).

Covers Tier 3 / Tier 4 integration, mutual exclusion rules, merge groups,
suggested parameters, and the not-diagnosable list.
"""

from __future__ import annotations

import numpy as np

from vibfault.core.models import MachineParameters
from vibfault.pipeline import DiagnosticPipeline

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fault_ids(result) -> set[int]:
    """Return the set of fault IDs from diagnosed_faults."""
    return {f.fault_id for f in result.diagnosed_faults}


def _fault_names(result) -> set[str]:
    """Return the set of fault names from diagnosed_faults."""
    return {f.fault_name for f in result.diagnosed_faults}


# ---------------------------------------------------------------------------
# Test 1: Tier 3 electrical integration
# ---------------------------------------------------------------------------


class TestPipelineTier3Integration:
    """Tier 3 with a synthetic air-gap eccentricity signal (2FL + Fp sidebands)."""

    def test_pipeline_tier3_integration(self) -> None:
        fs = 4096
        t = np.arange(0, 2.0, 1 / fs)
        rng = np.random.default_rng(42)

        # 6-pole motor: rpm=1080, pole_pairs=3, line_freq=60
        #   shaft_freq = 18 Hz, f_sync = 20 Hz, f_slip = 2 Hz, Fp = 6 Hz
        # 2FL = 120 Hz, Fp sidebands at 114 and 126 Hz
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

        # Tier must be 3 (pole_pairs + line_frequency provided, no gear_teeth)
        assert result.tier == 3

        # Fault #8 (Air Gap Eccentricity) must be detected
        assert 8 in _fault_ids(result), (
            f"Expected fault #8 in diagnosed_faults, got {_fault_ids(result)}"
        )

        # Tier3Analyzer must appear in analysis_methods_used
        assert "Tier3Analyzer" in result.analysis_methods_used


# ---------------------------------------------------------------------------
# Test 2: Tier 4 gear integration
# ---------------------------------------------------------------------------


class TestPipelineTier4Integration:
    """Tier 4 with a synthetic gear mesh signal."""

    def test_pipeline_tier4_integration(self) -> None:
        fs = 8192
        t = np.arange(0, 2.0, 1 / fs)
        rng = np.random.default_rng(42)

        shaft_freq = 30  # Hz (1800 RPM)
        gmf = 20 * shaft_freq  # 600 Hz

        signal = (
            0.5 * np.sin(2 * np.pi * gmf * t)
            + 0.4 * np.sin(2 * np.pi * 2 * gmf * t)
            + 0.3 * np.sin(2 * np.pi * 3 * gmf * t)
            + 0.2 * np.sin(2 * np.pi * shaft_freq * t)  # 1X for sidebands
            + 0.15 * np.sin(2 * np.pi * (gmf + shaft_freq) * t)  # upper sb
            + 0.15 * np.sin(2 * np.pi * (gmf - shaft_freq) * t)  # lower sb
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

        # Tier must be 4
        assert result.tier == 4

        # Tier4Analyzer must be in analysis_methods_used
        assert "Tier4Analyzer" in result.analysis_methods_used

        # At least one gear fault detected (fault IDs 16-20)
        gear_fault_ids = _fault_ids(result) & {16, 17, 18, 19, 20}
        assert len(gear_fault_ids) >= 1, (
            f"Expected at least one gear fault (16-20), got {_fault_ids(result)}"
        )


# ---------------------------------------------------------------------------
# Test 3: Mutual exclusion #1 (Unbalance) vs #8 (Air Gap Eccentricity)
# ---------------------------------------------------------------------------


class TestMutualExclusion1vs8:
    """When both Unbalance and Air Gap Eccentricity trigger, only the
    higher-confidence candidate should survive."""

    def test_mutual_exclusion_1_vs_8(self) -> None:
        fs = 4096
        t = np.arange(0, 2.0, 1 / fs)
        rng = np.random.default_rng(42)

        shaft_freq = 18.0  # 1080 RPM (6-pole motor)

        # Strong 1X (triggers unbalance) + strong 2FL + Fp sidebands (triggers air gap)
        # Fp = 6 Hz, so sidebands at 114 and 126 Hz
        signal = (
            2.0 * np.sin(2 * np.pi * shaft_freq * t)  # very strong 1X
            + 1.0 * np.sin(2 * np.pi * 120 * t)  # 2FL
            + 0.5 * np.sin(2 * np.pi * 114 * t)  # Fp sideband
            + 0.5 * np.sin(2 * np.pi * 126 * t)  # Fp sideband
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

        # Both #1 and #8 must NOT be simultaneously present
        assert not (1 in ids and 8 in ids), (
            "Mutual exclusion failed: both fault #1 (Unbalance) and "
            f"#8 (Air Gap Eccentricity) present in {ids}"
        )

        # At least one of them should be present (the signal was designed
        # to trigger both before conflict resolution)
        assert 1 in ids or 8 in ids, (
            f"Expected at least one of #1 or #8 in diagnosed_faults, got {ids}"
        )


# ---------------------------------------------------------------------------
# Test 4: Suggested parameters at different tiers
# ---------------------------------------------------------------------------


class TestPipelineSuggestedParameters:
    """Pipeline should suggest next-tier parameters."""

    def test_tier1_suggests_bearing(self) -> None:
        """At Tier 1 (RPM only), suggested_parameters should mention Tier 2."""
        fs = 4096
        t = np.arange(0, 2.0, 1 / fs)
        rng = np.random.default_rng(42)
        signal = 0.01 * rng.standard_normal(len(t))

        params = MachineParameters(sampling_rate=fs, rpm=1800)
        assert params.tier == 1

        pipeline = DiagnosticPipeline()
        result = pipeline.run(signal, params)

        assert len(result.suggested_parameters) >= 1
        # Should mention bearing geometry or Tier 2
        suggestion = " ".join(result.suggested_parameters).lower()
        assert "bearing" in suggestion or "tier 2" in suggestion, (
            f"Expected bearing/Tier 2 suggestion, got: {result.suggested_parameters}"
        )

    def test_tier3_suggests_gear_teeth(self) -> None:
        """At Tier 3, suggested_parameters should mention gear_teeth for Tier 4."""
        fs = 4096
        t = np.arange(0, 2.0, 1 / fs)
        rng = np.random.default_rng(42)
        signal = 0.01 * rng.standard_normal(len(t))

        params = MachineParameters(
            sampling_rate=fs,
            rpm=1080,
            pole_pairs=3,
            line_frequency=60,
        )
        assert params.tier == 3

        pipeline = DiagnosticPipeline()
        result = pipeline.run(signal, params)

        assert len(result.suggested_parameters) >= 1
        suggestion = " ".join(result.suggested_parameters).lower()
        assert "gear" in suggestion or "tier 4" in suggestion, (
            f"Expected gear/Tier 4 suggestion, got: {result.suggested_parameters}"
        )


# ---------------------------------------------------------------------------
# Test 5: Not-diagnosable at Tier 0
# ---------------------------------------------------------------------------


class TestPipelineNotDiagnosable:
    """At Tier 0 (no RPM), all faults from higher tiers should be listed
    as not diagnosable."""

    def test_pipeline_not_diagnosable(self) -> None:
        fs = 4096
        t = np.arange(0, 2.0, 1 / fs)
        rng = np.random.default_rng(42)
        signal = 0.01 * rng.standard_normal(len(t))

        # Tier 0: only sampling_rate, no RPM
        params = MachineParameters(sampling_rate=fs)
        assert params.tier == 0

        pipeline = DiagnosticPipeline()
        result = pipeline.run(signal, params)

        # Should have no diagnosed faults (Tier0 emits none)
        assert len(result.diagnosed_faults) == 0

        not_diag = result.not_diagnosable

        # Electrical faults (Tier 3) should be listed as not diagnosable
        electrical_names = {
            "Air Gap Eccentricity",
            "Phase Problem",
            "Winding Short",
            "Broken Rotor Bar",
            "End Ring Short",
        }
        for name in electrical_names:
            assert name in not_diag, (
                f"Expected '{name}' in not_diagnosable, got {not_diag}"
            )

        # Gear faults (Tier 4) should be listed as not diagnosable
        gear_names = {
            "Gear Misalignment",
            "Broken Tooth",
            "Gear Eccentricity",
            "Gear Shaft Bend",
            "Gear Wear",
        }
        for name in gear_names:
            assert name in not_diag, (
                f"Expected '{name}' in not_diagnosable, got {not_diag}"
            )


# ---------------------------------------------------------------------------
# Test 6: Merge groups (#10/#13 and #14/#15)
# ---------------------------------------------------------------------------


class TestMergeGroups:
    """Tier 3 analyzer already emits merged candidates for electrical faults.
    Verify the merged_with field is populated correctly."""

    def test_tier3_emits_merged_rotor_bar(self) -> None:
        """Fault #14 (Broken Rotor Bar) should be emitted with merged_with=[15]
        (End Ring Short) by the Tier3Analyzer."""
        from vibfault.analyzers.tier3 import Tier3Analyzer

        fs = 4096
        t = np.arange(0, 2.0, 1 / fs)
        rng = np.random.default_rng(42)

        # Signal with 1X + Fp sidebands around 1X (triggers broken rotor bar)
        # 6-pole motor: rpm=1080 -> shaft_freq=18, Fp=6.0 Hz
        shaft_freq = 18.0
        fp = 6.0
        signal = (
            1.0 * np.sin(2 * np.pi * shaft_freq * t)  # 1X
            + 0.5 * np.sin(2 * np.pi * (shaft_freq - fp) * t)  # lower Fp sideband
            + 0.5 * np.sin(2 * np.pi * (shaft_freq + fp) * t)  # upper Fp sideband
            + 0.01 * rng.standard_normal(len(t))
        )

        params = MachineParameters(
            sampling_rate=fs,
            rpm=1080,
            pole_pairs=3,
            line_frequency=60,
        )

        analyzer = Tier3Analyzer()
        assert analyzer.can_run(params)

        candidates = analyzer.analyze(signal, params)
        rotor_candidates = [c for c in candidates if c.fault_id == 14]

        if rotor_candidates:
            rotor = rotor_candidates[0]
            assert rotor.merged_with is not None, (
                "Fault #14 should have merged_with populated"
            )
            assert 15 in rotor.merged_with, (
                f"Fault #14 merged_with should include 15, got {rotor.merged_with}"
            )
            assert rotor.diagnosis_type == "M", (
                f"Fault #14 diagnosis_type should be 'M' (merged), got '{rotor.diagnosis_type}'"
            )

    def test_tier3_emits_merged_stator(self) -> None:
        """Fault #10 (Phase Problem / Stator Electrical) should be emitted
        with merged_with=[13] (Winding Short) by the Tier3Analyzer."""
        from vibfault.analyzers.tier3 import Tier3Analyzer

        fs = 4096
        t = np.arange(0, 2.0, 1 / fs)
        rng = np.random.default_rng(42)

        # Signal with 2FL peak but NO 1X Fp sidebands (triggers stator, not rotor)
        # 6-pole motor: Fp = 6 Hz — wide enough to avoid false sideband detection
        signal = (
            1.0 * np.sin(2 * np.pi * 120 * t)  # 2FL
            + 0.01 * rng.standard_normal(len(t))
        )

        params = MachineParameters(
            sampling_rate=fs,
            rpm=1080,
            pole_pairs=3,
            line_frequency=60,
        )

        analyzer = Tier3Analyzer()
        assert analyzer.can_run(params)

        candidates = analyzer.analyze(signal, params)
        stator_candidates = [c for c in candidates if c.fault_id == 10]

        if stator_candidates:
            stator = stator_candidates[0]
            assert stator.merged_with is not None, (
                "Fault #10 should have merged_with populated"
            )
            assert 13 in stator.merged_with, (
                f"Fault #10 merged_with should include 13, got {stator.merged_with}"
            )
            assert stator.diagnosis_type == "M", (
                f"Fault #10 diagnosis_type should be 'M' (merged), got '{stator.diagnosis_type}'"
            )

    def test_pipeline_merge_both_members_collapsed(self) -> None:
        """If the pipeline's _enforce_merged_groups receives both members of a
        merge pair, they should be collapsed into a single candidate."""
        from vibfault.analyzers.protocol import FaultCandidate
        from vibfault.core.models import Evidence

        pipeline = DiagnosticPipeline()

        # Manually create both #10 and #13 as separate candidates
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
                ),
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
                ),
            ],
        )

        merged = pipeline._enforce_merged_groups([c10, c13])

        # Should collapse to a single candidate
        merged_ids = {c.fault_id for c in merged}
        assert len(merged) == 1, (
            f"Expected 1 merged candidate, got {len(merged)}: {merged_ids}"
        )

        survivor = merged[0]
        assert survivor.diagnosis_type == "M"
        assert survivor.merged_with is not None
        assert set(survivor.merged_with) == {10, 13}

        # Evidence should be merged (both features present)
        evidence_names = {e.feature_name for e in survivor.evidence}
        assert "2FL_peak_stator" in evidence_names
        assert "winding_indicator" in evidence_names

    def test_pipeline_merge_14_15_collapsed(self) -> None:
        """Both #14 and #15 should collapse into a single merged candidate."""
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
                ),
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
                ),
            ],
        )

        merged = pipeline._enforce_merged_groups([c14, c15])

        merged_ids = {c.fault_id for c in merged}
        assert len(merged) == 1, (
            f"Expected 1 merged candidate, got {len(merged)}: {merged_ids}"
        )

        survivor = merged[0]
        assert survivor.diagnosis_type == "M"
        assert survivor.merged_with is not None
        assert set(survivor.merged_with) == {14, 15}

        evidence_names = {e.feature_name for e in survivor.evidence}
        assert "rotor_bar_indicator" in evidence_names
        assert "end_ring_indicator" in evidence_names
