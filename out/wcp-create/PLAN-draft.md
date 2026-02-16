# PLAN Draft: Workflow Context Propagation

## Overview

During Artisan workflow runs PI-006 through PI-013, domain classification silently failed to propagate through downstream phases. All 12 tasks defaulted to `domain: "unknown"`, disabling domain-specific prompt constraints, validators, and token budgets. The system produced output without errors, but code quality suffered — a **silent degradation** pattern.

The root cause is a chain of 6 propagation gaps in the startd8-sdk Artisan workflow pipeline. This plan fixes all gaps, adds OTel instrumentation at propagation boundaries, and builds dashboards for propagation health monitoring.

**Objectives**: Wire DomainChecklist through ImplementPhaseHandler, make design calibration domain-aware, align validator names, instrument propagation boundaries with OTel span events, validate completeness in FINALIZE, and build health dashboards.

**Goals**: (1) Zero tasks defaulting to `domain: "unknown"` when enrichment data exists, (2) propagation completeness > 90% visible in Grafana, (3) full backward compatibility with no breaking changes.

- Project ID: `contextcore-wcp`
- Plan mode: `enriched`
- Manifest path: `.contextcore.yaml`
- Repos affected: startd8-sdk (primary), ContextCore (contracts, dashboards)

## 2. Goals and Outcomes

- Fix the 6 identified propagation gaps so domain classification reaches every downstream phase
- Add OTel span events at every propagation boundary for observability
- Build dashboard panels showing propagation health and defaulted-task rates
- Make design calibration domain-aware (token budget multipliers per domain)
- Align validator names between enrichment and test phases
- Validate propagation completeness in FINALIZE phase

## 3. Scope and Assumptions

### In Scope

- ContextCore: PropagationStatus enum, semantic conventions, design doc update, dashboard panels
- startd8-sdk: DomainChecklist wiring, calibration adjustment, validator alignment, OTel instrumentation, FINALIZE validation, integration tests

### Out of Scope

- Runtime auto-enrichment (already implemented in run_artisan_workflow.py)
- Changes to DomainPreflightWorkflow itself (working correctly)
- New dashboard (panels added to existing beaver-lead-contractor-progress dashboard)

### Assumptions

- DomainPreflightWorkflow runs before Artisan and enrichment data is in the seed
- DevelopmentPhase already accepts domain_checklist parameter (confirmed at line 1521)
- startd8-sdk OTel uses mock tracer pattern (_tracer module-level var)

## 4. Requirements Inputs

- `docs/design-principles/context-propagation.md`
- `docs/design-principles/context-propagation-session-brief.md`

## 5. Functional Requirements (FR)

- FR-001: ImplementPhaseHandler must construct DomainChecklist from enriched seed and pass to DevelopmentPhase
- FR-002: Design calibration must apply domain-specific token multipliers (config domains get 0.5x, tests 0.8x)
- FR-003: Validator names from enrichment must resolve to commands in TestPhaseHandler
- FR-004: FINALIZE phase must report propagation completeness (% of tasks with full context)
- FR-005: Span events emitted at every propagation boundary (context.propagated, context.defaulted)
- FR-006: PropagationStatus enum added to ContextCore contracts

## 6. Non-Functional Requirements (NFR)

- NFR-001: Zero performance regression — span events are lightweight additions to existing spans
- NFR-002: Backward compatible — all changes are additive, no breaking API changes
- NFR-003: Observable — propagation health visible in Grafana within 60s of workflow completion

## 7. Artifact Generation Plan

| Artifact Type | Expected Depth | Depends On | Notes |
|---------------|---------------|------------|-------|
| dashboard | comprehensive (>150 LOC) | prometheus_rule, slo_definition | Grafana JSON with panels, templating |
| prometheus_rule | standard (51-150 LOC) | service_monitor | Alert rules, recording rules |
| loki_rule | standard (51-150 LOC) | - | Log-based recording rules |
| service_monitor | brief (<=50 LOC) | - | K8s ServiceMonitor YAML |
| slo_definition | standard | - | SLO target + error budget |
| notification_policy | standard | prometheus_rule | Alert routing config |
| runbook | standard-comprehensive | prometheus_rule, dashboard | Incident procedures |

## 8. A2A Governance Gates

The export pipeline is validated by the A2A governance layer at every handoff boundary.

### Pre-Ingestion (Gate 1) — `contextcore contract a2a-check-pipeline`
- Structural integrity: all 4 export files present and valid
- Checksum chain: source → artifact manifest → CRD checksums verified
- Provenance consistency: git context and timestamps cross-checked
- Mapping completeness: every artifact has a task mapping entry
- Gap parity: coverage gaps match expected feature count
- Design calibration: expected depth per artifact type validated (warning only)

### Post-Ingestion (Gate 2) — `contextcore contract a2a-diagnose`
- Q1: Is the contract complete? (Export layer)
- Q2: Was the contract faithfully translated? (Plan Ingestion layer)
- Q3: Was the translated plan faithfully executed? (Artisan layer)

### Enrichment Fields (in onboarding-metadata.json)
- `derivation_rules`: business → artifact parameter mappings per type
- `expected_output_contracts`: depth, max_lines, completeness markers per type
- `artifact_dependency_graph`: adjacency list of artifact dependencies
- `resolved_artifact_parameters`: concrete parameter values per artifact
- `open_questions`: unresolved design decisions surfaced from guidance
- `file_ownership`: output path → artifact ID mapping for gap parity

## 9. Self-Validating Gap Verification

This plan uses itself as a test harness. Each identified gap maps to a **runtime integration check** (SV-*) that verifies the behavioral fix. These checks are implemented as pytest tests in `tests/plan_validation/test_wcp_gap_validation.py` (startd8-sdk) and `tests/plan_validation/test_wcp_contracts.py` (ContextCore).

**Execution model**: Run the full SV suite before implementation (all should fail, confirming gaps exist). After each WCP task, re-run — the corresponding SV checks should flip to passing. After all tasks, the full suite should be green.

### Gap → Task → Validation Mapping

| Gap # | Description | Fixed By | Validation Check | What It Verifies |
|-------|-------------|----------|------------------|------------------|
| 1 | Enrichment step not always run | (Already fixed) | SV-PREREQ | `run_artisan_workflow.py` auto-detects missing enrichment |
| 2 | Domain not in design_calibration | WCP-005 | SV-005 | `_derive_design_calibration()` returns different token budgets for `config-yaml` vs `python-package-module` |
| 3 | Domain stored but unused in implement | WCP-006 | SV-006 | `DevelopmentPhase` receives non-None `domain_checklist`; `context["domain_constraints"]` populated for enriched chunk |
| 4 | Key name mismatch | WCP-007 | SV-007 | `context["domain_constraints"]` key is the sole key used end-to-end (no `prompt_constraints` in execution path) |
| 5 | Design insights don't flow to implement | (Out of scope) | — | Design-to-implement feedback is a future WCP extension |
| 6 | Validator names mismatch | WCP-008 | SV-008 | Every `post_generation_validators` value from enrichment resolves to a command in `_resolve_validator_command()` |

### Additional Behavioral Checks

| Check | Fixed By | What It Verifies |
|-------|----------|------------------|
| SV-001 | WCP-001 | `PropagationStatus` enum exists in `contracts/types.py` with 4 values, all lowercase |
| SV-003-propagated | WCP-003 | `context.propagated` span event emitted when domain flows from DomainChecklist to DevelopmentPhase |
| SV-003-defaulted | WCP-003 | `context.defaulted` span event emitted when enrichment is missing and domain defaults to "unknown" |
| SV-004 | WCP-004 | `FinalizePhaseHandler._validate_propagation_completeness()` returns correct counts for mixed tasks (some with full context, some with defaults) |
| SV-E2E | WCP-009 | End-to-end: enriched seed with 3 domains (python-package-module, config-yaml, unknown) → after implement, the first two have `domain_constraints`, the third does not; FINALIZE reports 66% completeness |

### Progressive Validation Schedule

Run `python3 -m pytest tests/plan_validation/ -v` after each task:

| After Task | Expected Passing Checks | Expected Failing |
|------------|------------------------|------------------|
| (Before any) | SV-PREREQ only | All others |
| WCP-001 | + SV-001 | SV-005 through SV-E2E |
| WCP-005 | + SV-005 | SV-006 through SV-E2E |
| WCP-006 | + SV-006, SV-007 | SV-003, SV-004, SV-008, SV-E2E |
| WCP-008 | + SV-008 | SV-003, SV-004, SV-E2E |
| WCP-003 | + SV-003-propagated, SV-003-defaulted | SV-004, SV-E2E |
| WCP-004 | + SV-004 | SV-E2E |
| WCP-009 | + SV-E2E | (All passing) |

### Discovery Mechanism

If during implementation a new propagation gap is discovered that is NOT covered by an existing SV-* check:
1. Add a new SV-* check for the discovered gap **before** fixing it (confirm it fails)
2. Add a corresponding WCP-* subtask to the plan
3. Fix the gap
4. Confirm the new SV-* check passes
5. Update this mapping table

This ensures the plan's gap analysis stays synchronized with reality throughout execution.

## 10. Standard Test Obligations (per-task unit tests)

- Unit tests for PropagationStatus enum (ContextCore)
- Unit tests for DomainChecklist wiring in ImplementPhaseHandler (startd8-sdk)
- Unit tests for domain-aware calibration multipliers (startd8-sdk)
- Unit tests for validator name resolution (startd8-sdk)
- Unit tests for FINALIZE propagation completeness validation (startd8-sdk)
- Unit tests for span event emission at propagation boundaries (startd8-sdk)
- Integration test: end-to-end context propagation through enrichment → seed → chunks → develop → finalize
- A2A pipeline checker gate pass (Gate 1)
- Three Questions diagnostic pass (Gates 1-3)

## 11. Risks and Mitigations

- Risk: DomainChecklist constructor interface may have changed since plan exploration
  - Mitigation: Verify constructor signature before implementing WCP-006
- Risk: Span event overhead in high-task-count workflows
  - Mitigation: Events are lightweight string attributes; benchmark shows <1ms per event
- Risk: Validator name mapping may be incomplete
  - Mitigation: WCP-008 includes exhaustive audit of all enrichment validator names

## 12. Execution Notes for Startd8

- Feed this plan to `startd8 workflow run plan-ingestion`.
- Keep ContextCore export artifacts available for ingestion preflight.
- Route expectation: Prime for simpler scope; Artisan for complex or low-quality translation.
- **Pre-ingestion**: Run `contextcore contract a2a-check-pipeline` on export output.
- **Post-ingestion**: Run `contextcore contract a2a-diagnose` with `--ingestion-dir`.
- **Export**: Always use `--emit-provenance` for checksum chain integrity.

## 13. Implementation Order

```
WCP-SV (self-validation suite — write first, confirm all fail)
    │
    ├──→ WCP-001 (contract)  ──┐
    ├──→ WCP-002 (doc update)   │
    │                           ├──→ WCP-006 (wire DomainChecklist) ──→ WCP-007 (verify alignment)
    ├──→ WCP-005 (calibration) ─┘                                  │
    ├──→ WCP-008 (validators)                                       │
    │                                                               ├──→ WCP-003 (instrumentation)
    │                                                               │         │
    │                                                               ├──→ WCP-004 (FINALIZE validation)
    │                                                               │         │
    │                                                               └──→ WCP-009 (integration tests)
    │                                                                          │
    └──────────────────── re-run SV suite after each task ────────────────────→ └──→ WCP-010/011 (dashboards)
```

**Step 0**: WCP-SV — create self-validation tests, confirm all fail except SV-PREREQ.
**Parallelizable**: WCP-001, WCP-002, WCP-005, WCP-008 can all proceed in parallel after WCP-SV.
**Critical path**: WCP-SV → WCP-006 → WCP-003 → WCP-009 → WCP-010/011
**After each task**: Re-run `python3 -m pytest tests/plan_validation/ -v` to verify progressive pass/fail.
