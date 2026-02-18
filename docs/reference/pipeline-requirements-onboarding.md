# Pipeline-Innate Requirements: Onboarding & Pipeline Integrity

**Scope:** These requirements apply to ALL projects processed through the ContextCore Capability Delivery Pipeline. They are inherited automatically and satisfied by artifact generation, not by plan features.

**Label:** `pipeline-innate` (appears in `requirements_hints[].labels` in `onboarding-metadata.json`)

---

## Onboarding Requirements

### REQ-CDP-ONB-001: Capability Index

**Priority:** P2
**Artifact:** `capability_index`

A capability index (`*.agent.yaml`) is generated or updated for the project. Capabilities are extracted from source code and API contracts. Each capability includes: `capability_id`, `category`, `maturity`, `summary`, `evidence`.

### REQ-CDP-ONB-002: Agent Card

**Priority:** P2
**Artifact:** `agent_card`

An A2A agent card (`agent-card.json`) is generated from the capability index. Skills are populated from capabilities with `audiences: [agent]`.

### REQ-CDP-ONB-003: MCP Tool Definitions

**Priority:** P3
**Artifact:** `mcp_tools`

MCP tool definitions (`mcp-tools.json`) are generated from the capability index. Each tool includes `inputSchema` and `annotations`.

### REQ-CDP-ONB-004: Onboarding Metadata

**Priority:** P1
**Artifact:** `onboarding_metadata`

Programmatic onboarding metadata is exported during Stage 4 (EXPORT). Metadata includes project description, objectives, tactics, and deliverables.

---

## Pipeline Integrity Requirements

### REQ-CDP-INT-001: Provenance Chain

**Priority:** P1
**Artifact:** `provenance`

Every pipeline run emits `provenance.json` with source checksums and `run-provenance.json` linking inputs to outputs. Checksum chain is verifiable: manifest checksum at export matches checksum at ingestion.

### REQ-CDP-INT-002: Translation Quality Gate

**Priority:** P1
**Artifact:** `ingestion-traceability`

Plan ingestion verifies that project-specific requirements map to plan features and pipeline-innate requirements map to artifact generation. Requirements coverage percentage is computed and reported. Low translation quality triggers route escalation.

---

## Implementation

These requirements are defined in `src/contextcore/utils/pipeline_requirements.py` and injected into `onboarding-metadata.json` by `src/contextcore/utils/onboarding.py`. The plan-ingestion consumer (`startd8-sdk`) auto-satisfies them based on the `pipeline-innate` label.

---

## Referenced By

The following files reference this document as the authoritative source for pipeline-innate artifact types:

- `src/contextcore/models/artifact_manifest.py` — `ArtifactType` enum docstring
- `src/contextcore/utils/artifact_conventions.py` — output conventions per type
- `src/contextcore/utils/onboarding.py` — parameter sources, examples, contracts, schemas
- `schemas/contracts/artifact-intent.schema.json` — schema description
- `docs/capability-index/contextcore.agent.yaml` — `scope_boundaries` and `artifact_type_registry` capability
- `docs/design/MANIFEST_EXPORT_REQUIREMENTS.md` — export requirements
- `docs/design/ARTIFACT_MANIFEST_CONTRACT.md` — artifact types table
- `docs/plans/EXPORT_PIPELINE_IMPLEMENTATION_SUMMARY.md` — calibration hints
