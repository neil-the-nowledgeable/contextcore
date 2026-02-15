"""
Contract drift detection for regression prevention — Layer 7.

Compares two versions of a ``ContextContract`` to detect changes that
could break propagation.  Detects:

- **Added phases** — new phases that may introduce requirements.
- **Removed phases** — phases that were producing fields for others.
- **Added fields** — new entry/exit requirements on existing phases.
- **Removed fields** — fields that were required or produced are gone.
- **Severity changes** — a field's severity changed (e.g. WARNING→BLOCKING).
- **Added/removed chains** — propagation chain declarations changed.

Usage::

    from contextcore.contracts.regression import ContractDriftDetector

    detector = ContractDriftDetector()
    report = detector.compare(old_contract, new_contract)
    if report.has_breaking_changes:
        for change in report.breaking_changes:
            logger.error("Breaking: %s", change.description)
"""

from __future__ import annotations

import logging
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from contextcore.contracts.propagation.schema import ContextContract

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class DriftChange(BaseModel):
    """A single detected change between two contract versions."""

    model_config = ConfigDict(extra="forbid")

    change_type: str = Field(
        ...,
        description=(
            "phase_added | phase_removed | field_added | field_removed | "
            "severity_changed | chain_added | chain_removed"
        ),
    )
    phase: str = ""
    field: str = ""
    direction: str = Field(
        default="", description="entry | exit | enrichment | chain"
    )
    breaking: bool = False
    description: str = ""
    old_value: Optional[str] = None
    new_value: Optional[str] = None


class DriftReport(BaseModel):
    """Aggregated drift detection report."""

    model_config = ConfigDict(extra="forbid")

    changes: list[DriftChange] = Field(default_factory=list)
    total_changes: int = 0
    breaking_count: int = 0
    non_breaking_count: int = 0
    old_pipeline_id: str = ""
    new_pipeline_id: str = ""

    @property
    def has_breaking_changes(self) -> bool:
        return self.breaking_count > 0

    @property
    def breaking_changes(self) -> list[DriftChange]:
        return [c for c in self.changes if c.breaking]

    @property
    def non_breaking_changes(self) -> list[DriftChange]:
        return [c for c in self.changes if not c.breaking]


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------


class ContractDriftDetector:
    """Compares two contract versions to detect propagation-breaking drift."""

    def compare(
        self,
        old: ContextContract,
        new: ContextContract,
    ) -> DriftReport:
        """Compare two contract versions and report all changes.

        Args:
            old: The baseline contract version.
            new: The updated contract version.

        Returns:
            ``DriftReport`` with all detected changes.
        """
        changes: list[DriftChange] = []

        changes.extend(self._detect_phase_changes(old, new))
        changes.extend(self._detect_field_changes(old, new))
        changes.extend(self._detect_chain_changes(old, new))

        breaking = sum(1 for c in changes if c.breaking)

        if breaking > 0:
            logger.warning(
                "Contract drift: %d changes (%d breaking) between '%s' and '%s'",
                len(changes),
                breaking,
                old.pipeline_id,
                new.pipeline_id,
            )
        elif changes:
            logger.info(
                "Contract drift: %d non-breaking changes between '%s' and '%s'",
                len(changes),
                old.pipeline_id,
                new.pipeline_id,
            )

        return DriftReport(
            changes=changes,
            total_changes=len(changes),
            breaking_count=breaking,
            non_breaking_count=len(changes) - breaking,
            old_pipeline_id=old.pipeline_id,
            new_pipeline_id=new.pipeline_id,
        )

    # -- internal: phase changes ---------------------------------------------

    def _detect_phase_changes(
        self,
        old: ContextContract,
        new: ContextContract,
    ) -> list[DriftChange]:
        changes: list[DriftChange] = []

        old_phases = set(old.phases.keys())
        new_phases = set(new.phases.keys())

        for phase in sorted(new_phases - old_phases):
            changes.append(
                DriftChange(
                    change_type="phase_added",
                    phase=phase,
                    breaking=False,
                    description=f"Phase '{phase}' added",
                )
            )

        for phase in sorted(old_phases - new_phases):
            changes.append(
                DriftChange(
                    change_type="phase_removed",
                    phase=phase,
                    breaking=True,
                    description=(
                        f"Phase '{phase}' removed — may break "
                        f"downstream dependencies"
                    ),
                )
            )

        return changes

    # -- internal: field changes ---------------------------------------------

    def _detect_field_changes(
        self,
        old: ContextContract,
        new: ContextContract,
    ) -> list[DriftChange]:
        changes: list[DriftChange] = []

        common_phases = set(old.phases.keys()) & set(new.phases.keys())

        for phase_name in sorted(common_phases):
            old_phase = old.phases[phase_name]
            new_phase = new.phases[phase_name]

            # Entry required
            changes.extend(
                self._compare_field_lists(
                    phase_name,
                    "entry",
                    {f.name: f for f in old_phase.entry.required},
                    {f.name: f for f in new_phase.entry.required},
                )
            )

            # Entry enrichment
            changes.extend(
                self._compare_field_lists(
                    phase_name,
                    "enrichment",
                    {f.name: f for f in old_phase.entry.enrichment},
                    {f.name: f for f in new_phase.entry.enrichment},
                )
            )

            # Exit required
            changes.extend(
                self._compare_field_lists(
                    phase_name,
                    "exit",
                    {f.name: f for f in old_phase.exit.required},
                    {f.name: f for f in new_phase.exit.required},
                )
            )

            # Exit optional
            changes.extend(
                self._compare_field_lists(
                    phase_name,
                    "exit_optional",
                    {f.name: f for f in old_phase.exit.optional},
                    {f.name: f for f in new_phase.exit.optional},
                )
            )

        return changes

    @staticmethod
    def _compare_field_lists(
        phase: str,
        direction: str,
        old_fields: dict,
        new_fields: dict,
    ) -> list[DriftChange]:
        changes: list[DriftChange] = []

        old_names = set(old_fields.keys())
        new_names = set(new_fields.keys())

        # Added fields
        for name in sorted(new_names - old_names):
            new_f = new_fields[name]
            is_breaking = (
                direction in ("entry", "enrichment")
                and new_f.severity.value == "blocking"
            )
            changes.append(
                DriftChange(
                    change_type="field_added",
                    phase=phase,
                    field=name,
                    direction=direction,
                    breaking=is_breaking,
                    description=(
                        f"Field '{name}' added to {phase}/{direction}"
                        + (" (BLOCKING — may break existing callers)"
                           if is_breaking else "")
                    ),
                    new_value=new_f.severity.value,
                )
            )

        # Removed fields
        for name in sorted(old_names - new_names):
            is_breaking = direction in ("exit", "exit_optional")
            changes.append(
                DriftChange(
                    change_type="field_removed",
                    phase=phase,
                    field=name,
                    direction=direction,
                    breaking=is_breaking,
                    description=(
                        f"Field '{name}' removed from {phase}/{direction}"
                        + (" (may break downstream phases)"
                           if is_breaking else "")
                    ),
                    old_value=old_fields[name].severity.value,
                )
            )

        # Severity changes on common fields
        for name in sorted(old_names & new_names):
            old_sev = old_fields[name].severity.value
            new_sev = new_fields[name].severity.value
            if old_sev != new_sev:
                is_breaking = (
                    new_sev == "blocking" and old_sev != "blocking"
                )
                changes.append(
                    DriftChange(
                        change_type="severity_changed",
                        phase=phase,
                        field=name,
                        direction=direction,
                        breaking=is_breaking,
                        description=(
                            f"Field '{name}' in {phase}/{direction}: "
                            f"severity {old_sev} → {new_sev}"
                            + (" (ESCALATED to blocking)"
                               if is_breaking else "")
                        ),
                        old_value=old_sev,
                        new_value=new_sev,
                    )
                )

        return changes

    # -- internal: chain changes ---------------------------------------------

    def _detect_chain_changes(
        self,
        old: ContextContract,
        new: ContextContract,
    ) -> list[DriftChange]:
        changes: list[DriftChange] = []

        old_chains = {c.chain_id for c in old.propagation_chains}
        new_chains = {c.chain_id for c in new.propagation_chains}

        for chain_id in sorted(new_chains - old_chains):
            changes.append(
                DriftChange(
                    change_type="chain_added",
                    field=chain_id,
                    direction="chain",
                    breaking=False,
                    description=f"Propagation chain '{chain_id}' added",
                )
            )

        for chain_id in sorted(old_chains - new_chains):
            changes.append(
                DriftChange(
                    change_type="chain_removed",
                    field=chain_id,
                    direction="chain",
                    breaking=True,
                    description=(
                        f"Propagation chain '{chain_id}' removed — "
                        f"end-to-end verification lost"
                    ),
                )
            )

        return changes
