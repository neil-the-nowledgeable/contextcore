# Export Pipeline Analysis Guide

**File**: `docs/EXPORT_PIPELINE_ANALYSIS_GUIDE.md`

**Description**: A technical reference guide for plan ingestion and artisan workflow developers that explains the 7-step A2A governance-aware flow — ContextCore install init, ContextCore export, A2A pipeline checker (Gate 1), startd8-sdk plan ingestion, A2A diagnostic (Gate 2), contractor execution, and finalize verification (Gate 3) — as a single data flow, then layers defense-in-depth principles on top for issue analysis. Covers what `init` validates and seeds, the four export output files plus enrichment fields, the 5-phase plan ingestion pipeline with complexity-score routing, the 7-phase artisan workflow with design calibration, A2A governance gates and contract types, a symptom-based troubleshooting matrix, and six defense-in-depth principles (boundary validation, adversarial thinking, checksum circuit breakers, backward failure tracing, calibration guards, and the "Three Questions" diagnostic ordering).

---

How `contextcore install init` and `contextcore manifest export` feed the Plan Ingester and the Artisan Workflow — and how to apply defense-in-depth when diagnosing problems across the full 7-step A2A governance-aware pipeline.

**Audience**: Plan ingestion workflow developers, artisan workflow developers, SDK integrators.

**Related capability manifests** (startd8-sdk):

- `startd8.workflow.capabilities.yaml` — workflow capabilities including `plan_ingestion` and `artisan_orchestrator`
- `startd8.sdk.capabilities.yaml` — SDK core capabilities including ContextCore integration
- `startd8.observability.manifest.yaml` — telemetry surface

---

## 1. The Big Picture: Seven Steps, Three Systems, One Data Flow

```text
Step 1                Step 2                  Step 3              Step 4                  Step 5
┌────────────────┐   ┌────────────────┐     ┌────────────────┐  ┌────────────────┐     ┌────────────────┐
│ ContextCore    │──▶│ ContextCore    │──▶  │ A2A Pipeline   │──▶│ Plan Ingestion │──▶  │ A2A Diagnostic │
│ Install Init   │   │ Manifest Export│      │ Checker        │  │ converts+routes│      │ Three Questions│
│                │   │ --emit-        │      │ (Gate 1)       │  │                │      │ (Gate 2)       │
│                │   │ provenance     │      │                │  │                │      │                │
└────────────────┘   └────────────────┘     └────────────────┘  └────────────────┘     └────────────────┘
                                                                                              │
                                                                          ┌───────────────────┘
                                                                          ▼
                                                                    Step 6              Step 7
                                                                   ┌────────────────┐  ┌────────────────┐
                                                                   │ Contractor     │──▶│ A2A Finalize   │
                                                                   │ Execution      │  │ Verification   │
                                                                   │ (Prime/Artisan)│  │ (Gate 3)       │
                                                                   └────────────────┘  └────────────────┘
```

Each step has a well-defined responsibility:

| Step | Command | Responsibility | Analogy |
| ---- | ------- | -------------- | ------- |
| **1. Init** | `contextcore install init` | Verifies installation readiness, emits telemetry, provides entry points | Opening the jobsite and confirming tools are available |
| **2. Export** | `contextcore manifest export --emit-provenance` | Declares *what* artifacts are needed, with enrichment metadata and checksum chain | The architect's blueprint |
| **3. Gate 1** | `contextcore contract a2a-check-pipeline` | Validates export integrity: structural, checksums, provenance, mapping, gaps, calibration (6 checks) | Building inspector checks the blueprint |
| **4. Ingestion** | `startd8 workflow run plan-ingestion` | Converts blueprint into actionable work items and routes by complexity | The general contractor's estimate and crew assignment |
| **5. Gate 2** | `contextcore contract a2a-diagnose` | Three Questions diagnostic: contract complete? faithfully translated? faithfully executed? | Mid-build quality audit |
| **6. Execution** | Prime or Artisan contractor | Structured build with design review, implementation, testing | The specialist crew doing the work |
| **7. Gate 3** | Finalize verification | Per-artifact checksums, provenance chain verification, status rollup | Final inspection |

---

## 2. What `contextcore manifest export` Produces

The export command reads a `.contextcore.yaml` v2 manifest and produces up to **six files**, each serving a distinct downstream consumer:

| # | File | Purpose | When produced | Primary Consumer |
| - | ---- | ------- | ------------- | ---------------- |
| 1 | `{project}-projectcontext.yaml` | Kubernetes CRD — project metadata, business criticality, SLOs, risks | Always | K8s controller, Grafana labels |
| 2 | `{project}-artifact-manifest.yaml` | **The CONTRACT** — specifies every observability artifact needed (dashboards, PrometheusRules, SLOs, Loki rules, ServiceMonitors, runbooks, etc.) with derivation rules showing how business metadata maps to artifact config | Always | Plan Ingester, Artisan seed |
| 3 | `provenance.json` | Audit trail — git context, timestamps, checksums, CLI args, duration | `--emit-provenance` | Integrity verification, A2A provenance-consistency gate |
| 4 | `onboarding-metadata.json` | **Programmatic onboarding** — artifact type schemas, parameter sources, output conventions, coverage gaps, checksums, semantic conventions, enrichment fields, task mappings | Default (use `--no-onboarding` to skip) | Plan Ingester (directly), Artisan context seed enrichment, A2A pipeline checker |
| 5 | `validation-report.json` | Export-time validation diagnostics — schema errors, cross-reference issues, quality gate results | Always | CI/automation, deterministic gating |
| 6 | `export-quality-report.json` | Strict-quality gate summary — field completeness, coverage analysis | `--emit-quality-report` or strict-quality mode | Quality review, pre-ingestion audit |

The critical insight: **ContextCore knows WHAT artifacts are needed** (derived from business criticality, SLOs, alerting requirements) but does **not** know how to create them. The artifact manifest is the contract between the "what" and the "how."

**Additional export flags** (not shown in this guide's examples): `--embed-provenance` (inline provenance in artifact manifest), `--emit-quality-report` / `--strict-quality` (quality gate report), `--deterministic-output` (stable ordering), `--format yaml|json`, `--namespace`, `--existing artifact_id:path` (mark individual artifacts as existing). Run `contextcore manifest export --help` for the full list.

### Key fields in onboarding-metadata.json

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
| `artifact_task_mapping` | Maps artifact ID → plan task ID (e.g., `checkout-api-dashboard` → `PI-019`) | Plan Ingester EMIT, task tracking |

### Enrichment fields in onboarding-metadata.json

These fields are populated by `src/contextcore/utils/onboarding.py` and provide the deeper context that A2A governance gates validate:

| Field | What it tells downstream | Used by |
| ----- | ----------------------- | ------- |
| `derivation_rules` | Per-artifact-type rules mapping business metadata (criticality, SLOs) to artifact parameters (severity, thresholds, intervals) | Artisan DESIGN, A2A design-calibration gate |
| `expected_output_contracts` | Per-artifact-type contracts defining expected depth, max_lines, max_tokens, completeness markers, required fields | Artisan IMPLEMENT/TEST, A2A gap-parity gate |
| `artifact_dependency_graph` | Maps artifact ID → list of dependent artifact IDs (e.g., SLO depends on PrometheusRule) | Plan Ingester PARSE ordering, Artisan PLAN sequencing |
| `resolved_artifact_parameters` | Pre-resolved parameter values per artifact, ready for template substitution | Artisan IMPLEMENT |
| `open_questions` | Unresolved questions from `guidance.questions` that downstream should surface | Plan Ingester ASSESS, contractor design review |
| `file_ownership` | Maps output file path → artifact ID for post-generation validation and ownership tracking | Artisan FINALIZE, CI ownership checks |
| `objectives` | Strategic objectives from `strategy.objectives` for contractor alignment | Artisan DESIGN context |
| `requirements_hints` | Requirement ID → label/acceptance anchors bridge for downstream ingestion | Plan Ingester ASSESS |

### A2A governance integration

The export output is the primary input for A2A governance validation. Two CLI commands validate the export before and after plan ingestion:

| Command | Gate | What it validates | When to run |
| ------- | ---- | ----------------- | ----------- |
| `contextcore contract a2a-check-pipeline <export-dir>` | Gate 1 | 6 checks: structural integrity, checksum chain, provenance consistency, mapping completeness, gap parity, design calibration | After export, before plan ingestion |
| `contextcore contract a2a-diagnose <export-dir>` | Gate 2 | Three Questions: contract complete? faithfully translated? faithfully executed? | After plan ingestion, before contractor execution |

Gate 1 runs 6 checks; checksum-chain uses checksums from `onboarding-metadata.json` (always present). The provenance-consistency gate (1 of 6) is skipped if `provenance.json` is absent — use `--emit-provenance` for full 6/6 gate coverage. Gate 2 requires `export_dir`; `--ingestion-dir` and `--artisan-dir` are optional (questions are skipped without them).

The A2A governance layer uses four contract types at phase boundaries:

| Contract | Purpose | Emitted by |
| -------- | ------- | ---------- |
| `TaskSpanContract` | Task/subtask lifecycle as trace spans | Export (optional `--emit-task-spans`), Plan Ingestion EMIT |
| `ArtifactIntent` | Declares planned artifact work before generation | Plan Ingestion TRANSFORM |
| `GateResult` | Phase boundary check outcomes | Pipeline checker, Three Questions diagnostic |
| `HandoffContract` | Agent-to-agent delegation | Plan Ingestion TRANSFORM (routing decision) |

See `docs/design/contextcore-a2a-comms-design.md` for the full A2A governance architecture and `docs/A2A_V1_GOVERNANCE_POLICY.md` for schema versioning policy.

---

## 3. How Plan Ingestion Consumes the Export

The `plan-ingestion` workflow (`startd8.workflow.builtin.plan_ingestion`) is a **5-phase pipeline** that converts the export output into SDK-native format:

### Phase 1 — PARSE

An LLM extracts features and dependencies from the artifact manifest. Each artifact in the manifest (e.g., `checkout-api-dashboard`, `checkout-api-prometheus-rules`) becomes a candidate feature with its parameters, derivation rules, and type schema drawn from the onboarding metadata.

### Phase 2 — ASSESS

An LLM scores 7 complexity dimensions (0–100) for the set of artifacts. This is where onboarding metadata is critical — it provides:

- `parameter_sources` — where each parameter comes from (manifest field path vs CRD field path)
- `artifact_types` — output conventions, file extensions, example snippets
- `coverage.gaps` — which artifacts are missing and need generation
- `semantic_conventions` — metric names, label conventions for dashboards/rules

### Phase 3 — TRANSFORM (routing decision)

- **Complexity score ≤ 40** → route to **PrimeContractor** (sequential feature-by-feature integration)
- **Complexity score > 40** → route to **Artisan Workflow** (structured 7-phase orchestration with design review)

The `force_route` config can override this. The `artifact_task_mapping` from onboarding metadata maps artifact IDs to task IDs (e.g., `checkout-api-dashboard` → `PI-019`) so downstream work items are traceable.

### Phase 4 — REFINE

Runs N rounds of `ArchitecturalReviewLogWorkflow` against the transformed plan. In dual-document mode, the review checks the plan against the artifact manifest as the requirements spec, producing S-prefix suggestions for the plan and F-prefix suggestions for the feature spec.

### Phase 5 — EMIT

Writes the review config and, optionally, ContextCore task tracking artifacts (epic/story/task state files, NDJSON event logs, tracking manifest) via `emit_task_tracking_artifacts()`. This closes the loop — artifacts that originated as ContextCore metadata are now tracked as ContextCore tasks.

---

## 4. How the Artisan Workflow Consumes the Export

When plan ingestion routes to the artisan path, the `ArtisanContractorWorkflow` (`startd8.workflow.contractor.artisan_orchestrator`) receives the plan as an **enriched context seed**. The export data flows through its **7 phases**:

### Phase 1 — PLAN

Deconstructs the artifact manifest into individual tasks. The `architectural_context` key (derived from manifest goals, constraints, shared modules, dependency clusters) provides domain awareness.

### Phase 2 — SCAFFOLD

Creates project structure. Output conventions from onboarding metadata (`output_path`, `output_ext`) determine where generated files go.

### Phase 3 — DESIGN

This is where the export data has the most impact. The `design_calibration` assigns depth tiers per task based on estimated LOC:

- **Brief** (≤50 LOC): e.g., ServiceMonitor YAML
- **Standard** (51–150 LOC): e.g., PrometheusRule, notification policy
- **Comprehensive** (>150 LOC): e.g., full Grafana dashboard JSON

The artifact manifest's derivation rules (how business criticality maps to alert severity, how SLO thresholds map to recording rules) become the design spec for each artifact.

### Phase 4 — IMPLEMENT

The `ImplementPhaseHandler` wired to `LeadContractorCodeGenerator` reads existing files (60KB cap) and dependency outputs as context. The `parameter_sources` from onboarding metadata tell the generator exactly which manifest or CRD fields to read for each parameter.

### Phase 5 — TEST

Validates generated artifacts.

### Phase 6 — REVIEW

Multi-agent review via the 3-tier cost model (Haiku drafter, Sonnet validator, Opus reviewer).

### Phase 7 — FINALIZE

Produces the final report with sha256 checksums per artifact, per-task status rollup, and cost aggregation. The provenance chain (`source_checksum` from export → onboarding → seed → finalize) enables end-to-end verification.

---

## 5. Troubleshooting Across the Seven Steps

When something goes wrong in artifact generation, trace through these checkpoints:

| Symptom | Check in Init | Check in Export | Check in Gate 1 | Check in Plan Ingester | Check in Gate 2 | Check in Artisan |
| ------- | ------------- | --------------- | --------------- | ---------------------- | --------------- | ---------------- |
| Missing artifact | `contextcore install init` without critical failures | Is it in `coverage.gaps`? | Does mapping-completeness pass? | Did PARSE extract it as a feature? | Q1: contract complete? | Did PLAN include it as a task? |
| Wrong parameters | N/A | Check `derivation_rules` and `parameter_sources` | Does design-calibration pass? | Did ASSESS use the right parameters? | Q2: faithfully translated? | Did DESIGN use the right derivation rule? |
| Stale output | Re-run `init` | Compare `source_checksum` with current manifest | Does checksum-chain pass? | Was the plan from a fresh export? | N/A | Does `enriched_seed_path` point to current export? |
| Routing mismatch | N/A | N/A | N/A | Check complexity score vs threshold (40) | Q2: faithfully translated? | N/A — artisan only runs if routed |
| Checksum failure | N/A | Re-run export with `--emit-provenance` | Run `a2a-check-pipeline` — it reports which checksum broke | Verify onboarding metadata wasn't edited | N/A | Verify design-handoff.json schema |
| Gate failure | N/A | N/A | Read `GateResult` — includes `failed_gate`, `reason`, `next_action` | N/A | Read diagnostic report — stops at first failing question | Check finalize report |
| Coverage below threshold | N/A | Use `--min-coverage`; run `--scan-existing` | Does gap-parity pass? | N/A | N/A | Check `tasks_failed` count |

---

## 6. Defense in Depth: Guarding the Pipeline End-to-End

The 7-step pipeline has a fundamental property: **each step trusts the output and assumptions from the prior step.** A defect in initialization or export can cascade silently through ingestion and into the artisan build. Defense in depth — now enforced by A2A governance gates at steps 3, 5, and 7 — means inserting validation at every boundary so that problems are caught as close to their source as possible, rather than manifesting as mysterious failures at the end.

### Principle 1: Validate at the Boundary, Not Just at the End

Each handoff between steps is a trust boundary. Insert checks at every one:

```text
Init ──[gate 0]──▶ Export ──[gate 1]──▶ Plan Ingestion ──[gate 2]──▶ Artisan ──[gate 3]──▶ Output
```

**Gate 0 — Init validation** (before export begins):

- Run `contextcore install init` to validate installation completeness and critical dependencies.
- **Note**: `init` always exits 0 (advisory mode). For strict gating that fails on incomplete installation, use `contextcore install verify` instead.
- Confirm telemetry export endpoint is correct (`--endpoint`) so installation metrics are flushed to your backend.
- If needed for quick onboarding docs only, use `--skip-verify`, but treat this as a reduced-safety mode.

**Gate 1 — Export output validation** (before plan ingestion begins):

- Run `contextcore manifest export --dry-run` first to preview without writing files.
- Enforce `--min-coverage` to fail early if the manifest is under-specified.
- **Run `contextcore contract a2a-check-pipeline <export-dir>`** to validate 6 structural integrity checks:
  - structural-integrity: all expected files present and parseable
  - checksum-chain: source → artifact manifest → CRD checksums are consistent
  - provenance-consistency: git metadata and timestamps are coherent
  - mapping-completeness: every target has corresponding artifacts
  - gap-parity: coverage gaps match parsed feature count
  - design-calibration: artifact depth tiers match type expectations
- Check that `parameter_sources` reference fields that actually exist and are populated in the manifest. A derivation rule pointing to `manifest.spec.requirements.latencyP99` is useless if that field is empty.

**Gate 2 — Plan ingestion output validation** (before artisan begins):

- **Run `contextcore contract a2a-diagnose <export-dir>`** for the Three Questions diagnostic (stops at first failing question):
  - Q1: Is the contract complete? (artifact manifest has all required artifacts)
  - Q2: Was the contract faithfully translated? (plan features match coverage gaps)
  - Q3: Was the translated plan faithfully executed? (task count matches feature count)
- After ASSESS, inspect the complexity score breakdown. If all 7 dimensions score near zero or near 100, the LLM likely misunderstood the input — the assessment is unreliable.
- After TRANSFORM, verify the routed plan references every artifact from `coverage.gaps`. Any artifact in the gap list that doesn't appear as a feature in the plan was dropped during parsing.
- After REFINE, check that architectural review suggestions were triaged (ACCEPT/REJECT). Untriaged suggestions indicate the review loop didn't converge.
- If `generate_task_tracking` is enabled, verify the NDJSON event log contains a `task.created` event for every expected artifact.

**Gate 3 — Artisan output validation** (before accepting final output):

- After FINALIZE, verify the per-task status rollup. A `partial` or `failed` overall status means some artifacts weren't generated successfully.
- Compare the FINALIZE artifact list against the original `coverage.gaps` from the export. Every gap should now have a corresponding artifact with a sha256 checksum.
- Verify the provenance chain: `source_checksum` from export should match the source checksum recorded in the finalize report. Any mismatch means the manifest changed between export and build.

### Principle 2: Treat Each Piece as Potentially Adversarial

Even though all steps are yours, reason about each handoff as if the upstream step could produce malformed, incomplete, or stale output:

| Boundary | What could go wrong | Defense |
| -------- | ------------------- | ------- |
| Init → Export | Installation baseline is incomplete; telemetry endpoint is wrong; operator skips verification without realizing risk | Run `contextcore install init` without `--skip-verify` in normal operation; fix critical requirement failures before exporting |
| Manifest → Export | Manifest has empty fields, missing targets, or stale version | Pre-flight validation (`_validate_manifest`) catches schema errors; `--min-coverage` catches under-specification |
| Export → Plan Ingestion | Export files are stale (from a previous run), checksums don't match current manifest, onboarding metadata was hand-edited | Compare `source_checksum` against current `.contextcore.yaml` hash before ingesting; reject if stale |
| Plan Ingestion → Artisan | Complexity score routed incorrectly; plan is missing artifacts; task mapping is incomplete | Assert plan feature count ≥ gap count; validate `artifact_task_mapping` covers all gaps; use `force_route` when you know the correct path |
| Artisan → Final Output | Generated artifacts have wrong parameters, missing fields, or don't pass schema validation | Post-generation schema validation per artifact type; cross-reference parameters against `parameter_sources` |

### Principle 3: Use Checksums as Circuit Breakers

The pipeline has a checksum chain: `source_checksum` → `artifact_manifest_checksum` → `project_context_checksum` → finalize artifact checksums. Treat any break in this chain as a **hard stop**:

```text
.contextcore.yaml ──sha256──▶ onboarding-metadata.json (source_checksum)
                              ├── artifact_manifest_checksum
                              └── project_context_checksum
                                        │
                    plan ingestion carries source_checksum forward
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

**Rule**: If `source_checksum` at any stage doesn't match the original, the pipeline is operating on stale data. Re-export before proceeding.

### Principle 4: Fail Loud, Fail Early, Fail Specific

When diagnosing a failure, start from the **output symptom** and trace backward through all seven steps. The most common mistake is assuming the problem is in the step where the symptom appeared:

```text
Symptom in artisan output
  └─ Is the artisan design spec correct?
       └─ Did plan ingestion produce the right plan?
            └─ Did the export produce a complete artifact manifest?
                 └─ Did init verify the environment and endpoint first?
                 └─ Is the source manifest correctly specified?
```

For each stage, check:

1. **Input integrity**: Does the input checksum match what the previous stage wrote?
2. **Completeness**: Are all expected items present? (gap count = feature count = task count)
3. **Freshness**: Is `source_checksum` still valid against the current `.contextcore.yaml`?
4. **Parameter fidelity**: Do parameter values at this stage match the source manifest fields?

### Principle 5: Design Calibration Guards Against Over/Under-Engineering

The artisan workflow's depth tiers (brief/standard/comprehensive) are derived from estimated LOC, but the export's artifact types provide a second signal. Use both to catch miscalibration:

| Artifact Type | Expected Depth | Red Flag |
| ------------- | -------------- | -------- |
| ServiceMonitor | Brief (≤50 LOC) | Calibrated as "comprehensive" — LLM is over-engineering a simple YAML |
| PrometheusRule | Standard (51–150 LOC) | Calibrated as "brief" — likely to produce incomplete alert rules |
| Dashboard (Grafana JSON) | Comprehensive (>150 LOC) | Calibrated as "brief" — will produce a skeleton, not a usable dashboard |
| SLO Definition | Standard | Calibrated as "comprehensive" — over-engineering for what's typically a simple spec |
| Runbook | Standard–Comprehensive | Calibrated as "brief" — runbook will lack incident procedures |

If the design calibration doesn't match the artifact type's expected depth, the `architectural_context` fed from the manifest is likely incomplete or the LLM assessment was inaccurate. Fix the input, don't patch the output.

### Principle 6: The Three Questions for Any Issue

When analyzing any problem in the pipeline, ask these three questions in order:

1. **Is the contract complete?** (Export layer)
   - Does the artifact manifest list every artifact needed?
   - Are all derivation rules populated with real values from the manifest?
   - Does `--scan-existing` correctly detect what's already built?

2. **Was the contract faithfully translated?** (Plan Ingestion layer)
   - Did PARSE extract every artifact as a feature?
   - Did ASSESS produce a reasonable complexity score?
   - Did TRANSFORM route to the right contractor?
   - Did REFINE catch architectural issues before implementation?

3. **Was the translated plan faithfully executed?** (Artisan layer)
   - Did DESIGN use the correct derivation rules and parameter sources?
   - Did IMPLEMENT read the right context files and dependencies?
   - Did TEST/REVIEW catch quality issues?
   - Does FINALIZE report show all tasks succeeded?

If the answer to question 1 is "no," fixing anything in questions 2 or 3 is wasted effort. **Always start from the source.**

---

## 7. The Contract Chain in One Sentence

> `contextcore install init` validates the environment and seeds installation telemetry, the `.contextcore.yaml` manifest declares business intent, `contextcore manifest export --emit-provenance` distills that intent into an artifact contract with enrichment metadata and checksum chain, `contextcore contract a2a-check-pipeline` validates 6 structural integrity gates, the plan ingester parses and routes by complexity, `contextcore contract a2a-diagnose` runs the Three Questions diagnostic, and the contractor workflow executes the structured build — with A2A governance gates, typed contracts (`TaskSpanContract`, `ArtifactIntent`, `GateResult`, `HandoffContract`), and provenance verifiable at every handoff.

---

## 8. Quick Reference: CLI Commands

```bash
# Step 1: initialize installation baseline (recommended first)
contextcore install init
contextcore install init --endpoint localhost:4317  # explicit OTLP endpoint

# Step 2: export with all outputs (--emit-provenance recommended for A2A gates)
contextcore manifest export -p .contextcore.yaml -o ./output --emit-provenance --min-coverage 80
contextcore manifest export -p .contextcore.yaml -o ./output --dry-run  # preview
contextcore manifest export -p .contextcore.yaml -o ./output --task-mapping task-map.json
contextcore manifest export -p .contextcore.yaml -o ./output --scan-existing ./k8s/observability

# Step 3: Gate 1 — A2A pipeline integrity check (6 gates)
contextcore contract a2a-check-pipeline ./output

# Step 4: plan ingestion (startd8-sdk)
startd8 workflow run plan-ingestion --plan_path plan.md --output_dir ./out
startd8 workflow run plan-ingestion --plan_path plan.md --output_dir ./out \
  --generate_task_tracking --project_id my-project

# Step 5: Gate 2 — Three Questions diagnostic
contextcore contract a2a-diagnose ./output --ingestion-dir ./out

# Step 6: contractor execution (these scripts live in startd8-sdk, not ContextCore)
python3 scripts/run_artisan_workflow.py --seed seed.json --output-dir out/ --cost-budget 10
python3 scripts/run_artisan_design_only.py --seed seed.json --output-dir out/  # design review
python3 scripts/run_artisan_implement_only.py --handoff out/design-handoff.json  # from handoff

# Step 7: finalize verification (built into artisan FINALIZE phase)
# Per-artifact checksums, provenance chain, status rollup

# A2A contract validation (standalone)
contextcore contract a2a-validate TaskSpanContract payload.json
contextcore contract a2a-pilot                                    # PI-101-002 simulation
contextcore contract a2a-pilot --source-checksum sha256:BAD       # failure injection
```
