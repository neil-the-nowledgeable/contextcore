"""Tests for pre-flight checker (Layer 3)."""

import pytest

from contextcore.contracts.preflight.checker import (
    PreflightChecker,
    PreflightResult,
    PreflightViolation,
)
from contextcore.contracts.propagation.schema import (
    ContextContract,
    FieldSpec,
    PhaseContract,
    PhaseEntryContract,
    PhaseExitContract,
)
from contextcore.contracts.types import ConstraintSeverity


@pytest.fixture
def checker():
    return PreflightChecker()


def _make_contract(phases, chains=None):
    """Create a minimal contract with the given phases dict."""
    return ContextContract(
        schema_version="0.1.0",
        pipeline_id="test",
        phases=phases,
        propagation_chains=chains or [],
    )


# ---------------------------------------------------------------------------
# Field readiness
# ---------------------------------------------------------------------------


class TestFieldReadiness:
    def test_all_fields_ready(self, checker):
        """All required fields present with real values -> passed."""
        contract = _make_contract(
            phases={
                "phase_a": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[
                            FieldSpec(name="project_id", severity=ConstraintSeverity.BLOCKING),
                            FieldSpec(name="tasks", severity=ConstraintSeverity.BLOCKING),
                        ],
                    ),
                ),
            },
        )
        context = {"project_id": "proj-1", "tasks": "task-1,task-2"}
        result = checker.check_field_readiness(contract, context, ["phase_a"])
        assert result.passed is True
        assert result.critical_violations == []
        assert result.fields_checked == 2

    def test_missing_blocking_field(self, checker):
        """Missing blocking field -> passed=False, critical_violations non-empty."""
        contract = _make_contract(
            phases={
                "phase_a": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[
                            FieldSpec(name="project_id", severity=ConstraintSeverity.BLOCKING),
                        ],
                    ),
                ),
            },
        )
        context = {}
        result = checker.check_field_readiness(contract, context, ["phase_a"])
        assert result.passed is False
        assert len(result.critical_violations) == 1
        assert result.critical_violations[0].field == "project_id"
        assert result.critical_violations[0].check_type == "field_readiness"

    def test_missing_warning_field(self, checker):
        """Missing warning field -> passed=True, warnings non-empty."""
        contract = _make_contract(
            phases={
                "phase_a": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[
                            FieldSpec(name="hint", severity=ConstraintSeverity.WARNING),
                        ],
                    ),
                ),
            },
        )
        context = {}
        result = checker.check_field_readiness(contract, context, ["phase_a"])
        assert result.passed is True
        assert len(result.warnings) == 1
        assert result.warnings[0].field == "hint"

    def test_field_with_none_not_ready(self, checker):
        """Field with None value is not ready."""
        contract = _make_contract(
            phases={
                "phase_a": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[
                            FieldSpec(name="f_none", severity=ConstraintSeverity.BLOCKING),
                        ],
                    ),
                ),
            },
        )
        context = {"f_none": None}
        result = checker.check_field_readiness(contract, context, ["phase_a"])
        assert result.passed is False
        assert len(result.critical_violations) == 1
        assert result.critical_violations[0].field == "f_none"

    def test_field_with_default_sentinel_values_not_ready(self, checker):
        """Fields holding default sentinel values ('', 'unknown', 'UNKNOWN') are not ready."""
        contract = _make_contract(
            phases={
                "phase_a": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[
                            FieldSpec(name="f_empty_str", severity=ConstraintSeverity.BLOCKING),
                            FieldSpec(name="f_unknown", severity=ConstraintSeverity.BLOCKING),
                            FieldSpec(name="f_upper_unknown", severity=ConstraintSeverity.BLOCKING),
                        ],
                    ),
                ),
            },
        )
        context = {
            "f_empty_str": "",
            "f_unknown": "unknown",
            "f_upper_unknown": "UNKNOWN",
        }
        result = checker.check_field_readiness(contract, context, ["phase_a"])
        assert result.passed is False
        assert len(result.critical_violations) == 3
        flagged_fields = {v.field for v in result.critical_violations}
        assert flagged_fields == {"f_empty_str", "f_unknown", "f_upper_unknown"}

    def test_field_produced_by_earlier_phase(self, checker):
        """A field required by phase B but produced by phase A is ready."""
        contract = _make_contract(
            phases={
                "phase_a": PhaseContract(
                    exit=PhaseExitContract(
                        required=[FieldSpec(name="intermediate_result")],
                    ),
                ),
                "phase_b": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[
                            FieldSpec(name="intermediate_result", severity=ConstraintSeverity.BLOCKING),
                        ],
                    ),
                ),
            },
        )
        # intermediate_result is NOT in the initial context, but phase_a produces it
        context = {}
        result = checker.check_field_readiness(contract, context, ["phase_a", "phase_b"])
        assert result.passed is True
        assert result.critical_violations == []

    def test_dot_path_field_resolution(self, checker):
        """Nested dict fields accessed via dot-path notation are resolved."""
        contract = _make_contract(
            phases={
                "phase_a": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[
                            FieldSpec(name="config.db.host", severity=ConstraintSeverity.BLOCKING),
                        ],
                    ),
                ),
            },
        )
        context = {"config": {"db": {"host": "localhost"}}}
        result = checker.check_field_readiness(contract, context, ["phase_a"])
        assert result.passed is True
        assert result.critical_violations == []

    def test_empty_contract_passes(self, checker):
        """Contract with no phases -> passed=True."""
        contract = _make_contract(phases={})
        result = checker.check_field_readiness(contract, {}, [])
        assert result.passed is True
        assert result.fields_checked == 0
        assert result.violations == []

    def test_multiple_phases_cascading_requires(self, checker):
        """Phase C requires a field produced by phase B, which requires a field from context."""
        contract = _make_contract(
            phases={
                "phase_a": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[
                            FieldSpec(name="seed", severity=ConstraintSeverity.BLOCKING),
                        ],
                    ),
                    exit=PhaseExitContract(
                        required=[FieldSpec(name="result_a")],
                    ),
                ),
                "phase_b": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[
                            FieldSpec(name="result_a", severity=ConstraintSeverity.BLOCKING),
                        ],
                    ),
                    exit=PhaseExitContract(
                        required=[FieldSpec(name="result_b")],
                    ),
                ),
                "phase_c": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[
                            FieldSpec(name="result_b", severity=ConstraintSeverity.BLOCKING),
                        ],
                    ),
                ),
            },
        )
        context = {"seed": "hello"}
        result = checker.check_field_readiness(
            contract, context, ["phase_a", "phase_b", "phase_c"]
        )
        assert result.passed is True
        assert result.critical_violations == []


# ---------------------------------------------------------------------------
# Seed enrichment
# ---------------------------------------------------------------------------


class TestSeedEnrichment:
    def test_enrichment_field_present_with_real_value(self, checker):
        """Enrichment field present with a real value -> no violation."""
        contract = _make_contract(
            phases={
                "phase_a": PhaseContract(
                    entry=PhaseEntryContract(
                        enrichment=[
                            FieldSpec(
                                name="domain",
                                severity=ConstraintSeverity.WARNING,
                                default="unknown",
                            ),
                        ],
                    ),
                ),
            },
        )
        context = {"domain": "web_application"}
        result = checker.check(contract, context, ["phase_a"])
        enrichment_violations = [
            v for v in result.violations if v.check_type == "seed_enrichment"
        ]
        assert len(enrichment_violations) == 0

    def test_enrichment_field_missing(self, checker):
        """Missing enrichment field -> violation with correct severity."""
        contract = _make_contract(
            phases={
                "phase_a": PhaseContract(
                    entry=PhaseEntryContract(
                        enrichment=[
                            FieldSpec(
                                name="domain",
                                severity=ConstraintSeverity.WARNING,
                                default="unknown",
                            ),
                        ],
                    ),
                ),
            },
        )
        context = {}
        result = checker.check(contract, context, ["phase_a"])
        enrichment_violations = [
            v for v in result.violations if v.check_type == "seed_enrichment"
        ]
        assert len(enrichment_violations) == 1
        assert enrichment_violations[0].severity == ConstraintSeverity.WARNING
        assert enrichment_violations[0].field == "domain"

    def test_enrichment_field_with_default_value(self, checker):
        """Enrichment field present but with default sentinel value -> violation."""
        contract = _make_contract(
            phases={
                "phase_a": PhaseContract(
                    entry=PhaseEntryContract(
                        enrichment=[
                            FieldSpec(
                                name="domain",
                                severity=ConstraintSeverity.WARNING,
                                default="unknown",
                            ),
                        ],
                    ),
                ),
            },
        )
        # "unknown" is in the default sentinels list
        context = {"domain": "unknown"}
        result = checker.check(contract, context, ["phase_a"])
        enrichment_violations = [
            v for v in result.violations if v.check_type == "seed_enrichment"
        ]
        assert len(enrichment_violations) == 1
        assert enrichment_violations[0].field == "domain"

    def test_advisory_enrichment_field_missing_no_violation(self, checker):
        """Advisory enrichment field missing -> no violation (advisory ignored)."""
        contract = _make_contract(
            phases={
                "phase_a": PhaseContract(
                    entry=PhaseEntryContract(
                        enrichment=[
                            FieldSpec(
                                name="calibration",
                                severity=ConstraintSeverity.ADVISORY,
                            ),
                        ],
                    ),
                ),
            },
        )
        context = {}
        result = checker.check(contract, context, ["phase_a"])
        enrichment_violations = [
            v for v in result.violations if v.check_type == "seed_enrichment"
        ]
        assert len(enrichment_violations) == 0

    def test_multiple_enrichment_fields_some_missing(self, checker):
        """Multiple enrichment fields: violations only for missing non-advisory fields."""
        contract = _make_contract(
            phases={
                "phase_a": PhaseContract(
                    entry=PhaseEntryContract(
                        enrichment=[
                            FieldSpec(name="domain", severity=ConstraintSeverity.WARNING),
                            FieldSpec(name="author", severity=ConstraintSeverity.WARNING),
                            FieldSpec(name="extra", severity=ConstraintSeverity.ADVISORY),
                        ],
                    ),
                ),
            },
        )
        # Only "domain" provided; "author" missing (WARNING), "extra" missing (ADVISORY)
        context = {"domain": "finance"}
        result = checker.check(contract, context, ["phase_a"])
        enrichment_violations = [
            v for v in result.violations if v.check_type == "seed_enrichment"
        ]
        # Only "author" should produce a violation; "extra" is advisory and skipped
        assert len(enrichment_violations) == 1
        assert enrichment_violations[0].field == "author"


# ---------------------------------------------------------------------------
# Phase graph
# ---------------------------------------------------------------------------


class TestPhaseGraph:
    def test_clean_graph(self, checker):
        """All requires have producers -> no graph issues."""
        contract = _make_contract(
            phases={
                "phase_a": PhaseContract(
                    exit=PhaseExitContract(
                        required=[FieldSpec(name="result_a")],
                    ),
                ),
                "phase_b": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[
                            FieldSpec(name="result_a", severity=ConstraintSeverity.BLOCKING),
                        ],
                    ),
                    exit=PhaseExitContract(
                        required=[FieldSpec(name="result_b")],
                    ),
                ),
                "phase_c": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[
                            FieldSpec(name="result_b", severity=ConstraintSeverity.BLOCKING),
                        ],
                    ),
                ),
            },
        )
        result = checker.check_phase_graph(
            contract, {}, ["phase_a", "phase_b", "phase_c"]
        )
        dangling = [i for i in result.phase_graph_issues if i.issue_type == "dangling_read"]
        assert len(dangling) == 0

    def test_dangling_read(self, checker):
        """Required field with no producer and not in initial context -> dangling read."""
        contract = _make_contract(
            phases={
                "phase_a": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[
                            FieldSpec(name="missing_field", severity=ConstraintSeverity.WARNING),
                        ],
                    ),
                ),
            },
        )
        result = checker.check_phase_graph(contract, {}, ["phase_a"])
        dangling = [i for i in result.phase_graph_issues if i.issue_type == "dangling_read"]
        assert len(dangling) == 1
        assert dangling[0].field == "missing_field"
        assert dangling[0].phase == "phase_a"

    def test_dangling_read_with_field_in_initial_context(self, checker):
        """Required field in initial context -> no dangling read."""
        contract = _make_contract(
            phases={
                "phase_a": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[
                            FieldSpec(name="seed", severity=ConstraintSeverity.BLOCKING),
                        ],
                    ),
                ),
            },
        )
        context = {"seed": "value"}
        result = checker.check_phase_graph(contract, context, ["phase_a"])
        dangling = [i for i in result.phase_graph_issues if i.issue_type == "dangling_read"]
        assert len(dangling) == 0

    def test_dead_write(self, checker):
        """Produced field never required by any phase -> dead write advisory."""
        contract = _make_contract(
            phases={
                "phase_a": PhaseContract(
                    exit=PhaseExitContract(
                        required=[FieldSpec(name="orphan_field")],
                    ),
                ),
            },
        )
        result = checker.check_phase_graph(contract, {}, ["phase_a"])
        dead_writes = [i for i in result.phase_graph_issues if i.issue_type == "dead_write"]
        assert len(dead_writes) == 1
        assert dead_writes[0].field == "orphan_field"
        assert dead_writes[0].phase == "phase_a"
        # Dead writes should be advisory-level violations
        advisory_violations = [
            v for v in result.violations
            if v.check_type == "phase_graph" and v.field == "orphan_field"
        ]
        assert advisory_violations[0].severity == ConstraintSeverity.ADVISORY

    def test_multiple_dangling_reads_across_phases(self, checker):
        """Multiple phases each requiring fields that nobody produces."""
        contract = _make_contract(
            phases={
                "phase_a": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[
                            FieldSpec(name="missing_1", severity=ConstraintSeverity.WARNING),
                        ],
                    ),
                ),
                "phase_b": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[
                            FieldSpec(name="missing_2", severity=ConstraintSeverity.WARNING),
                        ],
                    ),
                ),
            },
        )
        result = checker.check_phase_graph(contract, {}, ["phase_a", "phase_b"])
        dangling = [i for i in result.phase_graph_issues if i.issue_type == "dangling_read"]
        assert len(dangling) == 2
        dangling_fields = {i.field for i in dangling}
        assert dangling_fields == {"missing_1", "missing_2"}

    def test_phase_not_in_contract_skipped(self, checker):
        """Phase in phase_order but not in contract phases -> skipped gracefully."""
        contract = _make_contract(
            phases={
                "phase_a": PhaseContract(
                    exit=PhaseExitContract(
                        required=[FieldSpec(name="result_a")],
                    ),
                ),
            },
        )
        # "nonexistent" is not in contract.phases
        result = checker.check_phase_graph(
            contract, {}, ["nonexistent", "phase_a"]
        )
        assert result.passed is True

    def test_blocking_dangling_read_fails(self, checker):
        """Dangling read with BLOCKING severity -> passed=False."""
        contract = _make_contract(
            phases={
                "phase_a": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[
                            FieldSpec(name="critical_field", severity=ConstraintSeverity.BLOCKING),
                        ],
                    ),
                ),
            },
        )
        result = checker.check_phase_graph(contract, {}, ["phase_a"])
        assert result.passed is False
        assert len(result.critical_violations) == 1
        assert result.critical_violations[0].field == "critical_field"

    def test_warning_dangling_read_passes(self, checker):
        """Dangling read with WARNING severity -> passed=True."""
        contract = _make_contract(
            phases={
                "phase_a": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[
                            FieldSpec(name="optional_field", severity=ConstraintSeverity.WARNING),
                        ],
                    ),
                ),
            },
        )
        result = checker.check_phase_graph(contract, {}, ["phase_a"])
        assert result.passed is True
        assert len(result.warnings) >= 1


# ---------------------------------------------------------------------------
# Integrated check()
# ---------------------------------------------------------------------------


class TestCheckIntegrated:
    def test_check_runs_all_three_checks(self, checker):
        """check() aggregates field readiness, seed enrichment, and phase graph."""
        contract = _make_contract(
            phases={
                "phase_a": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[
                            FieldSpec(name="seed", severity=ConstraintSeverity.BLOCKING),
                        ],
                        enrichment=[
                            FieldSpec(name="domain", severity=ConstraintSeverity.WARNING),
                        ],
                    ),
                    exit=PhaseExitContract(
                        required=[FieldSpec(name="orphan")],
                    ),
                ),
            },
        )
        context = {"seed": "real_value"}
        result = checker.check(contract, context, ["phase_a"])

        # Field readiness: seed is present -> no readiness violations
        readiness_violations = [
            v for v in result.violations if v.check_type == "field_readiness"
        ]
        assert len(readiness_violations) == 0

        # Seed enrichment: domain missing -> 1 warning
        enrichment_violations = [
            v for v in result.violations if v.check_type == "seed_enrichment"
        ]
        assert len(enrichment_violations) == 1
        assert enrichment_violations[0].field == "domain"

        # Phase graph: orphan is a dead write -> 1 advisory
        graph_violations = [
            v for v in result.violations if v.check_type == "phase_graph"
        ]
        assert len(graph_violations) == 1
        assert graph_violations[0].severity == ConstraintSeverity.ADVISORY

        # Overall: no blocking violations, so passed
        assert result.passed is True

    def test_check_defaults_phase_order_to_contract_keys(self, checker):
        """check() with no phase_order defaults to contract.phases.keys()."""
        contract = _make_contract(
            phases={
                "alpha": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[
                            FieldSpec(name="seed", severity=ConstraintSeverity.BLOCKING),
                        ],
                    ),
                ),
                "beta": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[
                            FieldSpec(name="other", severity=ConstraintSeverity.BLOCKING),
                        ],
                    ),
                ),
            },
        )
        context = {"seed": "ok", "other": "ok"}
        # phase_order not provided -> should use keys: ["alpha", "beta"]
        result = checker.check(contract, context)
        assert result.passed is True
        assert result.phases_checked == 2

    def test_passed_result_counts(self, checker):
        """Passed result reports correct phases_checked and fields_checked."""
        contract = _make_contract(
            phases={
                "p1": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[
                            FieldSpec(name="a", severity=ConstraintSeverity.BLOCKING),
                        ],
                    ),
                ),
                "p2": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[
                            FieldSpec(name="b", severity=ConstraintSeverity.BLOCKING),
                            FieldSpec(name="c", severity=ConstraintSeverity.BLOCKING),
                        ],
                    ),
                ),
            },
        )
        context = {"a": "val", "b": "val", "c": "val"}
        result = checker.check(contract, context, ["p1", "p2"])
        assert result.passed is True
        assert result.phases_checked == 2
        # fields_checked includes field_readiness details + seed enrichment details
        # 3 from readiness, 0 from enrichment = 3
        assert result.fields_checked >= 3

    def test_failed_result_violation_breakdown(self, checker):
        """Failed result correctly categorises critical, warning, and advisory violations."""
        contract = _make_contract(
            phases={
                "phase_a": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[
                            FieldSpec(name="blocker", severity=ConstraintSeverity.BLOCKING),
                            FieldSpec(name="warn_field", severity=ConstraintSeverity.WARNING),
                        ],
                        enrichment=[
                            FieldSpec(name="enrich", severity=ConstraintSeverity.WARNING),
                        ],
                    ),
                    exit=PhaseExitContract(
                        required=[FieldSpec(name="dead_field")],
                    ),
                ),
            },
        )
        context = {}
        result = checker.check(contract, context, ["phase_a"])
        assert result.passed is False

        # At least 1 blocking (from field_readiness for "blocker" and/or phase_graph)
        assert len(result.critical_violations) >= 1
        # At least 1 warning (from "warn_field" and/or "enrich")
        assert len(result.warnings) >= 1
        # At least 1 advisory (dead_field is a dead write)
        assert len(result.advisories) >= 1

        # Verify we can find specific violations by check_type
        check_types = {v.check_type for v in result.violations}
        assert "field_readiness" in check_types
        assert "phase_graph" in check_types
