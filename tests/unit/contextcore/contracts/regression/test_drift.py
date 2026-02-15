"""Tests for contract drift detection (Layer 7 — regression prevention)."""

from __future__ import annotations

import pytest

from contextcore.contracts.propagation.schema import (
    ChainEndpoint,
    ContextContract,
    FieldSpec,
    PhaseContract,
    PhaseEntryContract,
    PhaseExitContract,
    PropagationChainSpec,
)
from contextcore.contracts.regression.drift import (
    ContractDriftDetector,
    DriftChange,
    DriftReport,
)
from contextcore.contracts.types import ConstraintSeverity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_contract(
    pipeline_id: str = "test-pipeline",
    phases: dict[str, PhaseContract] | None = None,
    chains: list[PropagationChainSpec] | None = None,
) -> ContextContract:
    """Build a minimal ``ContextContract`` with optional overrides."""
    return ContextContract(
        schema_version="0.1.0",
        pipeline_id=pipeline_id,
        phases=phases if phases is not None else {},
        propagation_chains=chains or [],
    )


def _field(
    name: str,
    severity: ConstraintSeverity = ConstraintSeverity.BLOCKING,
) -> FieldSpec:
    """Shorthand for creating a ``FieldSpec``."""
    return FieldSpec(name=name, severity=severity)


def _chain(chain_id: str) -> PropagationChainSpec:
    """Shorthand for creating a ``PropagationChainSpec``."""
    return PropagationChainSpec(
        chain_id=chain_id,
        source=ChainEndpoint(phase="src", field="f"),
        destination=ChainEndpoint(phase="dst", field="f"),
    )


# ---------------------------------------------------------------------------
# DriftReport model tests
# ---------------------------------------------------------------------------


class TestDriftReportModel:
    """Tests for the DriftReport Pydantic model and its properties."""

    def test_empty_report_has_no_breaking_changes(self):
        report = DriftReport()
        assert report.has_breaking_changes is False
        assert report.breaking_changes == []
        assert report.non_breaking_changes == []
        assert report.total_changes == 0
        assert report.breaking_count == 0
        assert report.non_breaking_count == 0

    def test_report_properties_filter_correctly(self):
        breaking = DriftChange(
            change_type="phase_removed", phase="x", breaking=True, description="rm"
        )
        non_breaking = DriftChange(
            change_type="phase_added", phase="y", breaking=False, description="add"
        )
        report = DriftReport(
            changes=[breaking, non_breaking],
            total_changes=2,
            breaking_count=1,
            non_breaking_count=1,
        )
        assert report.has_breaking_changes is True
        assert report.breaking_changes == [breaking]
        assert report.non_breaking_changes == [non_breaking]

    def test_report_all_breaking(self):
        changes = [
            DriftChange(change_type="phase_removed", breaking=True, description="a"),
            DriftChange(change_type="chain_removed", breaking=True, description="b"),
        ]
        report = DriftReport(
            changes=changes,
            total_changes=2,
            breaking_count=2,
            non_breaking_count=0,
        )
        assert report.has_breaking_changes is True
        assert len(report.breaking_changes) == 2
        assert len(report.non_breaking_changes) == 0

    def test_report_pipeline_ids(self):
        report = DriftReport(old_pipeline_id="v1", new_pipeline_id="v2")
        assert report.old_pipeline_id == "v1"
        assert report.new_pipeline_id == "v2"


# ---------------------------------------------------------------------------
# Identical contracts
# ---------------------------------------------------------------------------


class TestIdenticalContracts:
    """Comparing identical contracts should produce an empty report."""

    def test_empty_contracts(self):
        old = _make_contract()
        new = _make_contract()
        report = ContractDriftDetector().compare(old, new)
        assert report.total_changes == 0
        assert report.changes == []
        assert report.has_breaking_changes is False

    def test_identical_non_empty_contracts(self):
        phases = {
            "plan": PhaseContract(
                entry=PhaseEntryContract(required=[_field("project_root")]),
                exit=PhaseExitContract(required=[_field("tasks")]),
            ),
        }
        chains = [_chain("task_flow")]
        old = _make_contract(phases=phases, chains=chains)
        new = _make_contract(phases=phases, chains=chains)
        report = ContractDriftDetector().compare(old, new)
        assert report.total_changes == 0


# ---------------------------------------------------------------------------
# Phase changes
# ---------------------------------------------------------------------------


class TestPhaseChanges:
    """Tests for phase addition and removal detection."""

    def test_phase_added_is_non_breaking(self):
        old = _make_contract(phases={})
        new = _make_contract(phases={"plan": PhaseContract()})
        report = ContractDriftDetector().compare(old, new)

        assert report.total_changes == 1
        assert report.breaking_count == 0
        change = report.changes[0]
        assert change.change_type == "phase_added"
        assert change.phase == "plan"
        assert change.breaking is False

    def test_phase_removed_is_breaking(self):
        old = _make_contract(phases={"plan": PhaseContract()})
        new = _make_contract(phases={})
        report = ContractDriftDetector().compare(old, new)

        assert report.total_changes == 1
        assert report.breaking_count == 1
        change = report.changes[0]
        assert change.change_type == "phase_removed"
        assert change.phase == "plan"
        assert change.breaking is True
        assert "downstream" in change.description.lower()

    def test_multiple_phases_added(self):
        old = _make_contract(phases={})
        new = _make_contract(
            phases={"alpha": PhaseContract(), "beta": PhaseContract()}
        )
        report = ContractDriftDetector().compare(old, new)

        assert report.total_changes == 2
        assert report.breaking_count == 0
        types = {c.change_type for c in report.changes}
        assert types == {"phase_added"}
        # Sorted alphabetically
        assert report.changes[0].phase == "alpha"
        assert report.changes[1].phase == "beta"

    def test_multiple_phases_removed(self):
        old = _make_contract(
            phases={"alpha": PhaseContract(), "beta": PhaseContract()}
        )
        new = _make_contract(phases={})
        report = ContractDriftDetector().compare(old, new)

        assert report.total_changes == 2
        assert report.breaking_count == 2

    def test_phase_added_and_removed_simultaneously(self):
        old = _make_contract(phases={"old_phase": PhaseContract()})
        new = _make_contract(phases={"new_phase": PhaseContract()})
        report = ContractDriftDetector().compare(old, new)

        assert report.total_changes == 2
        assert report.breaking_count == 1  # removal is breaking
        assert report.non_breaking_count == 1  # addition is non-breaking
        change_types = {c.change_type for c in report.changes}
        assert change_types == {"phase_added", "phase_removed"}


# ---------------------------------------------------------------------------
# Field changes — entry required
# ---------------------------------------------------------------------------


class TestEntryFieldChanges:
    """Tests for entry required field additions and removals."""

    def test_entry_field_added_blocking_is_breaking(self):
        old = _make_contract(phases={"plan": PhaseContract()})
        new = _make_contract(
            phases={
                "plan": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[_field("project_root", ConstraintSeverity.BLOCKING)]
                    )
                )
            }
        )
        report = ContractDriftDetector().compare(old, new)

        assert report.total_changes == 1
        assert report.breaking_count == 1
        change = report.changes[0]
        assert change.change_type == "field_added"
        assert change.phase == "plan"
        assert change.field == "project_root"
        assert change.direction == "entry"
        assert change.breaking is True
        assert change.new_value == "blocking"
        assert "BLOCKING" in change.description

    def test_entry_field_added_warning_is_non_breaking(self):
        old = _make_contract(phases={"plan": PhaseContract()})
        new = _make_contract(
            phases={
                "plan": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[_field("hint", ConstraintSeverity.WARNING)]
                    )
                )
            }
        )
        report = ContractDriftDetector().compare(old, new)

        assert report.total_changes == 1
        assert report.breaking_count == 0
        assert report.changes[0].breaking is False

    def test_entry_field_added_advisory_is_non_breaking(self):
        old = _make_contract(phases={"plan": PhaseContract()})
        new = _make_contract(
            phases={
                "plan": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[_field("note", ConstraintSeverity.ADVISORY)]
                    )
                )
            }
        )
        report = ContractDriftDetector().compare(old, new)

        assert report.breaking_count == 0

    def test_entry_field_removed_is_non_breaking(self):
        old = _make_contract(
            phases={
                "plan": PhaseContract(
                    entry=PhaseEntryContract(required=[_field("obsolete")])
                )
            }
        )
        new = _make_contract(phases={"plan": PhaseContract()})
        report = ContractDriftDetector().compare(old, new)

        assert report.total_changes == 1
        change = report.changes[0]
        assert change.change_type == "field_removed"
        assert change.direction == "entry"
        assert change.breaking is False  # entry removal is non-breaking


# ---------------------------------------------------------------------------
# Field changes — enrichment
# ---------------------------------------------------------------------------


class TestEnrichmentFieldChanges:
    """Tests for entry enrichment field additions and removals."""

    def test_enrichment_field_added_blocking_is_breaking(self):
        old = _make_contract(phases={"plan": PhaseContract()})
        new = _make_contract(
            phases={
                "plan": PhaseContract(
                    entry=PhaseEntryContract(
                        enrichment=[
                            _field("domain", ConstraintSeverity.BLOCKING)
                        ]
                    )
                )
            }
        )
        report = ContractDriftDetector().compare(old, new)

        assert report.total_changes == 1
        assert report.breaking_count == 1
        change = report.changes[0]
        assert change.change_type == "field_added"
        assert change.direction == "enrichment"
        assert change.breaking is True

    def test_enrichment_field_added_warning_is_non_breaking(self):
        old = _make_contract(phases={"plan": PhaseContract()})
        new = _make_contract(
            phases={
                "plan": PhaseContract(
                    entry=PhaseEntryContract(
                        enrichment=[
                            _field("domain", ConstraintSeverity.WARNING)
                        ]
                    )
                )
            }
        )
        report = ContractDriftDetector().compare(old, new)

        assert report.total_changes == 1
        assert report.breaking_count == 0


# ---------------------------------------------------------------------------
# Field changes — exit
# ---------------------------------------------------------------------------


class TestExitFieldChanges:
    """Tests for exit required and exit optional field changes."""

    def test_exit_required_field_removed_is_breaking(self):
        old = _make_contract(
            phases={
                "plan": PhaseContract(
                    exit=PhaseExitContract(required=[_field("tasks")])
                )
            }
        )
        new = _make_contract(phases={"plan": PhaseContract()})
        report = ContractDriftDetector().compare(old, new)

        assert report.total_changes == 1
        assert report.breaking_count == 1
        change = report.changes[0]
        assert change.change_type == "field_removed"
        assert change.direction == "exit"
        assert change.breaking is True
        assert "downstream" in change.description.lower()
        assert change.old_value == "blocking"

    def test_exit_optional_field_removed_is_breaking(self):
        old = _make_contract(
            phases={
                "plan": PhaseContract(
                    exit=PhaseExitContract(optional=[_field("summary")])
                )
            }
        )
        new = _make_contract(phases={"plan": PhaseContract()})
        report = ContractDriftDetector().compare(old, new)

        assert report.total_changes == 1
        assert report.breaking_count == 1
        change = report.changes[0]
        assert change.change_type == "field_removed"
        assert change.direction == "exit_optional"
        assert change.breaking is True

    def test_exit_required_field_added_is_non_breaking(self):
        """Adding a new exit field is non-breaking (exit direction, not entry)."""
        old = _make_contract(phases={"plan": PhaseContract()})
        new = _make_contract(
            phases={
                "plan": PhaseContract(
                    exit=PhaseExitContract(required=[_field("tasks")])
                )
            }
        )
        report = ContractDriftDetector().compare(old, new)

        assert report.total_changes == 1
        # Exit field added — not entry/enrichment direction, so not breaking
        # regardless of severity
        assert report.breaking_count == 0


# ---------------------------------------------------------------------------
# Severity changes
# ---------------------------------------------------------------------------


class TestSeverityChanges:
    """Tests for field severity escalation and de-escalation."""

    def test_severity_warning_to_blocking_is_breaking(self):
        old = _make_contract(
            phases={
                "plan": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[_field("tasks", ConstraintSeverity.WARNING)]
                    )
                )
            }
        )
        new = _make_contract(
            phases={
                "plan": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[_field("tasks", ConstraintSeverity.BLOCKING)]
                    )
                )
            }
        )
        report = ContractDriftDetector().compare(old, new)

        assert report.total_changes == 1
        assert report.breaking_count == 1
        change = report.changes[0]
        assert change.change_type == "severity_changed"
        assert change.phase == "plan"
        assert change.field == "tasks"
        assert change.old_value == "warning"
        assert change.new_value == "blocking"
        assert change.breaking is True
        assert "ESCALATED" in change.description

    def test_severity_blocking_to_warning_is_non_breaking(self):
        old = _make_contract(
            phases={
                "plan": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[_field("tasks", ConstraintSeverity.BLOCKING)]
                    )
                )
            }
        )
        new = _make_contract(
            phases={
                "plan": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[_field("tasks", ConstraintSeverity.WARNING)]
                    )
                )
            }
        )
        report = ContractDriftDetector().compare(old, new)

        assert report.total_changes == 1
        assert report.breaking_count == 0
        change = report.changes[0]
        assert change.change_type == "severity_changed"
        assert change.old_value == "blocking"
        assert change.new_value == "warning"
        assert change.breaking is False

    def test_severity_advisory_to_blocking_is_breaking(self):
        old = _make_contract(
            phases={
                "plan": PhaseContract(
                    exit=PhaseExitContract(
                        required=[_field("output", ConstraintSeverity.ADVISORY)]
                    )
                )
            }
        )
        new = _make_contract(
            phases={
                "plan": PhaseContract(
                    exit=PhaseExitContract(
                        required=[_field("output", ConstraintSeverity.BLOCKING)]
                    )
                )
            }
        )
        report = ContractDriftDetector().compare(old, new)

        assert report.total_changes == 1
        assert report.breaking_count == 1
        assert report.changes[0].breaking is True

    def test_severity_advisory_to_warning_is_non_breaking(self):
        old = _make_contract(
            phases={
                "plan": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[_field("hint", ConstraintSeverity.ADVISORY)]
                    )
                )
            }
        )
        new = _make_contract(
            phases={
                "plan": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[_field("hint", ConstraintSeverity.WARNING)]
                    )
                )
            }
        )
        report = ContractDriftDetector().compare(old, new)

        assert report.total_changes == 1
        assert report.breaking_count == 0
        assert report.changes[0].breaking is False


# ---------------------------------------------------------------------------
# Chain changes
# ---------------------------------------------------------------------------


class TestChainChanges:
    """Tests for propagation chain additions and removals."""

    def test_chain_added_is_non_breaking(self):
        old = _make_contract()
        new = _make_contract(chains=[_chain("task_flow")])
        report = ContractDriftDetector().compare(old, new)

        assert report.total_changes == 1
        assert report.breaking_count == 0
        change = report.changes[0]
        assert change.change_type == "chain_added"
        assert change.field == "task_flow"
        assert change.direction == "chain"
        assert change.breaking is False

    def test_chain_removed_is_breaking(self):
        old = _make_contract(chains=[_chain("task_flow")])
        new = _make_contract()
        report = ContractDriftDetector().compare(old, new)

        assert report.total_changes == 1
        assert report.breaking_count == 1
        change = report.changes[0]
        assert change.change_type == "chain_removed"
        assert change.field == "task_flow"
        assert change.direction == "chain"
        assert change.breaking is True
        assert "verification lost" in change.description.lower()

    def test_multiple_chains_added_and_removed(self):
        old = _make_contract(chains=[_chain("old_chain")])
        new = _make_contract(chains=[_chain("new_chain_a"), _chain("new_chain_b")])
        report = ContractDriftDetector().compare(old, new)

        assert report.total_changes == 3  # 1 removed + 2 added
        assert report.breaking_count == 1
        assert report.non_breaking_count == 2


# ---------------------------------------------------------------------------
# Mixed changes (integration tests)
# ---------------------------------------------------------------------------


class TestMixedChanges:
    """Tests combining multiple kinds of drift in a single comparison."""

    def test_phases_fields_and_chains_all_changed(self):
        old = _make_contract(
            phases={
                "plan": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[_field("project_root", ConstraintSeverity.WARNING)]
                    ),
                    exit=PhaseExitContract(
                        required=[_field("tasks")]
                    ),
                ),
                "review": PhaseContract(),
            },
            chains=[_chain("task_flow")],
        )
        new = _make_contract(
            phases={
                "plan": PhaseContract(
                    entry=PhaseEntryContract(
                        required=[_field("project_root", ConstraintSeverity.BLOCKING)]
                    ),
                    # exit "tasks" field removed
                ),
                # "review" removed, "deploy" added
                "deploy": PhaseContract(),
            },
            chains=[_chain("deploy_flow")],
        )
        report = ContractDriftDetector().compare(old, new)

        change_types = [c.change_type for c in report.changes]

        # Phase changes: review removed (breaking), deploy added (non-breaking)
        assert "phase_added" in change_types
        assert "phase_removed" in change_types

        # Field changes on "plan": severity escalation (breaking), exit removed (breaking)
        assert "severity_changed" in change_types
        assert "field_removed" in change_types

        # Chain changes: task_flow removed (breaking), deploy_flow added (non-breaking)
        assert "chain_added" in change_types
        assert "chain_removed" in change_types

        # At minimum: review removed, severity escalated, tasks exit removed,
        #             task_flow chain removed => 4 breaking
        assert report.breaking_count >= 4
        assert report.has_breaking_changes is True

    def test_report_counts_are_consistent(self):
        """total_changes == breaking_count + non_breaking_count always."""
        old = _make_contract(
            phases={"a": PhaseContract(), "b": PhaseContract()},
            chains=[_chain("c1")],
        )
        new = _make_contract(
            phases={"b": PhaseContract(), "c": PhaseContract()},
            chains=[_chain("c2")],
        )
        report = ContractDriftDetector().compare(old, new)

        assert report.total_changes == report.breaking_count + report.non_breaking_count
        assert report.total_changes == len(report.changes)
        assert report.breaking_count == len(report.breaking_changes)
        assert report.non_breaking_count == len(report.non_breaking_changes)

    def test_pipeline_ids_captured_in_report(self):
        old = _make_contract(pipeline_id="pipeline-v1")
        new = _make_contract(pipeline_id="pipeline-v2")
        report = ContractDriftDetector().compare(old, new)

        assert report.old_pipeline_id == "pipeline-v1"
        assert report.new_pipeline_id == "pipeline-v2"
