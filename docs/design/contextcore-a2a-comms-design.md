# ContextCore A2A Communications Design

**Status**: Implemented (v1)
**Last updated**: 2026-02-14

---

## Overview

ContextCore's Agent-to-Agent (A2A) governance layer provides contract-first validation, boundary enforcement, phase gates, pipeline integrity checking, and structured diagnostics for the full export pipeline. All agent handoffs, artifact promotions, and phase transitions are governed by typed contracts and quality gates — with observability built in via OpenTelemetry spans.

### Core Principle

> **Keep execution in the framework. Govern only boundaries and evidence in ContextCore.**

Agents and pipelines run their own logic; ContextCore validates contracts at ingress/egress points, enforces gates at phase transitions, and provides a structured diagnostic when something breaks.

### The Contract Chain in One Sentence

> `contextcore install init` validates the environment and seeds installation telemetry, the `.contextcore.yaml` manifest declares business intent, `contextcore manifest export` distills that intent into an artifact contract with onboarding metadata, the plan ingester parses and routes by complexity, and the artisan workflow executes the structured build — with checksums and provenance verifiable at every handoff.

### Document Relationships

| Document | Role | Relationship to this doc |
| -------- | ---- | ------------------------ |
| This document | Architecture reference | Primary — how the A2A governance layer works |
| [Export Pipeline Analysis Guide](../EXPORT_PIPELINE_ANALYSIS_GUIDE.md) | Operational reference | Foundational — defines the 7-step A2A governance-aware pipeline and 6 defense-in-depth principles that this layer implements |
| [Agent Communication Protocol](../agent-communication-protocol.md) | Protocol specification | Complementary — covers OTel-level agent insight/guidance/handoff span protocols |
| [A2A Contracts Design](../A2A_CONTRACTS_DESIGN.md) | Conceptual design | Predecessor — the pre-implementation "why and what" for the four contract types |
| [A2A Interoperability Plan](../A2A_INTEROPERABILITY_HIGH_LEVEL_PLAN.md) | Strategy | Predecessor — the pre-implementation strategy that shaped this design |

---

## Pipeline Context: Where A2A Governance Sits

The export pipeline is a 7-step data flow across three systems. A2A governance inserts validation at every handoff boundary (steps 3, 5, and 7 are governance gates):

```text
Step 1          Step 2           Step 3          Step 4            Step 5          Step 6           Step 7
┌──────────┐   ┌──────────┐    ┌──────────┐   ┌──────────────┐  ┌──────────┐   ┌──────────────┐  ┌──────────┐
│ Init     │──▶│ Export   │──▶ │ Gate 1   │──▶│ Plan         │──▶│ Gate 2   │──▶│ Contractor   │──▶│ Gate 3   │──▶ Output
│          │   │ --emit-  │    │ a2a-check│   │ Ingestion    │  │ a2a-     │   │ Execution    │  │ Finalize │
│          │   │ provenance│   │ -pipeline│   │              │  │ diagnose │   │              │  │ Verify   │
└──────────┘   └──────────┘    └──────────┘   └──────────────┘  └──────────┘   └──────────────┘  └──────────┘
 validates      reads manifest,  6 integrity    5 phases:         Three          7 phases:         per-artifact
 install,       writes 4 outputs checks         PARSE → ASSESS → Questions      PLAN → SCAFFOLD → checksums,
 seeds          + enrichment     (structural,   TRANSFORM →       (Q1/Q2/Q3)     DESIGN →          provenance
 telemetry      fields           checksum,etc)  REFINE → EMIT                    IMPLEMENT →       chain
                                                                                  TEST → REVIEW →
                                                                                  FINALIZE
```

Each step has a well-defined responsibility:

| Step | Command | Responsibility | Analogy |
| ---- | ------- | -------------- | ------- |
| **1. Init** | `contextcore install init` | Verifies installation readiness, emits initial telemetry | Opening the jobsite and confirming tools |
| **2. Export** | `contextcore manifest export --emit-provenance` | Declares *what* artifacts are needed, with enrichment metadata and checksum chain | The architect's blueprint |
| **3. Gate 1** | `contextcore contract a2a-check-pipeline` | 6 structural integrity checks on export output | Building inspector checks the blueprint |
| **4. Ingestion** | `startd8 workflow run plan-ingestion` | Converts blueprint into work items, routes by complexity | General contractor's estimate and crew assignment |
| **5. Gate 2** | `contextcore contract a2a-diagnose` | Three Questions diagnostic (contract complete? translated? executed?) | Mid-build quality audit |
| **6. Execution** | Prime or Artisan contractor | Structured build with design review, implementation, testing | Specialist crew doing the work |
| **7. Gate 3** | Finalize verification | Per-artifact checksums, provenance chain, status rollup | Final inspection |

The critical insight: **ContextCore knows WHAT artifacts are needed** (derived from business criticality, SLOs, alerting requirements) but does **not** know how to create them. The artifact manifest is the contract between the "what" and the "how."

### What Export Produces

The export command reads a `.contextcore.yaml` v2 manifest and produces up to 4 files:

| # | File | Purpose | Primary Consumer |
| - | ---- | ------- | ---------------- |
| 1 | `{project}-projectcontext.yaml` | Kubernetes CRD — project metadata, business criticality, SLOs, risks | K8s controller, Grafana labels |
| 2 | `{project}-artifact-manifest.yaml` | **The CONTRACT** — every observability artifact needed, with derivation rules | Plan Ingester, Artisan seed |
| 3 | `provenance.json` | Audit trail — git context, timestamps, checksums, CLI args | Integrity verification, compliance |
| 4 | `onboarding-metadata.json` | **Programmatic onboarding** — artifact schemas, parameter sources, coverage gaps, checksums | Plan Ingester (directly), Artisan context seed |

### Key Fields in onboarding-metadata.json

This is the file that the pipeline checker and Three Questions diagnostic operate on:

| Field | What it tells downstream | Used by |
| ----- | ----------------------- | ------- |
| `artifact_types` | Output conventions, file extensions, example snippets per type | Artisan SCAFFOLD, IMPLEMENT |
| `parameter_sources` | Which manifest/CRD field each parameter comes from | Artisan DESIGN, IMPLEMENT |
| `parameter_schema` | Expected parameter keys per artifact type | Plan Ingester ASSESS, Artisan validation |
| `coverage.gaps` | Which artifacts are missing and need generation | Plan Ingester PARSE, Artisan PLAN |
| `semantic_conventions` | Metric names, label conventions for dashboards/rules | Artisan DESIGN, IMPLEMENT |
| `artifact_manifest_checksum` | SHA-256 of the artifact manifest content | Integrity verification at every handoff |
| `project_context_checksum` | SHA-256 of the CRD content | Integrity verification |
| `source_checksum` | SHA-256 of the source `.contextcore.yaml` | Full provenance chain verification |
| `artifact_task_mapping` | Maps artifact ID to plan task ID (e.g., `checkout-api-dashboard` to `PI-019`) | Plan Ingester EMIT, task tracking |
| `design_calibration_hints` | Expected depth/LOC per artifact type | A2A design calibration gate |
| `file_ownership` | Maps output paths to artifact IDs and types | A2A gap parity gate |

### Plan Ingestion Phases (Step 3)

The plan ingestion workflow converts export output into SDK-native format in 5 phases. Understanding these is essential for interpreting Q2 diagnostic checks:

| Phase | What It Does | A2A Gate Relevance |
| ----- | ------------ | ------------------ |
| **PARSE** | LLM extracts features/dependencies from artifact manifest. Each artifact becomes a candidate feature. | Q2 `parse-coverage` — did every gap become a feature? |
| **ASSESS** | LLM scores 7 complexity dimensions (0-100) using parameter_sources, artifact_types, coverage.gaps | Q2 `assess-complexity-score` — is the score reasonable? |
| **TRANSFORM** | Routes by complexity: score <=40 to PrimeContractor, >40 to Artisan. `force_route` can override. | Q2 `transform-routing` — does route match score? |
| **REFINE** | N rounds of architectural review against artifact manifest as requirements spec | Q2 checks for review output files |
| **EMIT** | Writes review config and optionally ContextCore task tracking artifacts, closing the loop | Verifiable via NDJSON event log |

### Artisan Workflow Phases (Step 4)

When plan ingestion routes to the artisan path, the workflow receives the plan as an enriched context seed. Understanding these phases is essential for interpreting Q3 diagnostic checks:

| Phase | What It Does | A2A Gate Relevance |
| ----- | ------------ | ------------------ |
| **PLAN** | Deconstructs artifact manifest into individual tasks with `architectural_context` | Q3 — task count should match gap count |
| **SCAFFOLD** | Creates project structure using `output_path`/`output_ext` from onboarding metadata | Output conventions drive file layout |
| **DESIGN** | Assigns depth tiers per task (brief/standard/comprehensive) based on estimated LOC | Design calibration gate validates this |
| **IMPLEMENT** | `LeadContractorCodeGenerator` reads existing files + `parameter_sources` from metadata | Q3 `implement-output-files` |
| **TEST** | Validates generated artifacts | Q3 `test-results-exist` |
| **REVIEW** | Multi-agent review via 3-tier cost model (Haiku drafter, Sonnet validator, Opus reviewer) | Review output files |
| **FINALIZE** | Produces final report with per-artifact sha256, status rollup, cost aggregation | Q3 `finalize-all-tasks-succeeded` |

### Gate Placement

Each gate maps to an A2A implementation:

| Gate | Boundary | Implementation | What It Checks |
| ---- | -------- | -------------- | -------------- |
| **Gate 0** | Init -> Export | `pipeline_checker` structural integrity gate | Install baseline exists, telemetry endpoint correct |
| **Gate 1** | Export -> Plan Ingestion | `pipeline_checker` (checksum chain, provenance, design calibration) | Checksums match, metadata complete, calibration valid |
| **Gate 2** | Plan Ingestion -> Artisan | `three_questions` Q2, `check_mapping_completeness`, `check_gap_parity` | PARSE coverage, complexity scoring, routing, gap parity |
| **Gate 3** | Artisan -> Output | `three_questions` Q3, finalize report validation | Design fidelity, output files, test results, all tasks succeeded |

---

## Defense-in-Depth Implementation

The Export Pipeline Analysis Guide defines 6 defense-in-depth principles. The 7-step pipeline has a fundamental property: **each step trusts the output and assumptions from the prior step.** A defect in initialization or export can cascade silently through ingestion and into the artisan build. Defense in depth — now enforced by A2A governance gates at steps 3, 5, and 7 — means inserting validation at every boundary so that problems are caught as close to their source as possible.

### Principle 1: Validate at the Boundary -> `boundary.py` + `pipeline_checker.py`

Every handoff between steps is a trust boundary. `validate_outbound()` and `validate_inbound()` enforce schema compliance at each boundary. The pipeline checker runs 6 gates against real export output before downstream consumers touch it.

```text
Init ──[gate 0]──▶ Export ──[gate 1]──▶ Plan Ingestion ──[gate 2]──▶ Artisan ──[gate 3]──▶ Output
         │                    │                    │                       │
   structural-integrity  checksum-chain     mapping-completeness    finalize-report
                         provenance-check   gap-parity              output-files
                         design-calibration
```

**Gate 1 detail** (automated by `a2a-check-pipeline`):

- Verify `artifact_manifest_checksum` and `project_context_checksum` match actual file contents
- Check that `parameter_sources` reference fields that actually exist in the manifest
- Enforce `--min-coverage` to fail early if the manifest is under-specified

**Gate 2 detail** (automated by `a2a-diagnose --ingestion-dir`):

- After ASSESS, inspect complexity score. If all dimensions score near 0 or 100, the LLM likely misunderstood the input.
- After TRANSFORM, verify the routed plan references every artifact from `coverage.gaps`. Any artifact in the gap list that doesn't appear as a feature was dropped.
- After REFINE, check that architectural review suggestions were triaged. Untriaged suggestions indicate the review loop didn't converge.

**Gate 3 detail** (automated by `a2a-diagnose --artisan-dir`):

- After FINALIZE, verify per-task status rollup. A `partial` or `failed` overall status means some artifacts weren't generated.
- Compare the FINALIZE artifact list against `coverage.gaps`. Every gap should now have a corresponding artifact with a sha256 checksum.
- Verify provenance chain: `source_checksum` from export should match the source checksum in the finalize report.

### Principle 2: Adversarial Thinking -> `validator.py` + `BoundaryEnforcementError`

Even though all steps are yours, reason about each handoff as if the upstream step could produce malformed, incomplete, or stale output:

| Boundary | What could go wrong | Defense |
| -------- | ------------------- | ------- |
| Init -> Export | Installation baseline incomplete; telemetry endpoint wrong; operator skips verification | Run `contextcore install init` without `--skip-verify`; fix critical failures before exporting |
| Manifest -> Export | Empty fields, missing targets, stale version | Pre-flight validation catches schema errors; `--min-coverage` catches under-specification |
| Export -> Plan Ingestion | Files stale from previous run; checksums don't match; metadata hand-edited | `check_checksum_chain` recomputes from files; `provenance-consistency` cross-checks; reject if stale |
| Plan Ingestion -> Artisan | Score routed incorrectly; plan missing artifacts; task mapping incomplete | `check_gap_parity` catches dropped artifacts; `check_mapping_completeness` catches incomplete mapping |
| Artisan -> Final Output | Wrong parameters, missing fields, don't pass schema validation | Post-generation validation per artifact type; cross-reference against `parameter_sources` |

The `A2AValidator` rejects unknown fields (`additionalProperties: false`), enforces required fields, validates enums, and produces structured `ValidationErrorEnvelope` with `error_code`, `failed_path`, `message`, and `next_action`.

`BoundaryEnforcementError` includes a `.to_failure_event()` method that emits structured telemetry for every rejection — making silent handoff failures impossible.

### Principle 3: Checksums as Circuit Breakers -> `check_checksum_chain` + pipeline checker

The pipeline has a checksum chain that the pipeline checker **recomputes from actual files** and compares against stored values:

```text
.contextcore.yaml ──sha256──▶ onboarding-metadata.json
                              ├── source_checksum          ← recomputed from source file
                              ├── artifact_manifest_checksum ← recomputed from manifest YAML
                              └── project_context_checksum   ← recomputed from CRD YAML
                                        │
                    provenance.json cross-checks source_checksum
                                        │
                              ┌─────────▼─────────┐
                              │ artisan seed.json  │
                              │ (source_checksum)  │
                              └─────────┬─────────┘
                                        │
                              ┌─────────▼─────────┐
                              │ FINALIZE report    │
                              │ per-artifact sha256│
                              └───────────────────┘
```

**Rule**: If `source_checksum` at any stage doesn't match the original, the pipeline is operating on stale data. The checksum gate is **blocking** — it halts downstream execution.

### Principle 4: Fail Loud, Fail Early, Fail Specific -> `GateResult` + evidence

When diagnosing a failure, the most common mistake is assuming the problem is in the step where the symptom appeared. Trace backward:

```text
Symptom in artisan output
  └─ Is the artisan design spec correct?
       └─ Did plan ingestion produce the right plan?
            └─ Did the export produce a complete artifact manifest?
                 └─ Did init verify the environment and endpoint first?
                 └─ Is the source manifest correctly specified?
```

Every gate produces a `GateResult` with:

- `result`: pass/fail
- `severity`: info/warning/error/critical
- `blocking`: whether failure halts the pipeline
- `evidence`: list of `EvidenceItem` with `type`, `ref`, and `description`
- `next_action`: what the operator should do to fix it

For each stage, the diagnostic checks 4 dimensions:

1. **Input integrity**: Does the input checksum match what the previous stage wrote?
2. **Completeness**: Are all expected items present? (gap count = feature count = task count)
3. **Freshness**: Is `source_checksum` still valid against the current `.contextcore.yaml`?
4. **Parameter fidelity**: Do parameter values at this stage match the source manifest fields?

### Principle 5: Design Calibration Guards -> pipeline checker calibration gate

The design calibration gate validates that `design_calibration_hints` in onboarding metadata:

- Cover all artifact types with gaps
- Use valid depth tiers (`brief`, `standard`, `comprehensive`, `standard-comprehensive`)
- Have populated `expected_loc_range` and `red_flag` descriptions
- Cross-check against `expected_output_contracts` if present
- Validate actual generated artifact LOC against expected ranges (if artifacts exist)

| Artifact Type | Expected Depth | Red Flag |
| ------------- | -------------- | -------- |
| ServiceMonitor | Brief (<=50 LOC) | Calibrated as "comprehensive" — over-engineering |
| PrometheusRule | Standard (51-150 LOC) | Calibrated as "brief" — incomplete rules |
| Dashboard (Grafana JSON) | Comprehensive (>150 LOC) | Calibrated as "brief" — skeleton only |
| SLO Definition | Standard | Calibrated as "comprehensive" — over-engineering |
| Runbook | Standard-Comprehensive | Calibrated as "brief" — missing procedures |

If calibration doesn't match expected depth, the `architectural_context` fed from the manifest is likely incomplete or the LLM assessment was inaccurate. **Fix the input, don't patch the output.** This gate is non-blocking (warning severity) since miscalibration is a quality signal, not an integrity failure.

### Principle 6: Three Questions Diagnostic -> `three_questions.py`

The most important diagnostic rule: stop at the first failing layer.

| Question | Layer | Implemented Checks |
| -------- | ----- | ------------------ |
| **Q1: Is the contract complete?** | Export | All 6 pipeline checker gates + artifact manifest population, derivation rules, parameter schema, `--scan-existing` coverage |
| **Q2: Was the contract faithfully translated?** | Plan Ingestion | PARSE coverage (all gaps extracted as features), ASSESS complexity score, TRANSFORM routing correctness, architectural review output |
| **Q3: Was the translated plan faithfully executed?** | Artisan | Design handoff fidelity, generated output files, test/review results, FINALIZE report (all tasks succeeded) |

> *"If the answer to question 1 is 'no', fixing anything in questions 2 or 3 is wasted effort. Always start from the source."*

### Troubleshooting Matrix

The full symptom matrix automated by the Three Questions diagnostic:

| Symptom | Check in Export (Q1) | Check in Plan Ingester (Q2) | Check in Artisan (Q3) |
| ------- | -------------------- | --------------------------- | --------------------- |
| Missing artifact | Is it in the artifact manifest? Check `coverage.gaps` | Did PARSE extract it as a feature? | Did PLAN include it as a task? |
| Wrong parameters | Check `parameter_sources` — is the manifest field populated? | Did ASSESS correctly score complexity? | Did DESIGN use the right derivation rule? |
| Stale output | Compare `source_checksum` with current manifest hash | Was plan ingested from fresh export? | Does `enriched_seed_path` point to current export? |
| Routing mismatch | N/A | Check complexity score vs threshold (default 40) | N/A — artisan only runs if routed there |
| Checksum failure | Re-run export; check artifact/CRD checksums | Verify onboarding metadata wasn't hand-edited | Verify design-handoff.json schema version |
| Coverage below threshold | Use `--min-coverage`; run `--scan-existing` | N/A | Check finalize `tasks_failed` count |

---

## Contract Types (v1)

Four typed contracts govern A2A communication, each with a JSON schema and a matching Pydantic v2 model:

| Contract | Purpose | Key Fields |
| -------- | ------- | ---------- |
| **TaskSpanContract** | Task/subtask lifecycle as a trace span | `project_id`, `task_id`, `phase`, `status`, `checksums`, `metrics` |
| **HandoffContract** | Agent-to-agent delegation | `from_agent`, `to_agent`, `capability_id`, `inputs`, `expected_output`, `priority` |
| **ArtifactIntent** | Declaration of planned artifact work | `artifact_id`, `artifact_type`, `intent`, `parameter_sources`, `promotion_reason` |
| **GateResult** | Quality/integrity gate outcome | `gate_id`, `phase`, `result` (pass/fail), `severity`, `blocking`, `evidence` |

### Phase Enum Coverage

The `Phase` enum in `models.py` maps to the pipeline stages:

| Phase Enum | Pipeline Step | Covers |
| ---------- | ------------- | ------ |
| `INIT_BASELINE` | Step 1 (Init) | `contextcore install init` |
| `EXPORT_CONTRACT` | Step 2 (Export) | `contextcore manifest export` output validation |
| `CONTRACT_INTEGRITY` | Gate 1 | Checksum chain, provenance, mapping |
| `INGEST_PARSE_ASSESS` | Step 3 (PARSE + ASSESS) | Feature extraction, complexity scoring |
| `ROUTING_DECISION` | Step 3 (TRANSFORM) | Complexity-based routing |
| `ARTISAN_DESIGN` | Step 4 (PLAN + SCAFFOLD + DESIGN) | Design calibration, handoff |
| `ARTISAN_IMPLEMENT` | Step 4 (IMPLEMENT) | Code generation |
| `TEST_VALIDATE` | Step 4 (TEST) | Artifact validation |
| `REVIEW_CALIBRATE` | Step 4 (REVIEW) | Multi-agent review |
| `FINALIZE_VERIFY` | Step 4 (FINALIZE) | Status rollup, provenance chain |

### Schema Location

```text
schemas/contracts/
├── task-span-contract.schema.json
├── handoff-contract.schema.json
├── artifact-intent.schema.json
├── gate-result.schema.json
└── README.md
```

---

## Implementation Modules

All implementation lives in `src/contextcore/contracts/a2a/`:

### models.py — Pydantic v2 Contract Models

Typed Python models mirroring the JSON schemas. All models use `ConfigDict(extra="forbid")` for strict validation and enforce `schema_version = "v1"`.

Enums: `Phase`, `SpanStatus`, `HandoffPriority`, `HandoffContractStatus`, `ArtifactIntentAction`, `PromotionReason`, `GateOutcome`, `GateSeverity`

### validator.py — JSON Schema Validation (Principle 2)

- `A2AValidator.validate(contract_name, payload)` -> `ValidationReport`
- Produces structured `ValidationErrorEnvelope` with: `error_code`, `schema_id`, `failed_path`, `message`, `next_action`
- Error codes: `MISSING_REQUIRED_FIELD`, `UNKNOWN_FIELD`, `WRONG_TYPE`, `ENUM_MISMATCH`, `PATTERN_MISMATCH`, `MIN_LENGTH_VIOLATION`, `CONST_VIOLATION`, `SCHEMA_ERROR`
- `validate_payload(contract_name, payload)` — convenience function

### boundary.py — Boundary Enforcement (Principles 1 + 2)

- `validate_outbound(contract_name, payload)` — validate before sending
- `validate_inbound(contract_name, payload)` — validate on receipt
- Raises `BoundaryEnforcementError` on failure with `.to_failure_event()` for telemetry
- Emits structured failure events for observability

### gates.py — Phase Gate Library (Principles 1 + 3 + 4)

Three reusable gate checks, each returning a `GateResult`:

| Gate | What It Checks | Analysis Guide Principle |
| ---- | -------------- | ----------------------- |
| `check_checksum_chain` | Expected vs actual checksums for source, manifest, and CRD | P3: Checksums as circuit breakers |
| `check_mapping_completeness` | Every artifact ID has a task mapping entry | P1: Validate at the boundary |
| `check_gap_parity` | Coverage gaps match parsed features (no drops, no orphans) | P1 + P4: Fail specific |

`GateChecker` — convenience class carrying `trace_id` across multiple gate checks. Properties: `has_blocking_failure`, `blocking_failures`, `all_passed`. Method: `summary()`.

### pipeline_checker.py — Pipeline Integrity Checker (Principles 1-5)

Reads real `onboarding-metadata.json` and `provenance.json` from export output and runs **6 gates**:

| # | Gate | Phase | Principle | Blocking? |
| - | ---- | ----- | --------- | --------- |
| 1 | Structural integrity | `EXPORT_CONTRACT` | P1, P4 | Yes |
| 2 | Checksum chain (recomputed) | `CONTRACT_INTEGRITY` | P3 | Yes |
| 3 | Provenance cross-check | `CONTRACT_INTEGRITY` | P2, P3 | Yes |
| 4 | Mapping completeness | `CONTRACT_INTEGRITY` | P1 | Yes |
| 5 | Gap parity | `INGEST_PARSE_ASSESS` | P1, P4 | Yes |
| 6 | Design calibration | `ARTISAN_DESIGN` | P5 | No (warning) |

`PipelineCheckReport` — aggregated result with `is_healthy`, `to_text()`, `summary()`, `write_json()`.

### three_questions.py — Three Questions Diagnostic (Principle 6)

Implements the structured diagnostic ordering. Stops at the first failing question.

`DiagnosticResult` — structured output with `all_passed`, `first_failure`, `start_here` recommendation.

### pilot.py — PI-101-002 Pilot Runner

Simulates a full 10-span trace (`S1`-`S10`) with gate checks at each boundary. Supports failure injection for testing: `--source-checksum` (tamper), `--drop-feature` (gap parity), `--test-failures` (test failure injection).

`PilotResult` — full trace evidence, serializable to JSON.

### queries.py — Observability Queries

Pre-built TraceQL and LogQL queries for A2A governance:

- `blocked_span_hotspot()` — find all blocked spans grouped by phase
- `gate_failure_rate()` — gate failure count over time
- `handoff_validation_failures()` — boundary enforcement rejections
- `dropped_artifacts()` — gap parity violations
- `finalize_failure_trend()` — finalize-phase failures over time

---

## CLI Commands

All commands are under `contextcore contract`:

```bash
# Validate a JSON payload against an A2A contract schema
contextcore contract a2a-validate TaskSpanContract payload.json
contextcore contract a2a-validate HandoffContract handoff.json --format json

# Run a specific phase gate check
contextcore contract a2a-gate checksum data.json --gate-id PI-101-002-S3-C2 --task-id PI-101-002-S3
contextcore contract a2a-gate mapping data.json --gate-id G1 --task-id T1
contextcore contract a2a-gate gap-parity data.json --gate-id G2 --task-id T2

# Run the PI-101-002 pilot trace
contextcore contract a2a-pilot                              # Happy path
contextcore contract a2a-pilot --source-checksum sha256:BAD # Checksum failure
contextcore contract a2a-pilot --drop-feature gap-latency   # Gap parity failure
contextcore contract a2a-pilot --test-failures 2            # Test failure injection

# Run pipeline integrity checker on real export output (Gate 1)
contextcore contract a2a-check-pipeline out/enrichment-validation
contextcore contract a2a-check-pipeline out/enrichment-validation --fail-on-unhealthy --report report.json

# Run Three Questions diagnostic (Gates 1-3)
contextcore contract a2a-diagnose out/enrichment-validation
contextcore contract a2a-diagnose out/enrichment-validation \
    --ingestion-dir out/plan-ingestion \
    --artisan-dir out/artisan \
    --fail-on-issue
```

---

## Observability

### Grafana Dashboard

`k8s/observability/dashboards/a2a-governance.json` — 8-panel dashboard with:

- Blocked span hotspots by phase
- Gate failure rate over time
- Handoff validation failures
- Dropped artifacts (gap parity violations)
- Finalize failure trend
- Project-scoped template variable

### Semantic Conventions

Extended `docs/agent-semantic-conventions.md` with 8 framework interoperability attribute namespaces:

| Namespace | Purpose |
| --------- | ------- |
| `graph.*` | Graph/workflow execution (LangGraph, AutoGen) |
| `crew.*` | Multi-agent crew orchestration (CrewAI) |
| `pipeline.*` | Pipeline/component execution (Haystack, LlamaIndex) |
| `rag.*` | Retrieval-augmented generation |
| `conversation.*` | Multi-turn conversation state |
| `optimization.*` | Prompt/pipeline optimization (DSPy) |
| `validation.*` | Output validation (Guidance, Outlines, Instructor) |
| `capability.*` | Skill/capability invocation |

---

## Test Coverage

| Test File | Tests | What It Covers |
| --------- | ----- | -------------- |
| `tests/test_a2a_contracts.py` | 50 | Pydantic models, JSON schema validation, boundary enforcement |
| `tests/test_a2a_pilot.py` | 21 | PI-101-002 pilot runner, failure injection, trace evidence |
| `tests/test_a2a_queries.py` | 24 | TraceQL/LogQL queries, dashboard JSON validation |
| `tests/test_pipeline_checker.py` | 34 | Pipeline integrity checker, all 6 gates, real-format fixtures |
| `tests/test_three_questions.py` | 25 | Three Questions diagnostic, stop-at-first-failure, Q1/Q2/Q3 |
| **Total** | **154** | |

---

## Integration Guides

| Guide | Path | Audience |
| ----- | ---- | -------- |
| Universal integration pattern | `docs/integrations/INTEGRATION_PATTERN_GUIDE.md` | Any framework |
| LangGraph-specific | `docs/integrations/LANGGRAPH_PATTERN.md` | LangGraph users |

The universal pattern follows 4 steps:

1. Map framework primitives to ContextCore spans
2. Wrap delegations with `HandoffContract`
3. Emit `GateResult` at phase transitions
4. Add framework-specific lineage attributes

---

## Documentation Index

### Design and Strategy

| Document | Path |
| -------- | ---- |
| A2A Contracts Design (predecessor) | `docs/A2A_CONTRACTS_DESIGN.md` |
| A2A Contracts Project Plan | `docs/A2A_CONTRACTS_PROJECT_PLAN.md` |
| A2A Interoperability Plan (predecessor) | `docs/A2A_INTEROPERABILITY_HIGH_LEVEL_PLAN.md` |
| Agent Communication Protocol (companion) | `docs/agent-communication-protocol.md` |
| PI-101-002 Trace Span Execution Plan | `docs/PI-101-002_TRACE_SPAN_EXECUTION_PLAN.md` |
| Export Pipeline Analysis Guide (foundational) | `docs/EXPORT_PIPELINE_ANALYSIS_GUIDE.md` |
| A2A Truncation Prevention | `docs/A2A_TRUNCATION_PREVENTION.md` |
| Artifact Manifest Contract | `docs/ARTIFACT_MANIFEST_CONTRACT.md` |

### Rollout and Adoption

| Document | Path |
| -------- | ---- |
| Day 1 Kickoff Agenda | `docs/A2A_DAY1_KICKOFF_AGENDA.md` |
| 7-Day Execution Checklist | `docs/A2A_7_DAY_EXECUTION_CHECKLIST.md` |
| 5-Minute Quickstart Guide | `docs/A2A_QUICKSTART.md` |
| v1 Governance Policy | `docs/A2A_V1_GOVERNANCE_POLICY.md` |

### Framework Comparisons and Integrations

| Document | Path |
| -------- | ---- |
| LangChain Governance Extension | `docs/LANGCHAIN_CONTEXTCORE_GOVERNANCE_EXTENSION.md` |
| LangChain vs ContextCore A2A Guide | `docs/LANGCHAIN_VS_CONTEXTCORE_A2A_GUIDE.md` |
| Universal Integration Pattern Guide | `docs/integrations/INTEGRATION_PATTERN_GUIDE.md` |
| LangGraph Integration Pattern | `docs/integrations/LANGGRAPH_PATTERN.md` |
| Framework Comparisons | `docs/framework-comparisons/*.md` |

### Artisan Workflow

| Document | Path |
| -------- | ---- |
| Artisan Workflow Testing Issues | `docs/ARTISAN_WORKFLOW_TESTING_ISSUES.md` |
| Artisan Pipeline Issues (Tasks as Spans) | `docs/ARTISAN_PIPELINE_ISSUES_AND_TASKS_AS_SPANS.md` |

### Schemas

| Schema | Path |
| ------ | ---- |
| TaskSpanContract | `schemas/contracts/task-span-contract.schema.json` |
| HandoffContract | `schemas/contracts/handoff-contract.schema.json` |
| ArtifactIntent | `schemas/contracts/artifact-intent.schema.json` |
| GateResult | `schemas/contracts/gate-result.schema.json` |
| Schema guide | `schemas/contracts/README.md` |

### Implementation

| Module | Path | Purpose |
| ------ | ---- | ------- |
| Models | `src/contextcore/contracts/a2a/models.py` | Pydantic v2 contract models |
| Validator | `src/contextcore/contracts/a2a/validator.py` | JSON schema validation + error envelopes |
| Boundary | `src/contextcore/contracts/a2a/boundary.py` | Ingress/egress enforcement |
| Gates | `src/contextcore/contracts/a2a/gates.py` | Phase gate library |
| Pipeline Checker | `src/contextcore/contracts/a2a/pipeline_checker.py` | Real export output integrity checking |
| Three Questions | `src/contextcore/contracts/a2a/three_questions.py` | Structured diagnostic ordering |
| Pilot | `src/contextcore/contracts/a2a/pilot.py` | PI-101-002 trace runner |
| Queries | `src/contextcore/contracts/a2a/queries.py` | TraceQL/LogQL query builders |
| CLI | `src/contextcore/cli/contract.py` | All A2A CLI commands |
| Dashboard | `k8s/observability/dashboards/a2a-governance.json` | Grafana governance dashboard |
