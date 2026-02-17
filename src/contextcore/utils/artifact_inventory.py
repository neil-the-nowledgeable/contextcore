"""
Artifact inventory builder for the pipeline provenance system.

Builds typed inventory entries that register reusable export-stage artifacts
in ``run-provenance.json``, enabling downstream pipeline stages to discover
what has already been computed (Mottainai Design Principle).

Each entry declares: what the artifact is (semantic role), where it lives
(file path + json_path), who produced it (pipeline stage), whether it is
fresh (checksum + timestamp), and what downstream stages should use it for
(consumption hints).

Usage::

    from contextcore.utils.artifact_inventory import build_export_inventory

    inventory = build_export_inventory(
        onboarding_metadata=metadata,
        source_checksum="a8111a9c...",
    )
    # Pass to build_run_provenance_payload(artifact_inventory=inventory)
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Controlled vocabulary: export-stage inventory roles
# ---------------------------------------------------------------------------

EXPORT_INVENTORY_ROLES: Dict[str, Dict[str, Any]] = {
    "derivation_rules": {
        "json_path": "$.derivation_rules",
        "metadata_key": "derivation_rules",
        "description": "Business-to-parameter derivation rules per artifact type",
        "consumers": ["artisan.design", "artisan.implement"],
        "consumption_hint": (
            "Inject per-task derivation rules into FeatureContext.additional_context "
            "to avoid LLM re-derivation of business-to-parameter mappings."
        ),
    },
    "resolved_parameters": {
        "json_path": "$.resolved_artifact_parameters",
        "metadata_key": "resolved_artifact_parameters",
        "description": "Pre-resolved parameter values per artifact, ready for template substitution",
        "consumers": ["artisan.design", "artisan.implement"],
        "consumption_hint": (
            "Use concrete values (e.g., alertSeverity: P2) instead of asking "
            "the LLM to derive them from manifest fields."
        ),
    },
    "output_contracts": {
        "json_path": "$.expected_output_contracts",
        "metadata_key": "expected_output_contracts",
        "description": "Per-artifact-type expected depth, completeness markers, max lines/tokens",
        "consumers": ["artisan.design", "artisan.implement", "artisan.test"],
        "consumption_hint": (
            "Use expected_depth to override LOC-based calibration. "
            "Use completeness_markers for post-generation validation."
        ),
    },
    "dependency_graph": {
        "json_path": "$.artifact_dependency_graph",
        "metadata_key": "artifact_dependency_graph",
        "description": "Artifact-level dependency ordering",
        "consumers": ["ingestion.parse", "artisan.plan"],
        "consumption_hint": "Use for task ordering instead of LLM-inferred dependency edges.",
    },
    "calibration_hints": {
        "json_path": "$.design_calibration_hints",
        "metadata_key": "design_calibration_hints",
        "description": "Per-artifact-type expected depth tier and LOC range",
        "consumers": ["ingestion.calibration", "artisan.design"],
        "consumption_hint": (
            "Override LOC-based depth tier when artifact type has a known "
            "expected depth (e.g., dashboards are always comprehensive)."
        ),
    },
    "open_questions": {
        "json_path": "$.open_questions",
        "metadata_key": "open_questions",
        "description": "Unresolved questions from manifest guidance",
        "consumers": ["artisan.design"],
        "consumption_hint": (
            "Surface in design prompt so LLM does not make decisions "
            "that contradict unresolved questions."
        ),
    },
    "parameter_sources": {
        "json_path": "$.parameter_sources",
        "metadata_key": "parameter_sources",
        "description": "Per-artifact-type parameter origin mapping",
        "consumers": ["artisan.design", "artisan.implement"],
        "consumption_hint": "Use to trace parameter values back to manifest fields.",
    },
    "semantic_conventions": {
        "json_path": "$.semantic_conventions",
        "metadata_key": "semantic_conventions",
        "description": "Metric and label naming conventions",
        "consumers": ["artisan.design", "artisan.implement"],
        "consumption_hint": "Enforce consistent naming in generated observability artifacts.",
    },
    "example_artifacts": {
        "json_path": "$.example_artifacts",
        "metadata_key": "example_artifacts",
        "description": "Example output per artifact type",
        "consumers": ["artisan.design"],
        "consumption_hint": "Provide as few-shot examples in design prompts.",
    },
    "coverage_gaps": {
        "json_path": "$.coverage_gaps",
        "metadata_key": "coverage_gaps",
        "description": "Artifact types needing generation",
        "consumers": ["ingestion.parse", "artisan.plan"],
        "consumption_hint": "Use as the authoritative list of what needs to be generated.",
    },
}


# ---------------------------------------------------------------------------
# Controlled vocabulary: pre-pipeline inventory roles (create / polish)
# ---------------------------------------------------------------------------

PRE_PIPELINE_INVENTORY_ROLES: Dict[str, Dict[str, Any]] = {
    "project_context": {
        "stage": "create",
        "description": "Project context resource produced by contextcore create",
        "consumers": ["contextcore.manifest.export", "startd8.workflow.plan_ingestion"],
        "consumption_hint": (
            "Provides project identity and business context for downstream "
            "manifest export and plan-ingestion stages."
        ),
    },
    "polish_report": {
        "stage": "polish",
        "description": "Plan quality report produced by contextcore polish",
        "consumers": ["startd8.workflow.plan_ingestion", "artisan.review"],
        "consumption_hint": (
            "Surface polish check results in plan-ingestion and review phases "
            "so agents know which quality gates the plan already passes."
        ),
    },
    "fix_report": {
        "stage": "fix",
        "description": "Auto-remediation report produced by contextcore fix",
        "consumers": ["contextcore.manifest.init_from_plan", "startd8.workflow.plan_ingestion", "artisan.review"],
        "consumption_hint": (
            "Surface fix actions so agents know which gaps were auto-remediated "
            "vs. need human attention."
        ),
    },
    "remediated_plan": {
        "stage": "fix",
        "description": "Remediated plan document with deterministic fixes applied",
        "consumers": ["contextcore.manifest.analyze_plan", "contextcore.manifest.init_from_plan"],
        "consumption_hint": (
            "Use as --plan input instead of original. "
            "Passes all fixable polish checks."
        ),
    },
}


# ---------------------------------------------------------------------------
# Checksum helper
# ---------------------------------------------------------------------------

def compute_sub_document_checksum(data: Any) -> str:
    """Compute SHA-256 of a JSON-serializable sub-document.

    Uses ``json.dumps(data, sort_keys=True)`` for deterministic serialization.
    """
    serialized = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Entry builder
# ---------------------------------------------------------------------------

def build_inventory_entry(
    role: str,
    stage: str,
    source_file: str,
    produced_by: str,
    data: Any,
    *,
    json_path: Optional[str] = None,
    description: str = "",
    consumers: Optional[List[str]] = None,
    consumption_hint: str = "",
    source_checksum: Optional[str] = None,
    source_checksum_file: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a single artifact inventory entry.

    Args:
        role: Semantic role from the controlled vocabulary.
        stage: Pipeline stage (e.g. ``"export"``, ``"ingestion"``).
        source_file: Relative path to the file containing this artifact.
        produced_by: Fully qualified producer identifier.
        data: The artifact data (used to compute checksum).
        json_path: JSONPath expression to the artifact within the source file.
        description: Human-readable description.
        consumers: Pipeline stages/phases that should use this artifact.
        consumption_hint: Guidance for how the consumer should use the artifact.
        source_checksum: SHA-256 of the upstream source the artifact was derived from.
        source_checksum_file: Path to the upstream source file.
    """
    entry: Dict[str, Any] = {
        "artifact_id": f"{stage}.{role}",
        "role": role,
        "description": description,
        "produced_by": produced_by,
        "stage": stage,
        "source_file": source_file,
        "sha256": compute_sub_document_checksum(data),
        "produced_at": datetime.now(timezone.utc).isoformat(),
        "consumers": consumers or [],
        "consumption_hint": consumption_hint,
    }
    if json_path:
        entry["json_path"] = json_path
    if source_checksum or source_checksum_file:
        entry["freshness"] = {}
        if source_checksum:
            entry["freshness"]["source_checksum"] = source_checksum
        if source_checksum_file:
            entry["freshness"]["source_file"] = source_checksum_file
    return entry


# ---------------------------------------------------------------------------
# Export inventory builder
# ---------------------------------------------------------------------------

def build_export_inventory(
    onboarding_metadata: Dict[str, Any],
    source_checksum: Optional[str] = None,
    source_checksum_file: Optional[str] = None,
    source_file: str = "onboarding-metadata.json",
) -> List[Dict[str, Any]]:
    """Build inventory entries for all export-stage roles present in onboarding metadata.

    Iterates ``EXPORT_INVENTORY_ROLES``, checks whether each role's data exists
    in ``onboarding_metadata``, and builds an inventory entry for every role
    that has data. Roles with missing or empty data are skipped.

    Args:
        onboarding_metadata: The onboarding metadata dict (from export).
        source_checksum: SHA-256 of the upstream source manifest.
        source_checksum_file: Path to the upstream source manifest file.
        source_file: Relative filename of the onboarding metadata file.

    Returns:
        List of inventory entry dicts, one per role with data present.
    """
    inventory: List[Dict[str, Any]] = []

    for role, role_spec in EXPORT_INVENTORY_ROLES.items():
        metadata_key = role_spec["metadata_key"]
        data = onboarding_metadata.get(metadata_key)

        # Skip roles with no data or empty data
        if not data:
            continue

        entry = build_inventory_entry(
            role=role,
            stage="export",
            source_file=source_file,
            produced_by="contextcore.manifest.export",
            data=data,
            json_path=role_spec["json_path"],
            description=role_spec["description"],
            consumers=role_spec["consumers"],
            consumption_hint=role_spec["consumption_hint"],
            source_checksum=source_checksum,
            source_checksum_file=source_checksum_file,
        )
        inventory.append(entry)

    return inventory


# ---------------------------------------------------------------------------
# Extend inventory (for pre-pipeline stages: create, polish)
# ---------------------------------------------------------------------------

def extend_inventory(
    output_dir: Path,
    new_entries: List[Dict[str, Any]],
    *,
    filename: str = "run-provenance.json",
) -> bool:
    """Append inventory entries to an existing (or new) run-provenance.json.

    - Reads existing provenance file, or starts from an empty v2 skeleton.
    - Upgrades v1 provenance to v2 if needed (adds ``artifact_inventory``).
    - De-duplicates by ``artifact_id`` — existing entries win.
    - Writes atomically back to *output_dir/filename*.

    Returns ``True`` if the file was written successfully.
    """
    output_dir = Path(output_dir)
    prov_path = output_dir / filename

    # Read or create skeleton
    if prov_path.exists():
        try:
            payload = json.loads(prov_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            payload = {}
    else:
        payload = {}

    # Upgrade v1 → v2 if needed
    version = payload.get("version", "1.0.0")
    if version < "2.0.0":
        payload["version"] = "2.0.0"

    # Ensure artifact_inventory list exists
    existing = payload.setdefault("artifact_inventory", [])

    # Dedup: existing artifact_ids win
    existing_ids = {e["artifact_id"] for e in existing if "artifact_id" in e}
    for entry in new_entries:
        if entry.get("artifact_id") not in existing_ids:
            existing.append(entry)
            existing_ids.add(entry["artifact_id"])

    # Atomic write
    output_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = prov_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(prov_path)
    return True
