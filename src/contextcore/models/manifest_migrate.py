"""
Context Manifest migration utilities.

Provides non-destructive migration from v1.1 to v2.0 manifests.

Migration rules:
- Move `objectives/strategies` into `strategy.*`
- Keep `spec` unchanged (derived from v1.1 distill_crd)
- Default `guidance` to empty (humans add this later)
- Preserve `metadata.changelog` and append a migration entry

Usage:
    from contextcore.models.manifest_migrate import migrate_v1_to_v2
    from contextcore.models.manifest import load_context_manifest

    v1 = load_context_manifest("path/to/.contextcore.yaml")
    v2_dict = migrate_v1_to_v2(v1)

    # Optionally write back
    with open("path/to/.contextcore.yaml", "w") as f:
        yaml.dump(v2_dict, f)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from contextcore.models.manifest import (
    ContextManifest,
    Objective,
    Strategy,
    Tactic,
    Insight,
    ChangelogEntry,
)
from contextcore.models.manifest_v2 import (
    ContextManifestV2,
    AgentGuidanceSpec,
    InsightV2,
    ManifestMetadataV2,
    ManifestState,
    ObjectiveV2,
    StrategySpec,
    TacticV2,
)


def _migrate_objective(obj: Objective) -> ObjectiveV2:
    """Convert a v1.1 Objective to v2 ObjectiveV2."""
    return ObjectiveV2(
        id=obj.id,
        description=obj.description,
        key_results=obj.key_results,  # KeyResult is unchanged
    )


def _migrate_tactic(
    tactic: Tactic, strategy_id: Optional[str] = None, objective_refs: Optional[List[str]] = None
) -> TacticV2:
    """Convert a v1.1 Tactic to v2 TacticV2."""
    return TacticV2(
        id=tactic.id,
        description=tactic.description,
        status=tactic.status,
        owner=tactic.owner,
        start_date=tactic.start_date,
        due_date=tactic.due_date,
        completed_date=tactic.completed_date,
        blocked_reason=tactic.blocked_reason,
        progress=tactic.progress,
        linked_objectives=objective_refs or [],
        artifacts=tactic.artifacts,
    )


def _migrate_insight(insight: Insight) -> InsightV2:
    """Convert a v1.1 Insight to v2 InsightV2."""
    return InsightV2(
        id=insight.id or f"INS-MIGRATED-{hash(insight.summary) % 10000:04d}",
        type=insight.type,
        summary=insight.summary,
        confidence=insight.confidence,
        source=insight.source,
        severity=insight.severity,
        observed_at=insight.observed_at,
        expires_at=insight.expires_at,
        impact=insight.impact,
        evidence=insight.evidence,
        recommended_actions=insight.recommended_actions,
    )


def _flatten_tactics_from_strategies(
    strategies: List[Strategy],
) -> tuple[List[TacticV2], List[Dict[str, Any]]]:
    """
    Flatten tactics from strategy hierarchy.

    Returns:
        Tuple of (tactics list, strategy_groups for reference)
    """
    tactics: List[TacticV2] = []
    strategy_groups: List[Dict[str, Any]] = []

    for strategy in strategies:
        # Build strategy group reference
        group = {
            "id": strategy.id,
            "description": strategy.description,
            "horizon": strategy.horizon.value if strategy.horizon else None,
            "rationale": strategy.rationale,
            "objective_refs": strategy.objective_refs,
        }
        strategy_groups.append(group)

        # Migrate each tactic, linking to strategy's objective refs
        for tactic in strategy.tactics:
            migrated_tactic = _migrate_tactic(
                tactic,
                strategy_id=strategy.id,
                objective_refs=strategy.objective_refs,
            )
            tactics.append(migrated_tactic)

    return tactics, strategy_groups


def migrate_v1_to_v2(
    v1: ContextManifest,
    *,
    migration_note: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Migrate a v1.1 ContextManifest to v2.0 format.

    This is a non-destructive migration that:
    - Converts objectives to ObjectiveV2 (minimal change)
    - Flattens tactics from strategy hierarchy
    - Keeps strategy groupings for reference
    - Creates empty guidance section
    - Preserves and extends changelog

    Args:
        v1: The v1.1 ContextManifest to migrate
        migration_note: Optional note to add to changelog

    Returns:
        Dictionary suitable for YAML serialization as v2 manifest
    """
    # 1. Migrate objectives
    objectives_v2 = [_migrate_objective(obj) for obj in v1.objectives]

    # 2. Flatten tactics from strategies
    tactics_v2, strategy_groups = _flatten_tactics_from_strategies(v1.strategies)

    # 3. Migrate insights (add id if missing)
    insights_v2 = [_migrate_insight(ins) for ins in v1.insights]

    # 4. Build strategy spec
    strategy_spec = StrategySpec(
        objectives=objectives_v2,
        tactics=tactics_v2,
        strategy_groups=strategy_groups,
    )

    # 5. Build metadata (preserve changelog, add migration entry)
    changelog = list(v1.metadata.changelog) if v1.metadata else []
    summary_parts = [
        migration_note or "Migrated from v1.1 to v2.0",
        "Flattened strategy/tactic hierarchy",
        "Added guidance section (empty)",
    ]
    changelog.append(
        ChangelogEntry(
            version="2.0",
            date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            actor="agent:contextcore-migrate",
            summary="; ".join(summary_parts),
        )
    )

    metadata_v2 = ManifestMetadataV2(
        name=v1.metadata.name if v1.metadata else "migrated-manifest",
        owners=v1.metadata.owners if v1.metadata else [],
        changelog=changelog,
        last_updated=datetime.now(timezone.utc),
        links={},
    )

    # 6. Extract spec from v1.1 (if it has distill_crd capability)
    spec_dict = v1.distill_crd(namespace="default").get("spec", {})

    # 7. Build the v2 manifest dict
    v2_dict: Dict[str, Any] = {
        "apiVersion": "contextcore.io/v1alpha2",
        "kind": "ContextManifest",
        "metadata": metadata_v2.model_dump(by_alias=True, exclude_none=True),
        "spec": spec_dict,
        "strategy": strategy_spec.model_dump(by_alias=True, exclude_none=True),
        "guidance": AgentGuidanceSpec().model_dump(by_alias=True, exclude_none=True),
        "insights": [ins.model_dump(by_alias=True, exclude_none=True) for ins in insights_v2],
        "state": None,
    }

    return v2_dict


def migrate_v1_to_v2_model(
    v1: ContextManifest,
    *,
    migration_note: Optional[str] = None,
) -> ContextManifestV2:
    """
    Migrate a v1.1 ContextManifest to v2.0 and return as ContextManifestV2 model.

    This validates the migration output against the v2 schema.

    Args:
        v1: The v1.1 ContextManifest to migrate
        migration_note: Optional note to add to changelog

    Returns:
        Validated ContextManifestV2 instance
    """
    v2_dict = migrate_v1_to_v2(v1, migration_note=migration_note)
    return ContextManifestV2(**v2_dict)


def validate_migration(v1: ContextManifest, v2: ContextManifestV2) -> List[str]:
    """
    Validate that migration preserved data correctly.

    Returns a list of validation messages (empty = all good).
    """
    issues: List[str] = []

    # Check objective count
    if len(v2.strategy.objectives) != len(v1.objectives):
        issues.append(
            f"Objective count mismatch: v1={len(v1.objectives)}, v2={len(v2.strategy.objectives)}"
        )

    # Check tactic count (sum of all tactics from all strategies)
    v1_tactic_count = sum(len(s.tactics) for s in v1.strategies)
    if len(v2.strategy.tactics) != v1_tactic_count:
        issues.append(
            f"Tactic count mismatch: v1={v1_tactic_count}, v2={len(v2.strategy.tactics)}"
        )

    # Check insight count
    if len(v2.insights) != len(v1.insights):
        issues.append(
            f"Insight count mismatch: v1={len(v1.insights)}, v2={len(v2.insights)}"
        )

    # Check metadata preserved
    if v1.metadata:
        if v2.metadata.name != v1.metadata.name:
            issues.append(
                f"Metadata name changed: v1={v1.metadata.name}, v2={v2.metadata.name}"
            )

    return issues
