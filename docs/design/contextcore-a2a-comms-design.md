# ContextCore A2A Communications Design

**Status**: Implemented (v1)
**Last updated**: 2026-02-14

---

## Overview

ContextCore's Agent-to-Agent (A2A) governance layer provides contract-first validation, boundary enforcement, phase gates, pipeline integrity checking, and structured diagnostics for the full export pipeline. All agent handoffs, artifact promotions, and phase transitions are governed by typed contracts and quality gates — with observability built in via OpenTelemetry spans.

### Core Principle

> **Keep execution in the framework. Govern only boundaries and evidence in ContextCore.**

Agents and pipelines run their own logic; ContextCore validates contracts at ingress/egress points, enforces gates at phase transitions, and provides a structured diagnostic when something breaks.

### The Contract Chain

> (1) `contextcore install init` validates the environment, (2) the `.contextcore.yaml` manifest declares business intent, (3) `contextcore manifest export` distills that intent into an artifact contract with onboarding metadata, (4) the plan ingester routes by complexity, and (5) the contractor workflow executes the build — with checksums and provenance verifiable at every handoff.

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

The export pipeline is a 7-step data flow across three systems. A2A governance inserts validation at every handoff boundary (steps 3, 5, and 7 are the primary governance gates; an advisory Gate 0 validates installation readiness between Steps 1 and 2):

> **Future alignment note**: Gates are conceptually boundary validations at the *end* of the step they gate, not separate pipeline steps. A future revision will remodel to a 4-step pipeline (Init, Export, Plan Ingestion, Contractor Execution) with gates embedded as step-final validation. The 7-step numbering is retained here for consistency with other documents that reference it.

```text
Step 1          Step 2           Step 3          Step 4            Step 5          Step 6           Step 7
┌──────────┐   ┌──────────┐    ┌──────────┐   ┌──────────────┐  ┌──────────┐   ┌──────────────┐  ┌──────────┐
│ Init     │──▶│ Export   │──▶ │ Gate 1   │──▶│ Plan         │──▶│ Gate 2   │──▶│ Contractor   │──▶│ Gate 3   │──▶ Output
│          │   │ --emit-  │    │ a2a-check│   │ Ingestion    │  │ a2a-     │   │ Execution    │  │ Finalize │
│          │   │ provenance│   │ -pipeline│   │              │  │ diagnose │   │              │  │ Verify   │
└──────────┘   └──────────┘    └──────────┘   └──────────────┘  └──────────┘   └──────────────┘  └──────────┘
 validates      reads manifest,  6 integrity    5 phases:         Three          7 phases:         per-artifact
 install,       writes 4–6 outputs    checks       PARSE → ASSESS → Questions      PLAN → SCAFFOLD → checksums,
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
| **3. Gate 1** | `contextcore contract a2a-check-pipeline` | 6 integrity checks on export output | Building inspector checks the blueprint |
| **4. Ingestion** | `startd8 workflow run plan-ingestion` | Converts blueprint into work items, routes by complexity | General contractor's estimate and crew assignment |
| **5. Gate 2** | `contextcore contract a2a-diagnose` | Three Questions diagnostic (contract complete? translated? executed?) | Mid-build quality audit |
| **6. Execution** | Prime or Artisan contractor | Structured build with design review, implementation, testing | Specialist crew doing the work |
| **7. Gate 3** | Finalize verification | Per-artifact checksums, provenance chain, status rollup | Final inspection |

The critical insight: **ContextCore knows WHAT artifacts are needed** (derived from business criticality, SLOs, alerting requirements) but does **not** know how to create them. The artifact manifest is the contract between the "what" and the "how."

### What Export Produces

The export command reads a `.contextcore.yaml` v2 manifest and produces up to 6 files:

| # | File | Purpose | Primary Consumer |
| - | ---- | ------- | ---------------- |
| 1 | `{project}-projectcontext.yaml` | Kubernetes CRD — project metadata, business criticality, SLOs, risks | K8s controller, Grafana labels |
| 2 | `{project}-artifact-manifest.yaml` | **The CONTRACT** — every observability artifact needed, with derivation rules | Plan Ingester, Artisan seed |
| 3 | `provenance.json` | Audit trail — git context, timestamps, checksums, CLI args | Integrity verification, compliance |
| 4 | `onboarding-metadata.json` | **Programmatic onboarding** — artifact schemas, parameter sources, coverage gaps, checksums | Plan Ingester (directly), Artisan context seed |
| 5 | `validation-report.json` | Export-time validation — checksum chain, coverage %, parameter resolvability | Pipeline checker, CI gates |
| 6 | `export-quality-report.json` | Quality metrics (optional with `--emit-quality-report`) — complexity scores, risk indicators | Quality dashboards, metrics |

The artifact manifest (#2) declares *what* to build; onboarding metadata (#4) provides the machine-readable schemas, checksums, and enrichment data that enable automated validation of the contract at every downstream gate.

### Key Fields in onboarding-metadata.json

This is the file that the pipeline checker and Three Questions diagnostic operate on:

| Field | What it tells downstream | Used by |
| ----- | ----------------------- | ------- |
| `artifact_types` | Output conventions, file extensions, example snippets per type | Artisan SCAFFOLD, IMPLEMENT |
| `parameter_sources` | Which manifest/CRD field each parameter comes from | Available for: Artisan DESIGN, IMPLEMENT (not yet consumed by startd8-sdk) |
| `parameter_schema` | Expected parameter keys per artifact type | Plan Ingester ASSESS, Artisan validation |
| `coverage.gaps` | Which artifacts are missing and need generation | Plan Ingester PARSE, Artisan PLAN |
| `semantic_conventions` | Metric names, label conventions for dashboards/rules | Available for: Artisan DESIGN, IMPLEMENT (not yet consumed by startd8-sdk) |
| `artifact_manifest_checksum` | SHA-256 of the artifact manifest content | Integrity verification at every handoff |
| `project_context_checksum` | SHA-256 of the CRD content | Integrity verification |
| `source_checksum` | SHA-256 of the source `.contextcore.yaml` | Full provenance chain verification |
| `artifact_task_mapping` | Maps artifact ID to plan task ID (e.g., `checkout-api-dashboard` to `PI-019`) | Plan Ingester EMIT, task tracking |
| `design_calibration_hints` | Expected depth/LOC per artifact type | A2A design calibration gate |
| `file_ownership` | Maps output paths to artifact IDs and types | A2A gap parity gate |

### Enrichment Fields in onboarding-metadata.json

These fields are populated by `src/contextcore/utils/onboarding.py` and provide the deeper context that A2A governance gates validate:

| Field | What it tells downstream | Used by |
| ----- | ----------------------- | ------- |
| `derivation_rules` | Per-artifact-type rules mapping business metadata (criticality, SLOs) to artifact parameters (severity, thresholds, intervals) | Artisan DESIGN, A2A design-calibration gate |
| `expected_output_contracts` | Per-artifact-type contracts defining expected depth, max_lines, max_tokens, completeness markers, required fields | Artisan IMPLEMENT/TEST, A2A gap-parity gate |
| `artifact_dependency_graph` | Maps artifact ID to list of dependent artifact IDs (e.g., SLO depends on PrometheusRule) | Plan Ingester PARSE ordering, Artisan PLAN sequencing |
| `resolved_artifact_parameters` | Pre-resolved parameter values per artifact, ready for template substitution | Artisan IMPLEMENT |
| `open_questions` | Unresolved questions from `guidance.questions` that downstream should surface | Plan Ingester ASSESS, contractor design review |
| `objectives` | Strategic objectives from `strategy.objectives` for contractor alignment | Artisan DESIGN context |
| `requirements_hints` | Requirement ID to label/acceptance anchors bridge for downstream ingestion | Plan Ingester ASSESS |

### Plan Ingestion Phases (Step 4)

The plan ingestion workflow converts export output into SDK-native format in 5 phases. Understanding these is essential for interpreting Q2 diagnostic checks:

| Phase | What It Does | A2A Gate Relevance |
| ----- | ------------ | ------------------ |
| **PARSE** | LLM extracts features/dependencies from artifact manifest. Each artifact becomes a candidate feature. | Q2 `parse-coverage` — did every gap become a feature? |
| **ASSESS** | LLM scores 7 complexity dimensions (0-100) using parameter_sources, artifact_types, coverage.gaps | Q2 `assess-complexity-score` — is the score reasonable? |
| **TRANSFORM** | Routes by complexity: score <=40 to PrimeContractor, >40 to Artisan. `force_route` can override. | Q2 `transform-routing` — does route match score? |
| **REFINE** | N rounds of architectural review against artifact manifest as requirements spec | Q2 checks for review output files |
| **EMIT** | Writes review config and optionally ContextCore task tracking artifacts, closing the loop | Verifiable via NDJSON event log |

### Artisan Workflow Phases (Step 6)

When plan ingestion routes to the artisan path, the workflow receives the plan as an enriched context seed. Understanding these phases is essential for interpreting Q3 diagnostic checks:

| Phase | What It Does | A2A Gate Relevance |
| ----- | ------------ | ------------------ |
| **PLAN** | Deconstructs artifact manifest into individual tasks with `architectural_context` | Q3 — task count should match gap count |
| **SCAFFOLD** | Creates project structure using `output_path`/`output_ext` from onboarding metadata | Output conventions drive file layout |
| **DESIGN** | Assigns depth tiers per task (brief/standard/comprehensive) based on estimated LOC | Design calibration gate validates this |
| **IMPLEMENT** | `LeadContractorCodeGenerator` reads existing files + `parameter_sources` from metadata | Q3 `implement-output-files` |
| **TEST** | Validates generated artifacts | Q3 `test-results-exist` |
| **REVIEW** | Multi-agent review via 3-tier cost model (drafter/validator/reviewer, currently mapped to Haiku/Sonnet/Opus) | Review output files |
| **FINALIZE** | Produces final report with per-artifact sha256, status rollup, cost aggregation | Q3 `finalize-all-tasks-succeeded` |

### Gate Placement

Each gate maps to an A2A implementation:

| Gate | Boundary | Implementation | What It Checks |
| ---- | -------- | -------------- | -------------- |
| **Gate 0** | Init -> Export | `contextcore install init` (or `install verify` for strict mode) | Install baseline exists, telemetry endpoint correct |
| **Gate 1** | Export -> Plan Ingestion | `pipeline_checker` (checksum chain, provenance, design calibration) | Checksums match, metadata complete, calibration valid |
| **Gate 2** | Plan Ingestion -> Artisan | `three_questions` Q2, `check_mapping_completeness`, `check_gap_parity` | PARSE coverage, complexity scoring, routing, gap parity |
| **Gate 3** | Artisan -> Output | `three_questions` Q3, finalize report validation | Design fidelity, output files, test results, all tasks succeeded |

*Gate 0 is advisory (`init` always exits 0); Gates 1–3 are the formal blocking/non-blocking pipeline gates.*

---

## Defense-in-Depth Implementation

The Export Pipeline Analysis Guide defines 6 defense-in-depth principles. The 7-step pipeline has a fundamental property: **each step trusts the output and assumptions from the prior step.** A defect in initialization or export can cascade silently through ingestion and into the artisan build. Defense in depth — now enforced by A2A governance gates at steps 3, 5, and 7 — means inserting validation at every boundary so that problems are caught as close to their source as possible.

### Principle 1: Validate at the Boundary -> `boundary.py` + `pipeline_checker.py`

Every handoff between steps is a trust boundary. `validate_outbound()` and `validate_inbound()` enforce schema compliance at each boundary. The pipeline checker runs 6 gates against real export output before downstream consumers touch it.

```text
Init ──[gate 0]──▶ Export ──[gate 1]──▶ Plan Ingestion ──[gate 2]──▶ Artisan ──[gate 3]──▶ Output
         │                    │                    │                       │
   init-validation      structural-integrity  mapping-completeness    finalize-report
                        checksum-chain        gap-parity              output-files
                        provenance-check      design-calibration
```

**Gate 1 detail** (automated by `a2a-check-pipeline`):

- `structural-integrity` — required fields exist and schema prefix is valid
- `checksum-chain` — recompute SHA-256 from files and compare against stored values
- `provenance-consistency` — cross-check `provenance.json` against onboarding metadata
- `mapping-completeness` — every coverage gap has a task mapping entry
- `gap-parity` — coverage gaps match artifact features (no drops, no orphans)
- `design-calibration` — calibration hints cover all artifact types with valid depth tiers (non-blocking)
- `parameter-resolvability` — parameter_sources reference fields that resolve to values (non-blocking)
- `--min-coverage` threshold enforcement — fail if overall coverage is below the specified minimum

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
| Artisan -> Final Output | Wrong parameters, missing fields, don't pass schema validation | Post-generation validation per artifact type; cross-reference against `parameter_sources` (implemented in FINALIZE phase — see Step 7 / Gate 3) |

The `A2AValidator` rejects unknown fields (`additionalProperties: false`), enforces required fields, validates enums, and produces structured `ValidationErrorEnvelope` with `error_code`, `failed_path`, `message`, and `next_action`.

`BoundaryEnforcementError` includes a `.to_failure_event()` method that emits structured telemetry for every rejection. When an OTel span is active, the failure event is automatically attached as a span event — making silent handoff failures impossible in instrumented code paths.

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

Example `next_action` values: `"Re-run export with --emit-provenance to populate provenance.json"`, `"Check .contextcore.yaml spec.requirements.latencyP99 — field is empty but referenced by parameter_sources"`, `"Run contextcore manifest export to regenerate checksums"`.

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
| **GateResult** | Quality/integrity gate outcome | `gate_id`, `phase`, `result` (pass/fail), `severity`, `blocking`, `evidence`, `reason`, `next_action` |

### Phase Enum Coverage

The `Phase` enum in `models.py` maps to the pipeline stages:

| Phase Enum | Pipeline Step | Covers |
| ---------- | ------------- | ------ |
| `INIT_BASELINE` | Step 1 (Init) | `contextcore install init` |
| `EXPORT_CONTRACT` | Step 2 (Export) | `contextcore manifest export` output validation |
| `CONTRACT_INTEGRITY` | Step 3 (Gate 1) | Checksum chain, provenance, mapping |
| `INGEST_PARSE_ASSESS` | Step 4 (PARSE + ASSESS) | Feature extraction, complexity scoring |
| `ROUTING_DECISION` | Step 4 (TRANSFORM) | Complexity-based routing |
| `ARTISAN_DESIGN` | Step 6 (PLAN + SCAFFOLD + DESIGN) | Design calibration, handoff |
| `ARTISAN_IMPLEMENT` | Step 6 (IMPLEMENT) | Code generation |
| `TEST_VALIDATE` | Step 6 (TEST) | Artifact validation |
| `REVIEW_CALIBRATE` | Step 6 (REVIEW) | Multi-agent review |
| `FINALIZE_VERIFY` | Step 7 (FINALIZE) | Status rollup, provenance chain |
| `OTHER` | Any step | Catch-all for custom/experimental phases |

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
- Error codes: `MISSING_REQUIRED_FIELD`, `UNKNOWN_FIELD`, `WRONG_TYPE`, `ENUM_MISMATCH`, `PATTERN_MISMATCH`, `MIN_LENGTH_VIOLATION`, `CONST_VIOLATION`, `VALUE_OUT_OF_RANGE`, `INVALID_FORMAT`, `EMPTY_OBJECT`, `SCHEMA_ERROR`
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

Reads real `onboarding-metadata.json` and `provenance.json` from export output and runs **7 gates** (plus an optional `--min-coverage` threshold check):

| # | Gate | Phase | Principle | Blocking? |
| - | ---- | ----- | --------- | --------- |
| 1 | Structural integrity | `EXPORT_CONTRACT` | P1, P4 | Yes |
| 2 | Checksum chain (recomputed) | `CONTRACT_INTEGRITY` | P3 | Yes |
| 3 | Provenance cross-check | `CONTRACT_INTEGRITY` | P2, P3 | Yes |
| 4 | Mapping completeness | `CONTRACT_INTEGRITY` | P1 | Yes |
| 5 | Gap parity | `INGEST_PARSE_ASSESS` | P1, P4 | Yes |
| 6 | Design calibration | `ARTISAN_DESIGN` | P5 | No (warning) |
| 7 | Parameter resolvability | `EXPORT_CONTRACT` | P1, P2 | No (warning) |

> **Note**: The Phase value on each gate indicates the *domain* the check validates, not the pipeline step where the check executes. All gates run during Gate 1 (`a2a-check-pipeline`), but some carry downstream Phase values because they validate metadata *about* those phases. For example, the gap-parity gate carries `Phase.INGEST_PARSE_ASSESS` because it validates data that plan ingestion will consume; the design-calibration gate carries `Phase.ARTISAN_DESIGN` because it validates hints the artisan workflow will use.

`PipelineCheckReport` — aggregated result with `is_healthy`, `to_text()`, `summary()`, `write_json()`.

### three_questions.py — Three Questions Diagnostic (Principle 6)

Implements the structured diagnostic ordering. Stops at the first failing question.

`DiagnosticResult` — structured output with `all_passed`, `first_failure`, `start_here` recommendation.

### pilot.py — PI-101-002 Pilot Runner

Simulates a full 10-span trace (`S1`-`S10`) with gate checks at each boundary. Supports failure injection for testing: `--source-checksum` (tamper), `--drop-feature` (gap parity), `--test-failures` (test failure injection).

`PilotResult` — full trace evidence, serializable to JSON.

### queries.py — Observability Queries

Pre-built TraceQL and LogQL queries for A2A governance:

**TraceQL (Tempo)**:

- `blocked_span_hotspot()` — blocked spans grouped by phase
- `blocked_spans_with_reason()` — blocked spans with reason and next action
- `gate_failure_rate()` — all failed gate results by severity
- `gate_results_by_phase(phase)` — gate results filtered by phase
- `finalize_outcomes()` — FINALIZE_VERIFY span outcomes
- `trace_by_id(trace_id)` — full trace lookup
- `spans_by_parent(parent_task_id)` — child spans of a parent task

**LogQL (Loki)**:

- `handoff_validation_failures()` — boundary enforcement rejections
- `handoff_failures_by_direction(direction)` — filtered by inbound/outbound
- `dropped_artifacts()` — gap parity violations
- `finalize_failure_trend()` — finalize failure count over time (1h buckets)
- `boundary_enforcement_errors()` — all boundary enforcement rejections

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

`k8s/observability/dashboards/a2a-governance.json` — 8-panel dashboard with project-scoped template variable:

| Panel | Datasource | Answers |
| ----- | ---------- | ------- |
| Blocked Span Hotspot | Tempo | Which phases block execution most often? |
| Gate Failures | Tempo | Which gates are failing and how severe? |
| Blocked Spans — Reason & Next Action | Tempo | What failed, where, why, what next? |
| Finalize Outcomes | Tempo | How often does finalization succeed vs fail? |
| Handoff Validation Failures | Loki | Which handoffs are being rejected and why? |
| Dropped Artifacts (Gap Parity Failures) | Loki | Which artifacts were silently dropped? |
| Finalize Failure Trend | Loki | Is the finalize failure rate improving or worsening? |
| Boundary Enforcement Errors | Loki | How many invalid payloads are caught at boundaries? |

### Semantic Conventions

When external frameworks emit spans through ContextCore, these attribute namespaces ensure framework-specific metadata is captured alongside A2A governance attributes, enabling cross-framework observability queries. Extended `docs/agent-semantic-conventions.md` with 8 framework interoperability attribute namespaces:

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

**Recommended reading order for new integrators**: (1) this document, (2) Export Pipeline Analysis Guide, (3) A2A Quickstart, (4) A2A Gate Requirements, (5) relevant integration pattern.

**Reading paths by role**:
- *New integrator*: This doc → Analysis Guide → Quickstart → Integration Pattern (Universal or LangGraph per framework)
- *Operator*: This doc → Quickstart → 7-Day Checklist → Governance Policy
- *Reviewer/auditor*: This doc → Gate Requirements → Governance Policy → Contracts Design

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

### Extension Requirements (Planned)

| Document | Path | Extension |
| -------- | ---- | --------- |
| Manifest Export Requirements | `docs/design/MANIFEST_EXPORT_REQUIREMENTS.md` | §17 --verify, §18 --emit-tasks |
| A2A Gate Requirements | `docs/design/A2A_GATE_REQUIREMENTS.md` | Gate 1/2 behavioral spec |
| Export Task Tracking Requirements | `docs/plans/EXPORT_TASK_TRACKING_REQUIREMENTS.md` | Extension 2 |
| Agent Insights CLI Requirements | `docs/design/AGENT_INSIGHTS_CLI_REQUIREMENTS.md` | Extension 3 |
| Contract Drift Detection Requirements | `docs/design/CONTRACT_DRIFT_DETECTION_REQUIREMENTS.md` | Extension 4 |
| Status Report Requirements | `docs/design/STATUS_REPORT_REQUIREMENTS.md` | Extension 5 |
| Weaver Registry Requirements | `docs/plans/WEAVER_REGISTRY_REQUIREMENTS.md` | Extension 6 |

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

---

## Planned Extensions

The following extensions are planned, ordered by value-to-effort ratio. Each builds directly on the implemented A2A governance layer and pipeline infrastructure documented above.

### Extension 1: Export `--verify` Flag

**Status**: Planned (roadmap item `pipeline.governance_gates`, timeline: Feb 2026)
**Effort**: Small (1–2 hours)
**Requirements**: [MANIFEST_EXPORT_REQUIREMENTS.md](MANIFEST_EXPORT_REQUIREMENTS.md) §17

Adds a `--verify` flag to `contextcore manifest export` that automatically runs Gate 1 (`a2a-check-pipeline`) on its own output after writing files. Chains steps 2 and 3 of the 7-step pipeline into a single invocation. Fails with non-zero exit if any blocking gate fails.

**Implementation surface**: ~30 lines in `src/contextcore/cli/manifest.py` — import `PipelineChecker`, add flag, call `checker.run()` after file write.

### Extension 2: Export Task Tracking (`--emit-tasks`)

**Status**: Planned (full requirements complete)
**Effort**: Medium (3–5 days, 4 phases)
**Requirements**: [EXPORT_TASK_TRACKING_REQUIREMENTS.md](../plans/EXPORT_TASK_TRACKING_REQUIREMENTS.md) (28 requirements, 8 open questions)

Adds `--emit-tasks` flag to `manifest export` that emits OTel task spans for each artifact in `coverage.gaps` before downstream execution begins. Creates epic → story → task span hierarchy using existing `TaskTracker`, records `task_trace_id` in `onboarding-metadata.json` for downstream correlation.

**Key integration**: Task spans use `TaskSpanContract` and `ArtifactIntent` models from the A2A governance layer. Gate results can be attached as events on the relevant task spans via `task_trace_id`.

### Extension 3: Agent Insights CLI

**Status**: Planned (roadmap item `visibility.agent_insights` — 1/2 phases done)
**Effort**: Small (1–2 days)
**Requirements**: [AGENT_INSIGHTS_CLI_REQUIREMENTS.md](AGENT_INSIGHTS_CLI_REQUIREMENTS.md)

Adds `contextcore insight list` and `contextcore insight search` commands wrapping the existing `InsightQuerier` from `src/contextcore/agent/insights.py`. Completes the agent visibility story: dashboard (done) + CLI (this extension).

### Extension 4: Contract Drift Detection

**Status**: Planned (stub exists: `contract check` CLI command references `ContractDriftDetector` that doesn't exist)
**Effort**: Medium (2–3 days)
**Requirements**: [CONTRACT_DRIFT_DETECTION_REQUIREMENTS.md](CONTRACT_DRIFT_DETECTION_REQUIREMENTS.md)

Implements `ContractDriftDetector` to detect when actual output schemas (onboarding-metadata.json structure, provenance.json structure) drift from declared A2A contract schemas. Completes the existing `contract check` command in `src/contextcore/cli/contract.py`.

**Distinction from boundary enforcement**: `boundary.py` catches runtime violations (wrong type, missing field on a specific payload). Drift detection catches structural evolution over time (field added to output but not to schema, enum value in code but not in contract).

### Extension 5: Status Compilation Elimination

**Status**: Planned (roadmap item `time.status_compilation_eliminated`, high priority, Feb 2026)
**Effort**: Medium (3–5 days, 2 phases)
**Requirements**: [STATUS_REPORT_REQUIREMENTS.md](STATUS_REPORT_REQUIREMENTS.md)

Auto-generates project status reports from existing pipeline telemetry. Phase (a): status aggregation queries that roll up gate results, artifact progress, and blocked spans into a structured summary. Phase (b): report generation that produces human-readable status from aggregated data.

**Dogfooding use case**: ContextCore's own telemetry becomes its status report — "ContextCore manages ContextCore."

### Extension 6: Weaver Semantic Convention Registry

**Status**: Planned (Phase 1 not started)
**Effort**: Medium-large (5–7 days, 3 phases)
**Requirements**: [WEAVER_REGISTRY_REQUIREMENTS.md](../plans/WEAVER_REGISTRY_REQUIREMENTS.md) (427 lines, 13 sections)

Formalizes ~185 semantic convention attributes across 17+ namespaces as an OTel Weaver-compatible registry. Addresses attribute name drift between Python enums, JSON schemas, and prose documentation. Enables CI validation (`weaver registry check`) and eventually automated doc generation.

### Extension Dependency Graph

```text
  [1. --verify flag] ──→ [2. --emit-tasks]
         │                       │
         └──→ [3. Insights CLI]  └──→ [5. Status Reports]
                    │
                    └──→ [4. Drift Detection]
                                        └──→ [6. Weaver Registry]
```

### Recommended Execution Order

- **Week 1**: Extensions 1 + 3 (small, close obvious gaps)
- **Week 2–3**: Extension 2 (export task tracking — foundational for status reports)
- **Week 3–4**: Extensions 4 + 5 (drift detection + status compilation)
- **Month 2**: Extension 6 (Weaver registry — requires cross-repo coordination)

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix implements the **Convergent Review Protocol (CRP)** — an iterative, domain-aware review process that converges toward full coverage. It is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-S{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R1-S1 | Fix Phase Enum table step numbering to match 7-step pipeline diagram | R1 Claude (Cursor) | Remapped: `INGEST_PARSE_ASSESS` → Step 4, `ROUTING_DECISION` → Step 4, `ARTISAN_*` → Step 6, `FINALIZE_VERIFY` → Step 7, `CONTRACT_INTEGRITY` → Step 3 (Gate 1) | 2026-02-14 |
| R1-S3 | Add note clarifying Phase semantics on GateResult (domain vs execution point) | R1 Claude (Cursor) | Added blockquote note after pipeline checker gates table | 2026-02-14 |
| R1-S4 | Clarify relationship between artifact-manifest.yaml and onboarding-metadata.json | R1 Claude (Cursor) | Added clarifying sentence after "What Export Produces" table | 2026-02-14 |
| R1-S6 | Add missing enrichment fields table for onboarding-metadata.json | R1 Claude (Cursor) | Added "Enrichment Fields in onboarding-metadata.json" section with 7 fields mirroring Analysis Guide | 2026-02-14 |
| R1-S7 | Add "not yet consumed" caveat on parameter_sources and semantic_conventions | R1 Claude (Cursor) | Updated "Used by" column to "Available for: ... (not yet consumed by startd8-sdk)" | 2026-02-14 |
| R1-S8 | Add concrete next_action examples after GateResult field list | R1 Claude (Cursor) | Added 3 example values inline after the `next_action` bullet | 2026-02-14 |
| R1-S10 | Add cross-reference on Artisan->Final Output defense row | R1 Claude (Cursor) | Added "(implemented in FINALIZE phase — see Step 7 / Gate 3)" parenthetical | 2026-02-14 |
| R1-S11 | Abstract Anthropic model names in REVIEW phase | R1 Claude (Cursor) | Changed to "drafter/validator/reviewer, currently mapped to Haiku/Sonnet/Opus" | 2026-02-14 |
| R1-S12 | Add intro sentence for semantic conventions namespace table | R1 Claude (Cursor) | Added context sentence about cross-framework observability | 2026-02-14 |
| R1-S14 | Fix pipeline_checker.py run() docstring to list all 6 gates | R1 Claude (Cursor) | Added gate #6 (design calibration) to docstring comment | 2026-02-14 |
| R1-S2 | Acknowledge Gate 0 in intro text and Gate Placement table | R1 Claude (Cursor) | Updated intro to mention advisory Gate 0; added italic note below Gate Placement table; added future-alignment note for 7-step→4-step remodel | 2026-02-14 |
| R1-S5 | Reformat "Contract Chain in One Sentence" as numbered sequence | R1 Claude (Cursor) | Reformatted as 5-part numbered inline list; trimmed clause-internal detail; renamed heading to "The Contract Chain" | 2026-02-14 |
| R1-S13 | Add reading-order guidance to Documentation Index | R1 Claude (Cursor) | Added one-line recommended order for new integrators plus 3 role-based reading paths (integrator, operator, reviewer/auditor) | 2026-02-14 |
| R2-S1 | Fix Gate 0 Implementation column (was pipeline_checker, should be install init) | R2 Claude (Cursor) | Changed to `contextcore install init` (or `install verify` for strict mode); pipeline_checker runs at Gate 1 on export output | 2026-02-14 |
| R2-S2 | Fix diagram "writes 4 outputs" to align with "up to 6 files" | R2 Claude (Cursor) | Changed to "writes 4–6 outputs" in pipeline diagram | 2026-02-14 |
| R2-S3 | Add reason, next_action to GateResult Key Fields in Contract Types table | R2 Claude (Cursor) | Added `reason`, `next_action` to GateResult row | 2026-02-14 |
| R2-S4 | Disambiguate "Integration Pattern" in reading paths | R2 Claude (Cursor) | Added "(Universal or LangGraph per framework)" to integrator path | 2026-02-14 |
| R3-S1 | Correct Step 3 description from "6 structural integrity checks" to "6 integrity checks" | R3 Claude (Cursor) | Updated Step 3 responsibility wording to avoid over-scoping structural-integrity to all Gate 1 checks | 2026-02-14 |
| R3-S2 | Align Principle 1 boundary diagram with Gate 0 ownership model | R3 Claude (Cursor) | Relabeled Gate 0 annotation to `init-validation`; moved `structural-integrity` under Gate 1 with checksum/provenance alignment | 2026-02-14 |
| R3-S3 | Improve readability of Export/Gate 1 explanatory row in main ASCII diagram | R3 Claude (Cursor) | Added spacing so `writes 4–6 outputs` and `checks` read as separate columns | 2026-02-14 |

---

#### Round 4 (2026-02-14) — Reviewer: Claude (Cursor agent)

**Review scope**: Full document re-read after Round 3 edits. Checked for precision in gate details and CLI examples.

**Methodology**: Compared "Gate 1 detail" text against the `pipeline_checker.py` implementation and the foundational Analysis Guide. Checked CLI example paths for general applicability.

##### Precision / Completeness

| ID | Severity | Section | Suggestion | Rationale |
|----|----------|---------|------------|-----------|
| R4-S1 | Medium | Gate 1 detail (line 173) | **Gate 1 detail list is incomplete and imprecise.** It lists 3 items (verify checksums, check parameter sources, enforce min-coverage) but the pipeline checker actually runs 6 specific gates. The current list mixes a gate (checksums) with an export option (min-coverage) and omits the other 4 gates (structural-integrity, provenance-consistency, mapping-completeness, gap-parity). **Fix**: Replace the bullet list with the actual 6 gates: `structural-integrity`, `checksum-chain`, `provenance-consistency`, `mapping-completeness`, `gap-parity`, `design-calibration`. | The document claims to validate "6 integrity checks" (per R3-S1) but then lists 3 random items. Listing the actual 6 gates provides the correct contract definition for Gate 1. |

##### Clarity / Consistency

| ID | Severity | Section | Suggestion | Rationale |
|----|----------|---------|------------|-----------|
| R4-S2 | Low | CLI Commands (lines 449-454) | **Example paths use `out/enrichment-validation` which is a specific test fixture name.** Standard export output paths are usually user-defined (e.g. `out/`, `output/`, or `out/export`). Using a test fixture name like `enrichment-validation` in reference documentation might confuse users into thinking that specific directory name is required or standard. **Fix**: Change `out/enrichment-validation` to `out/export` or simply `out/` in the CLI examples. | Makes the examples more generic and applicable to real-world usage. |

**No endorsements** (first pass of Round 4).

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R1-S9 | Add schema versioning/migration strategy paragraph | R1 Claude (Cursor) | No external users yet; v2 doesn't exist; governance policy doc exists but cross-referencing it here adds no value until there's an audience or a v2 to migrate to. Revisit when v2 is introduced. | 2026-02-14 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Round 1 (2026-02-14) — Reviewer: Claude (Cursor agent)

**Review scope**: Full document end-to-end, cross-referenced against `docs/EXPORT_PIPELINE_ANALYSIS_GUIDE.md` (foundational reference) and `src/contextcore/contracts/a2a/` implementation code (models.py, pipeline_checker.py, three_questions.py).

**Methodology**: Read main document, read foundational reference, read implementation source. Checked every table, diagram, and cross-reference for internal consistency, consistency with the Analysis Guide, and consistency with the code. Checked for omissions, ambiguity, and areas where a new reader would get confused.

##### Correctness

| ID | Severity | Section | Suggestion | Rationale |
|----|----------|---------|------------|-----------|
| R1-S1 | High | Phase Enum Coverage (table, lines 300–314) | **Step numbering in the Phase Enum table is inconsistent with the 7-step pipeline diagram.** The table says `INGEST_PARSE_ASSESS` is "Step 3" and all `ARTISAN_*` through `FINALIZE_VERIFY` are "Step 4", but the pipeline diagram (lines 38–51) and step responsibility table (lines 55–63) clearly label Plan Ingestion as Step 4, Contractor Execution as Step 6, and Finalize as Step 7. The Phase Enum table appears to use a collapsed 4-step numbering from a predecessor document. **Fix**: Remap to 7-step numbering: `INGEST_PARSE_ASSESS` → "Step 4 (PARSE + ASSESS)", `ROUTING_DECISION` → "Step 4 (TRANSFORM)", `ARTISAN_DESIGN` → "Step 6 (PLAN + SCAFFOLD + DESIGN)", `ARTISAN_IMPLEMENT` → "Step 6 (IMPLEMENT)", `TEST_VALIDATE` → "Step 6 (TEST)", `REVIEW_CALIBRATE` → "Step 6 (REVIEW)", `FINALIZE_VERIFY` → "Step 7 (FINALIZE)". | A reader following the 7-step diagram will be confused when the Phase Enum table uses different step numbers for the same stages. This is the most likely source of misunderstanding for a new integrator. |
| R1-S2 | Medium | Pipeline Context diagram (lines 38–51) and intro paragraph (line 36) | **Gate 0 is absent from the pipeline diagram and intro text, but present in the Gate Placement table (line 130).** The intro says "steps 3, 5, and 7 are governance gates" (3 gates), and the pipeline diagram only shows Gates 1–3. But the Gate Placement table lists Gate 0 (Init → Export). The Principle 1 boundary diagram (line 146) also shows `[gate 0]`. **Fix**: Either add Gate 0 to the main pipeline diagram (e.g., between Step 1 and Step 2), or add a note to the Gate Placement table clarifying that Gate 0 is an implicit/advisory pre-check rather than a formal pipeline gate, and update the intro sentence accordingly. | Two readers could reach contradictory conclusions about how many gates exist (3 vs 4). |

##### Clarity

| ID | Severity | Section | Suggestion | Rationale |
|----|----------|---------|------------|-----------|
| R1-S3 | High | Pipeline Checker gates table (lines 368–377) | **Clarify that the Phase value on a GateResult indicates the domain the check relates to, not the pipeline step where it executes.** The pipeline checker runs all 6 gates at Gate 1 time (Step 3, `a2a-check-pipeline`), but gates #5 and #6 carry Phase values `INGEST_PARSE_ASSESS` and `ARTISAN_DESIGN` respectively. This is because they validate metadata *about* those downstream phases (gap parity for ingestion, calibration hints for artisan design), even though the check itself runs during Gate 1. Without this explanation, a reader will ask: "Why does the Gate 1 pipeline checker run checks tagged as INGEST_PARSE_ASSESS?" **Fix**: Add a note below the table: "Note: The Phase value on each gate indicates the domain the check validates, not the pipeline step where the check executes. For example, the gap-parity gate runs during Gate 1 but carries `Phase.INGEST_PARSE_ASSESS` because it validates data that plan ingestion will consume." | Confirmed in code: `pipeline_checker.py` line 459 uses `Phase.INGEST_PARSE_ASSESS` for gap-parity, line 688/702 uses `Phase.ARTISAN_DESIGN` for design-calibration. Both run within the `PipelineChecker.run()` method which is invoked at Gate 1. |
| R1-S4 | Medium | What Export Produces (lines 69–78) | **Clarify the relationship between artifact-manifest.yaml (#2) and onboarding-metadata.json (#4).** Both list "Plan Ingester" and "Artisan" as primary consumers. A reader may wonder: are these redundant? The artifact manifest is the *contract* (what artifacts are needed, with derivation rules), while onboarding metadata is the *programmatic supplement* (schemas, parameter sources, checksums, coverage analysis) that enables automated validation and enrichment of the contract. **Fix**: Add a sentence after the table: "The artifact manifest (#2) declares *what* to build; onboarding metadata (#4) provides the machine-readable schemas, checksums, and enrichment data that enable automated validation of the contract at every downstream gate." | The Analysis Guide handles this better by describing onboarding-metadata.json's enrichment fields in a separate table (Section 2, "Enrichment fields"), making the layered relationship clearer. |
| R1-S5 | Low | The Contract Chain in One Sentence (lines 19–21) | **The "one sentence" is a 60+ word run-on that is difficult to parse in a single reading.** Consider reformatting as a numbered sequence or using em-dashes/semicolons to create clearer clause boundaries. The Analysis Guide (Section 7) has the same sentence with slightly more detail and the same readability issue. **Fix**: Either break into a numbered inline list ("`(1) contextcore install init validates..., (2) the .contextcore.yaml manifest declares..., (3) contextcore manifest export distills...`") or keep as-is but add a "read this after the pipeline diagram" note, since the sentence is most useful as a summary *after* understanding the pipeline, not before. | This is in the document header (Overview section) where a reader has zero context yet. The sentence front-loads the entire pipeline flow before the reader has seen the diagram. |

##### Omissions

| ID | Severity | Section | Suggestion | Rationale |
|----|----------|---------|------------|-----------|
| R1-S6 | High | Key Fields in onboarding-metadata.json (lines 82–97) | **The table is missing 7 enrichment fields documented in the Analysis Guide.** The Analysis Guide (Section 2, "Enrichment fields") lists: `derivation_rules`, `expected_output_contracts`, `artifact_dependency_graph`, `resolved_artifact_parameters`, `open_questions`, `objectives`, `requirements_hints`. These fields are populated by `src/contextcore/utils/onboarding.py` and are consumed by A2A gates (design-calibration, gap-parity) and downstream phases. **Fix**: Add a second table titled "Enrichment Fields in onboarding-metadata.json" mirroring the Analysis Guide's structure, or merge the missing fields into the existing table with a note that they are enrichment-phase additions. | A reader relying only on this design document will miss fields that the pipeline checker and artisan workflow actually use. The `derivation_rules` and `expected_output_contracts` fields are particularly important since they feed the design calibration gate (Principle 5). |
| R1-S7 | Medium | Key Fields table, `parameter_sources` and `semantic_conventions` rows | **Missing "not yet consumed" caveat.** The Analysis Guide notes these fields are "Available for: Artisan DESIGN, IMPLEMENT (not yet consumed — see startd8-sdk code fix plan)". This design document states flatly that they are "Used by: Artisan DESIGN, IMPLEMENT" without the implementation-status caveat. **Fix**: Add "(available, not yet consumed by startd8-sdk)" to the "Used by" column for these two rows, consistent with the Analysis Guide. | An integrator reading this doc will expect startd8-sdk to already consume these fields and be confused when it doesn't. |
| R1-S8 | Medium | GateResult fields (line 225–231) | **No concrete examples of `next_action` values.** The document explains that every `GateResult` includes a `next_action` field "what the operator should do to fix it" but never shows an example. **Fix**: Add 2–3 inline examples after the GateResult field list, e.g.: "`next_action` examples: `'Re-run export with --emit-provenance to populate provenance.json'`, `'Check .contextcore.yaml spec.requirements.latencyP99 — field is empty but referenced by parameter_sources'`, `'Run contextcore manifest export to regenerate checksums'`." | The `next_action` field is a key differentiator of this governance system (machine-readable remediation). Showing examples demonstrates its value and helps integrators understand the expected format. |
| R1-S9 | Low | Contract Types / models.py section (lines 287–314) | **Missing schema versioning/migration strategy.** The document notes `schema_version = "v1"` but doesn't describe what happens when v2 contracts are introduced. How will backward compatibility work? Will validators accept both v1 and v2? Will the Phase enum be extended or replaced? **Fix**: Add a brief paragraph: "Schema versioning: All v1 contracts enforce `schema_version: 'v1'`. When v2 contracts are introduced, validators will accept payloads matching any supported version. See `docs/A2A_V1_GOVERNANCE_POLICY.md` for the version lifecycle policy." (If such a policy exists — if not, note this as a gap.) | For a design document with "v1" in the contract types section header, the absence of forward-looking versioning guidance is a notable omission. |
| R1-S10 | Low | Defense-in-Depth Principle 2, "Artisan → Final Output" row (line 181) | **Post-generation validation is described as a defense but not detailed anywhere else in the document.** The table says "Post-generation validation per artifact type; cross-reference parameters against `parameter_sources`" but no section explains what this validation entails, which module implements it, or how it integrates with Gate 3. **Fix**: Either add a brief note cross-referencing the artisan FINALIZE phase description, or add a parenthetical "(implemented in FINALIZE phase — see Step 6 / Gate 3)" to the defense column. | A reader tracing the defense-in-depth chain will hit a dead end at this row. |

##### Consistency / Polish

| ID | Severity | Section | Suggestion | Rationale |
|----|----------|---------|------------|-----------|
| R1-S11 | Low | Artisan Workflow REVIEW phase (line 121) | **Anthropic model names (Haiku, Sonnet, Opus) are implementation-specific and may become stale.** The Analysis Guide uses the same phrasing (Section 4, Phase 6). **Fix**: Use abstract tier names with model names in parentheses: "3-tier cost model (drafter/validator/reviewer, currently mapped to Haiku/Sonnet/Opus)". This makes the architectural pattern (tiered cost model) primary and the model binding secondary. | Model names and mappings change; the tiered review pattern is the durable concept. |
| R1-S12 | Low | Observability / Semantic Conventions (lines 452–465) | **The 8 framework interoperability attribute namespaces table's relevance to A2A governance is unclear.** These namespaces (`graph.*`, `crew.*`, `pipeline.*`, etc.) describe how external frameworks map to OTel attributes, but the connection to A2A contract validation, gate checks, or pipeline integrity is not explained. **Fix**: Add a one-sentence introduction: "When external frameworks emit spans through ContextCore, these attribute namespaces ensure framework-specific metadata is captured alongside A2A governance attributes, enabling cross-framework observability queries." | Without context, this table reads as a tangential inclusion rather than a deliberate part of the A2A observability story. |
| R1-S13 | Low | Documentation Index (lines 497–561) | **The index is a flat list without reading-order guidance.** The "Document Relationships" table at the top of the document (lines 24–31) does this well for the core 5 documents, but the 30+ documents in the Documentation Index have no suggested reading path. **Fix**: Add a one-line note at the top of the Documentation Index: "Recommended reading order for new integrators: (1) this document, (2) Export Pipeline Analysis Guide, (3) A2A Quickstart, (4) A2A Gate Requirements, (5) relevant integration pattern." | A new integrator arriving at this section faces 30+ links with no prioritization signal. |
| R1-S14 | Low | Pipeline checker docstring in code | **Minor code-doc inconsistency**: The `run()` method docstring in `pipeline_checker.py` (line 739–749) lists only 5 gates in the "Gate execution order" comment but the code runs 6 (design-calibration is gate #6). Not a document issue per se, but a code comment that a reader cross-referencing will notice. **Fix**: Update the `run()` docstring to list all 6 gates. | Noted here since the design document is the reference and the code should match it. |

**No endorsements** (this is the first review round).

---

#### Round 2 (2026-02-14) — Reviewer: Claude (Cursor agent)

**Review scope**: Full document re-read after Round 1 edits. Cross-referenced against Appendix A/B (no re-suggestions), `docs/EXPORT_PIPELINE_ANALYSIS_GUIDE.md`, `src/contextcore/contracts/a2a/models.py`, `schemas/contracts/gate-result.schema.json`.

**Methodology**: Scanned for correctness, internal consistency, and alignment with foundational docs and implementation. Focused on issues not addressed in Round 1.

##### Correctness

| ID | Severity | Section | Suggestion | Rationale |
|----|----------|---------|------------|-----------|
| R2-S1 | High | Gate Placement table (line 148) | **Gate 0 Implementation column is incorrect.** The table says "Implementation: `pipeline_checker` structural integrity gate" for Gate 0 (Init -> Export). But the pipeline_checker runs on export output — it is invoked at Gate 1, not between Init and Export. The Export Pipeline Analysis Guide (Section 6, Gate 0) states: "Run `contextcore install init` to validate installation completeness" and "use `contextcore install verify` instead" for strict gating. **Fix**: Change Gate 0 Implementation to `contextcore install init` (or `install verify` for strict mode). The "structural integrity" label under gate 0 in the Principle 1 diagram refers to the *type* of check (installation baseline), not the pipeline_checker module. | A reader will incorrectly assume pipeline_checker runs at Gate 0. The pipeline_checker's structural-integrity gate is gate #1 of its 6 gates, and it runs at Gate 1 time on export output. |
| R2-S2 | Medium | Pipeline diagram (line 48) | **Diagram says "writes 4 outputs" but export produces up to 6 files.** The "What Export Produces" table (line 71) and Export Pipeline Analysis Guide both state "up to 6 files." A prior doc-code alignment fix updated the table from "4" to "6" but the ASCII diagram was not updated. **Fix**: Change "writes 4 outputs" to "writes 4–6 outputs" or "writes 6 outputs" to align with the table. | Inconsistency between diagram and table; readers may assume only 4 files are produced. |

##### Completeness

| ID | Severity | Section | Suggestion | Rationale |
|----|----------|---------|------------|-----------|
| R2-S3 | Low | Contract Types table, GateResult row (line 314) | **GateResult Key Fields omits `reason` and `next_action`.** The table lists `gate_id`, `phase`, `result`, `severity`, `blocking`, `evidence`. The `gate-result.schema.json` and `models.py` both include `reason` and `next_action`; the governance policy requires them for gate results. Principle 4 (line 247) documents `next_action` separately, but the Contract Types table should list all key fields for completeness. **Fix**: Add `reason`, `next_action` to the GateResult Key Fields: `gate_id`, `phase`, `result`, `severity`, `blocking`, `evidence`, `reason`, `next_action`. | The Contract Types table is the quick-reference for each contract; omitting fields that Principle 4 and the governance policy emphasize creates a gap. |

##### Clarity / Consistency

| ID | Severity | Section | Suggestion | Rationale |
|----|----------|---------|------------|-----------|
| R2-S4 | Low | Documentation Index (lines 522–528) | **Reading paths use shorthand names that don't match the table.** "Analysis Guide" and "Quickstart" are clear; "Integration Pattern" could mean Universal Integration Pattern Guide or LangGraph Pattern. "Governance Policy" maps to "v1 Governance Policy" in the table. **Fix**: Add parenthetical disambiguation for "Integration Pattern" in the integrator path: "Integration Pattern (Universal or LangGraph per framework)." Or add a note: "Document names above are shorthand; see tables below for full paths." | Minor — most readers will infer correctly, but explicit mapping reduces ambiguity. |

**No endorsements** (first pass of Round 2).

---

#### Round 3 (2026-02-14) — Reviewer: Claude (Cursor agent)

**Review scope**: Full document re-read after Round 2 application. Verified against Appendix A/B to avoid re-suggesting applied/rejected items.

**Methodology**: Targeted consistency pass for terminology precision and diagram/table alignment after recent edits.

##### Correctness / Precision

| ID | Severity | Section | Suggestion | Rationale |
|----|----------|---------|------------|-----------|
| R3-S1 | Medium | Step responsibility table, Step 3 row | **Step 3 description says \"6 structural integrity checks\" but Gate 1 runs 6 *integrity* checks, only one of which is structural-integrity.** **Fix**: Change to \"6 integrity checks on export output\" (or list all 6 gate names inline/footnote). | Current wording over-scopes \"structural integrity\" to all checks (checksum, provenance, mapping, gap parity, design calibration are not structural-integrity checks). |

##### Clarity / Internal Consistency

| ID | Severity | Section | Suggestion | Rationale |
|----|----------|---------|------------|-----------|
| R3-S2 | Medium | Principle 1 boundary diagram | **Boundary diagram now conflicts with Gate 0 implementation change from R2-S1.** Gate 0 is currently implemented via `install init`, but the diagram labels Gate 0 as `structural-integrity` and places checksum/provenance under Gate 1. This can imply pipeline_checker-owned structural-integrity is Gate 0. **Fix**: Relabel Gate 0 annotation to `install-baseline` (or `init-validation`) and keep `structural-integrity` under Gate 1 with checksum/provenance/mapping/gap-parity/calibration. | After R2-S1, Gate 0 is explicitly init validation. Diagram labels should reflect the same ownership model. |
| R3-S3 | Low | Main 7-step ASCII diagram, explanatory rows under boxes | **Minor readability regression in Export/Gate 1 row after R2-S2 edit (`writes 4–6 outputs  checks`).** **Fix**: Increase spacing or split onto an additional explanatory line so `writes 4–6 outputs` and `checks` read as distinct columns without visual collision. | Not functionally wrong, but the current spacing makes Export and Gate 1 descriptors run together when scanned quickly. |

**No endorsements** (first pass of Round 3).
