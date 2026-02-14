# A2A Governance: 7-Day Execution Checklist

This checklist turns the quick wins into a one-week rollout focused on execution governance and observability, without duplicating runtime orchestration.

> **Implementation status**: Days 1–7 are **complete**. All items below have been implemented and tested. See `docs/design/contextcore-a2a-comms-design.md` for the full architecture reference. The init/create/export workflow has been updated to reference all A2A capabilities.

## Goal for the week

- Enforce typed contracts at A2A boundaries
- Add fail-fast gates before downstream phase execution
- Pilot end-to-end on `PI-101-002`
- Produce actionable telemetry for blocked work, dropped artifacts, and finalize outcomes

---

## Owners (suggested)

- **Platform lead**: governance rules, schema/version policy, final sign-off
- **Workflow engineer**: gate integration and orchestration hooks
- **Agent runtime engineer**: handoff validation and error envelopes
- **Observability engineer**: queries/panels and rollout metrics
- **Docs owner**: developer + agent onboarding instructions

---

## Day-by-day plan

## Day 1: Baseline and alignment ✓

- ✓ Confirm canonical docs/schemas as source of truth:
  - `docs/A2A_CONTRACTS_DESIGN.md`
  - `docs/A2A_CONTRACTS_PROJECT_PLAN.md`
  - `schemas/contracts/*.schema.json`
- ✓ Agree strict ownership boundaries:
  - LangChain = runtime orchestration
  - ContextCore = governance + observability
- ✓ Freeze v1 field set for contracts (no new fields unless query/policy need is explicit).

### Day 1 done when

- ✓ Team confirms boundaries and v1 contracts in writing. See `docs/A2A_V1_GOVERNANCE_POLICY.md`.

## Day 2: Validation helper implementation ✓

- ✓ Implement JSON schema validator helpers for:
  - `TaskSpanContract` — `src/contextcore/contracts/a2a/validator.py`
  - `HandoffContract`
  - `ArtifactIntent`
  - `GateResult`
- ✓ Add standard validation error envelope:
  - `error_code`, `schema_id`, `failed_path`, `message`, `next_action`
  - Implemented as `ValidationErrorEnvelope` in `validator.py`

### Day 2 done when

- ✓ Unit tests prove invalid payloads fail with actionable errors. See `tests/test_a2a_contracts.py` (50 tests).

## Day 3: Boundary enforcement (outbound + inbound) ✓

- ✓ Enforce validation before writing outbound handoffs — `validate_outbound()` in `boundary.py`
- ✓ Enforce validation on inbound handoff acceptance — `validate_inbound()` in `boundary.py`
- ✓ Reject invalid payloads deterministically; emit failure events — `BoundaryEnforcementError.to_failure_event()`

### Day 3 done when

- ✓ No unvalidated handoff can enter execution path.

## Day 4: Phase gate library (minimum viable) ✓

- ✓ Add reusable gates for:
  - checksum chain integrity — `check_checksum_chain()` in `gates.py`
  - artifact-task mapping completeness — `check_mapping_completeness()` in `gates.py`
  - gap parity — `check_gap_parity()` in `gates.py`
- ✓ Emit `GateResult` for every gate outcome.
- ✓ Block downstream phase on gate failure with explicit reason + next action.
- ✓ Pipeline checker runs 6 gates on real export output — `pipeline_checker.py`
- ✓ Three Questions diagnostic implements stop-at-first-failure ordering — `three_questions.py`

### Day 4 done when

- ✓ `CONTRACT_INTEGRITY` and `INGEST_PARSE_ASSESS` are both enforced. See `tests/test_pipeline_checker.py` (34 tests), `tests/test_three_questions.py` (25 tests).

## Day 5: Pilot run on `PI-101-002` ✓

- ✓ Execute one full trace using the span model — `pilot.py` simulates 10-span trace (S1-S10)
- ✓ Record:
  - blocked spans
  - handoff failures
  - dropped artifact detections (via `--drop-feature` injection)
  - finalize status
- ✓ Failure injection: `--source-checksum` (tamper), `--drop-feature` (gap parity), `--test-failures`

### Day 5 done when

- ✓ Full pilot trace exists with gate evidence and no silent phase transitions. See `tests/test_a2a_pilot.py` (21 tests).

## Day 6: Observability pack ✓

- ✓ Build baseline queries/panels — `queries.py` with 5 pre-built TraceQL/LogQL queries:
  - `blocked_span_hotspot()` — blocked spans by phase
  - `gate_failure_rate()` — gate failures over time
  - `handoff_validation_failures()` — boundary rejections
  - `dropped_artifacts()` — gap parity violations
  - `finalize_failure_trend()` — finalize-phase failures
- ✓ Grafana dashboard — `k8s/observability/dashboards/a2a-governance.json` (8 panels)
- ✓ Each panel maps to a concrete operational action.

### Day 6 done when

- ✓ On-call/operator can answer "what failed, where, why, what next" in minutes. See `tests/test_a2a_queries.py` (24 tests).

## Day 7: Hardening and adoption handoff ✓

- ✓ Document "when to promote artifact as task" — `docs/A2A_V1_GOVERNANCE_POLICY.md` §8
- ✓ Publish quickstart for devs/agents — `docs/A2A_QUICKSTART.md`
- ✓ Lock v1 governance policy — `docs/A2A_V1_GOVERNANCE_POLICY.md`:
  - schema versioning rule (v1 frozen, additive evolution only)
  - new-field approval rule (query/policy justification required)
  - required metrics/queries for rollout
- ✓ Integration pattern guides — `docs/integrations/INTEGRATION_PATTERN_GUIDE.md`, `docs/integrations/LANGGRAPH_PATTERN.md`
- ✓ Framework interop conventions — 8 attribute namespaces in `docs/agent-semantic-conventions.md`

### Day 7 done when

- ✓ New contributor can execute pilot workflow without tribal knowledge.

---

## All-upside / low-risk items to do immediately

- Require schema validation at all A2A boundaries.
- Emit `GateResult` at every phase boundary.
- Keep local debug detail as events, not contract field growth.
- Pin `schema_version=v1` and block unknown top-level fields.
- Pilot on one feature (`PI-101-002`) before broad rollout.

---

## Weekly success criteria ✓

- ✓ 100% of handoffs are schema-validated on send and receive.
- ✓ 100% of enforced phase transitions emit `GateResult`.
- ✓ At least one full `PI-101-002` pilot trace completed with gate evidence.
- ✓ Time-to-root-cause for pilot failures is reduced vs prior baseline.
- ✓ No uncontrolled schema expansion during the week.
- **154 total tests** across 5 test files covering all A2A governance functionality.

## Post-Rollout: Workflow Integration

The init/create/export workflow has been updated to reference all A2A capabilities:

- `manifest init` next steps include `a2a-check-pipeline` and `a2a-diagnose`
- `manifest create` emits A2A-aware gates, specs, and PLAN templates
- `manifest init-from-plan` includes downstream readiness assessment with A2A gate predictions
- `manifest export --emit-provenance` is recommended for checksum chain integrity
