# A2A Contracts Quickstart

Get started with ContextCore A2A contracts in 5 minutes.

> **Full architecture reference**: See [A2A Communications Design](design/contextcore-a2a-comms-design.md) for the complete design and implementation details.

## Prerequisites

```bash
pip install contextcore          # or: pip install -e ".[dev]"
```

---

## 1. Validate a contract payload

Create a JSON payload and validate it against one of the 4 contract schemas:

```bash
# TaskSpanContract
echo '{
  "schema_version": "v1",
  "project_id": "my-project",
  "task_id": "TASK-001-S3",
  "phase": "CONTRACT_INTEGRITY",
  "status": "in_progress"
}' > /tmp/span.json

contextcore contract a2a-validate TaskSpanContract /tmp/span.json
# OK  TaskSpanContract validation passed (/tmp/span.json)
```

Invalid payloads produce actionable errors:

```bash
echo '{"schema_version": "v2", "task_id": "T-1"}' > /tmp/bad.json

contextcore contract a2a-validate TaskSpanContract /tmp/bad.json
# FAIL  TaskSpanContract validation failed (/tmp/bad.json)
#   [MISSING_REQUIRED_FIELD] /: 'project_id' is a required property
#     -> Add the missing required field at '/'.
#   [CONST_VIOLATION] /schema_version: 'v1' was expected
#     -> Set '/schema_version' to the required constant value.
```

---

## 2. Use contracts in Python

```python
from contextcore.contracts.a2a import (
    TaskSpanContract, HandoffContract, ArtifactIntent, GateResult,
    Phase, SpanStatus,
)

# Create a task span contract
contract = TaskSpanContract(
    project_id="my-project",
    task_id="TASK-001-S3",
    phase=Phase.CONTRACT_INTEGRITY,
    status=SpanStatus.IN_PROGRESS,
)

# Serialize (exclude None values for JSON schema compliance)
payload = contract.model_dump(mode="json", exclude_none=True)
```

---

## 3. Enforce boundaries

Validate payloads at every trust boundary (outbound and inbound):

```python
from contextcore.contracts.a2a import validate_outbound, validate_inbound

# Before sending a handoff — raises BoundaryEnforcementError on failure
validate_outbound("HandoffContract", handoff_payload)

# On receiving a handoff — rejects invalid payloads deterministically
validate_inbound("HandoffContract", received_payload)
```

---

## 4. Run gate checks

Use the built-in gates to enforce phase transitions:

```python
from contextcore.contracts.a2a import GateChecker

checker = GateChecker(trace_id="PI-101-002")

# Checksum chain integrity
r1 = checker.check_checksum_chain(
    gate_id="S3-C2",
    task_id="PI-101-002-S3",
    expected_checksums={"source": "sha256:abc123"},
    actual_checksums={"source": "sha256:abc123"},
)

# Artifact-task mapping completeness
r2 = checker.check_mapping_completeness(
    gate_id="S3-C1",
    task_id="PI-101-002-S3",
    artifact_ids=["dashboard", "alert-rule"],
    task_mapping={"dashboard": "T-10", "alert-rule": "T-11"},
)

# Gap/feature parity
r3 = checker.check_gap_parity(
    gate_id="S4-C1",
    task_id="PI-101-002-S4",
    gap_ids=["latency", "errors", "throughput"],
    feature_ids=["latency", "errors", "throughput"],
)

# Check if anything is blocking
if checker.has_blocking_failure:
    print("Blocked:", checker.blocking_failures)
else:
    print("All gates passed:", checker.summary())
```

Or from the CLI:

```bash
echo '{"expected": {"source": "sha256:aaa"}, "actual": {"source": "sha256:aaa"}}' > /tmp/gate.json

contextcore contract a2a-gate checksum /tmp/gate.json \
    --gate-id S3-C2 --task-id PI-101-002-S3
# PASS  S3-C2 (CONTRACT_INTEGRITY)
```

---

## 5. Run the PI-101-002 pilot

Execute a full end-to-end trace with gate evidence:

```bash
# Happy path — all 10 spans complete
contextcore contract a2a-pilot

# Inject a checksum mismatch — blocks at S3
contextcore contract a2a-pilot --source-checksum sha256:STALE

# Inject a gap parity failure — blocks at S4
contextcore contract a2a-pilot --drop-feature gap-latency-panel

# Inject test failures — blocks at S8
contextcore contract a2a-pilot --test-failures 2
```

Evidence is written to `out/pilot-trace.json` by default.

---

## 6. Check pipeline integrity on real export output

After running `contextcore manifest export`, validate the output with the pipeline checker:

```bash
# Run all 6 gates against an export output directory
contextcore contract a2a-check-pipeline out/enrichment-validation

# Fail CI if any blocking gate fails
contextcore contract a2a-check-pipeline out/enrichment-validation --fail-on-unhealthy

# Write a JSON report for automation
contextcore contract a2a-check-pipeline out/enrichment-validation --report pipeline-report.json
```

The checker reads `onboarding-metadata.json` and `provenance.json` and runs:

| # | Gate | Blocking? |
|---|------|-----------|
| 1 | Structural integrity — required fields exist | Yes |
| 2 | Checksum chain — recompute and compare file hashes | Yes |
| 3 | Provenance cross-check — consistency with provenance.json | Yes |
| 4 | Mapping completeness — every gap has a task mapping | Yes |
| 5 | Gap parity — gaps vs artifact features | Yes |
| 6 | Design calibration — depth tiers vs artifact types | No (warning) |

Or use it from Python:

```python
from contextcore.contracts.a2a import PipelineChecker

checker = PipelineChecker("out/enrichment-validation")
report = checker.run()

if report.is_healthy:
    print("All gates passed")
else:
    print(report.to_text())
```

---

## 7. Run the Three Questions diagnostic

When something goes wrong, the diagnostic walks through the pipeline in order and stops at the first failing layer:

```bash
# Check export layer only (Q1)
contextcore contract a2a-diagnose out/enrichment-validation

# Full pipeline diagnostic (Q1 + Q2 + Q3)
contextcore contract a2a-diagnose out/enrichment-validation \
    --ingestion-dir out/plan-ingestion \
    --artisan-dir out/artisan

# Fail CI if any question fails
contextcore contract a2a-diagnose out/enrichment-validation --fail-on-issue
```

The three questions:

| Question | Layer | What it checks |
|----------|-------|----------------|
| **Q1: Is the contract complete?** | Export | Pipeline checker gates + manifest population, parameter schema, `--scan-existing` |
| **Q2: Was the contract faithfully translated?** | Plan Ingestion | PARSE coverage, complexity scoring, routing correctness |
| **Q3: Was the translated plan faithfully executed?** | Artisan | Design fidelity, output files, test results, finalize report |

If Q1 fails, Q2 and Q3 are skipped — fixing downstream when the upstream contract is broken is wasted effort.

Or use it from Python:

```python
from contextcore.contracts.a2a import ThreeQuestionsDiagnostic

diag = ThreeQuestionsDiagnostic(
    "out/enrichment-validation",
    ingestion_dir="out/plan-ingestion",
    artisan_dir="out/artisan",
)
result = diag.run()

if not result.all_passed:
    print(f"Start here: {result.start_here}")
```

---

## 8. View the governance dashboard

Import the dashboard into Grafana:

```bash
contextcore dashboards provision
# Or manually import: k8s/observability/dashboards/a2a-governance.json
```

The dashboard has 8 panels answering:

| Panel | Question answered |
|-------|-------------------|
| Blocked Span Hotspot | Which phases block most often? |
| Gate Failures | Which gates are failing and how severe? |
| Blocked Spans Detail | What failed, where, why, what next? |
| Finalize Outcomes | How often does finalization succeed vs fail? |
| Handoff Validation Failures | Which handoffs are being rejected? |
| Dropped Artifacts | Which artifacts were silently dropped? |
| Finalize Failure Trend | Is the failure rate improving or worsening? |
| Boundary Enforcement Errors | How many invalid payloads are caught? |

---

## Contract schemas reference

| Contract | Schema | Required fields |
|----------|--------|-----------------|
| `TaskSpanContract` | `schemas/contracts/task-span-contract.schema.json` | `schema_version`, `project_id`, `task_id`, `phase`, `status` |
| `HandoffContract` | `schemas/contracts/handoff-contract.schema.json` | `schema_version`, `handoff_id`, `from_agent`, `to_agent`, `capability_id`, `inputs`, `expected_output` |
| `ArtifactIntent` | `schemas/contracts/artifact-intent.schema.json` | `schema_version`, `artifact_id`, `artifact_type`, `intent`, `owner`, `parameter_sources` |
| `GateResult` | `schemas/contracts/gate-result.schema.json` | `schema_version`, `gate_id`, `phase`, `result`, `severity`, `checked_at` |

All contracts enforce:
- `schema_version = "v1"` (required, constant)
- `additionalProperties: false` (unknown top-level fields rejected)
- Additive changes require `v2`; no widening of `v1`

---

## For agent implementers

- Emit `HandoffContract` for every delegation.
- Emit `GateResult` for every boundary decision.
- Use `ArtifactIntent` for planned artifact work; promote to task only when policy criteria are met.
- Keep local debugging as span events, not contract fields.
- Validate at write-time **and** read-time using `validate_outbound` / `validate_inbound`.
- Run `a2a-check-pipeline` after every export to catch integrity issues before they cascade.
- Run `a2a-diagnose` when troubleshooting — it tells you which layer to fix first.

## When to promote an artifact to a task

Promote when one or more apply:

1. Multi-step lifecycle needed
2. Dependency chain exists
3. Risk/severity warrants explicit control
4. Ownership and acceptance criteria are defined
5. Traceability/audit evidence required

Otherwise keep it as an event within an existing phase task.
