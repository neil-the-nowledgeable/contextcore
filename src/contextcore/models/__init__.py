"""
ContextCore models package.

Re-exports all CRD models from core.py (backward compatible) plus new
A2A-aligned Part, Message, and Artifact models.
"""

from __future__ import annotations

# CRD models (backward compatible - previously in models.py)
from contextcore.models.core import (
    BusinessSpec,
    DesignSpec,
    GeneratedArtifacts,
    ObservabilitySpec,
    ProjectContextSpec,
    ProjectContextStatus,
    ProjectSpec,
    RequirementsSpec,
    RiskSpec,
    TargetKind,
    TargetSpec,
    derive_observability,
)

# Contract types (re-exported for backward compat - previously accessible via models.py)
from contextcore.contracts.types import (
    AlertPriority,
    BusinessValue,
    Criticality,
    DashboardPlacement,
    LogLevel,
    RiskType,
)

# A2A-aligned models
from contextcore.models.part import Part, PartType
from contextcore.models.message import Message, MessageRole
from contextcore.models.artifact import Artifact

# Context Manifest v2.0 models (Active Control Plane)
from contextcore.models.manifest_v2 import (
    ContextManifestV2,
    AgentGuidanceSpec,
    Constraint,
    Focus,
    Preference,
    Question,
    StrategySpec,
    ObjectiveV2,
    TacticV2,
    InsightV2,
    ManifestMetadataV2,
    ManifestState,
)

# Version-aware manifest loader
from contextcore.models.manifest_loader import (
    load_manifest,
    load_manifest_v1,
    load_manifest_v2,
    load_manifest_from_dict,
    detect_manifest_version,
)

# Artifact Manifest (contract for Wayfinder implementations)
from contextcore.models.artifact_manifest import (
    ArtifactManifest,
    ArtifactManifestMetadata,
    ArtifactPriority,
    ArtifactSpec,
    ArtifactStatus,
    ArtifactType,
    CoverageSummary,
    DerivationRule,
    TargetCoverage,
)

# Legacy alias
Evidence = Part  # Evidence is now Part; use Part.from_evidence() for conversion

__all__ = [
    # CRD models
    "BusinessSpec",
    "DesignSpec",
    "GeneratedArtifacts",
    "ObservabilitySpec",
    "ProjectContextSpec",
    "ProjectContextStatus",
    "ProjectSpec",
    "RequirementsSpec",
    "RiskSpec",
    "TargetKind",
    "TargetSpec",
    "derive_observability",
    # Contract types
    "AlertPriority",
    "BusinessValue",
    "Criticality",
    "DashboardPlacement",
    "LogLevel",
    "RiskType",
    # A2A models
    "Part",
    "PartType",
    "Message",
    "MessageRole",
    "Artifact",
    # Legacy
    "Evidence",
    # Context Manifest v2.0
    "ContextManifestV2",
    "AgentGuidanceSpec",
    "Constraint",
    "Focus",
    "Preference",
    "Question",
    "StrategySpec",
    "ObjectiveV2",
    "TacticV2",
    "InsightV2",
    "ManifestMetadataV2",
    "ManifestState",
    # Manifest loader
    "load_manifest",
    "load_manifest_v1",
    "load_manifest_v2",
    "load_manifest_from_dict",
    "detect_manifest_version",
    # Artifact Manifest (Wayfinder contract)
    "ArtifactManifest",
    "ArtifactManifestMetadata",
    "ArtifactPriority",
    "ArtifactSpec",
    "ArtifactStatus",
    "ArtifactType",
    "CoverageSummary",
    "DerivationRule",
    "TargetCoverage",
]
