# Contracts Schemas (v1)

These schemas define the minimal typed contracts for interoperable A2A execution in ContextCore.

## Files

- `task-span-contract.schema.json`
- `handoff-contract.schema.json`
- `artifact-intent.schema.json`
- `gate-result.schema.json`

## Why these exist

- Keep agent-to-agent communication typed and machine-validated.
- Prevent silent drift across handoffs (checksums, mappings, phase gates).
- Make task and artifact lifecycle queryable through trace/span attributes.
- Reduce prose parsing by downstream systems.

## How to use

1. Produce payloads from agents/services in JSON.
2. Validate payloads against the schema before writing handoff artifacts or emitting spans.
3. Reject invalid payloads at boundary gates.
4. Persist valid payloads as execution evidence.

## Contract summaries

### 1) TaskSpanContract

Use for a task/subtask span lifecycle record.

Required:

- `schema_version` = `v1`
- `project_id`
- `task_id`
- `phase`
- `status`

Use when:

- opening/updating/closing phase spans
- recording blocked reasons and next action
- attaching checksum and quality counters

Example:

```json
{
  "schema_version": "v1",
  "project_id": "contextcore",
  "trace_id": "trace-123",
  "span_id": "span-abc",
  "task_id": "PI-101-002-S3",
  "parent_task_id": "PI-101-002",
  "phase": "CONTRACT_INTEGRITY",
  "status": "in_progress",
  "checksums": {
    "source_checksum": "sha256:111",
    "artifact_manifest_checksum": "sha256:222",
    "project_context_checksum": "sha256:333"
  },
  "metrics": {
    "gap_count": 6,
    "feature_count": 6,
    "complexity_score": 44.0,
    "artifact_count": 0
  },
  "acceptance_criteria": [
    "source checksum must match seed",
    "artifact_task_mapping covers all artifact ids"
  ],
  "timestamp": "2026-02-13T20:30:00Z"
}
```

### 2) HandoffContract

Use for typed A2A delegation requests and results.

Required:

- `schema_version` = `v1`
- `handoff_id`
- `from_agent`
- `to_agent`
- `capability_id`
- `inputs`
- `expected_output`

Use when:

- delegating a capability call between agents
- tracking handoff status transitions
- linking result traces back to the caller

Example:

```json
{
  "schema_version": "v1",
  "handoff_id": "handoff-789",
  "project_id": "contextcore",
  "trace_id": "trace-123",
  "parent_task_id": "PI-101-002-S6",
  "from_agent": "orchestrator",
  "to_agent": "artifact-generator",
  "capability_id": "generate_observability_artifact",
  "priority": "high",
  "inputs": {
    "artifact_id": "checkout-api-dashboard",
    "artifact_type": "grafana_dashboard",
    "parameters": {
      "service": "checkout-api"
    }
  },
  "expected_output": {
    "type": "artifact_bundle",
    "schema_ref": "https://contextcore.io/schemas/contracts/artifact-intent.schema.json"
  },
  "status": "pending",
  "created_at": "2026-02-13T20:35:00Z"
}
```

### 3) ArtifactIntent

Use for declaring an artifact requirement before generation.

Required:

- `schema_version` = `v1`
- `artifact_id`
- `artifact_type`
- `intent`
- `owner`
- `parameter_sources`

Use when:

- promoting an artifact need into a taskable unit
- preserving output conventions and semantic conventions
- making generation intent auditable

Example:

```json
{
  "schema_version": "v1",
  "artifact_id": "checkout-api-dashboard",
  "artifact_type": "grafana_dashboard",
  "intent": "create",
  "owner": "observability-team",
  "task_id": "PI-101-002-S7",
  "promoted_to_task": true,
  "promotion_reason": "risk",
  "parameter_sources": {
    "service_name": "manifest.spec.project.id",
    "slo_latency_p99": "manifest.spec.project.requirements.latencyP99"
  },
  "output_convention": {
    "output_path": "grafana/provisioning/dashboards",
    "output_ext": ".json"
  },
  "semantic_conventions": {
    "metrics_prefix": "contextcore_"
  },
  "acceptance_criteria": [
    "dashboard contains latency and error budget panels"
  ]
}
```

### 4) GateResult

Use for phase boundary checks and fail-fast decisions.

Required:

- `schema_version` = `v1`
- `gate_id`
- `phase`
- `result`
- `severity`
- `checked_at`

Use when:

- validating contract integrity, parse/gap parity, schema correctness
- deciding whether downstream spans may start
- storing evidence for blocked/failure decisions

Example:

```json
{
  "schema_version": "v1",
  "gate_id": "PI-101-002-S3-C2",
  "trace_id": "trace-123",
  "task_id": "PI-101-002-S3",
  "phase": "CONTRACT_INTEGRITY",
  "result": "pass",
  "severity": "info",
  "blocking": false,
  "reason": "All checksums match expected chain",
  "next_action": "Proceed to INGEST_PARSE_ASSESS",
  "evidence": [
    {
      "type": "file",
      "ref": "out/onboarding-metadata.json",
      "description": "Validated source_checksum against current manifest hash"
    }
  ],
  "checked_at": "2026-02-13T20:40:00Z"
}
```

## Recommended boundary validation points

- Before writing handoff payloads
- Before accepting a handoff for execution
- Before starting a downstream phase span
- Before finalizing a feature trace

## Compatibility notes

- `schema_version` is required and pinned to `v1` for all contracts.
- All schemas use `additionalProperties: false` at top-level to reduce accidental drift.
- Additive schema evolution should use a new version (`v2`) rather than widening `v1` semantics.
