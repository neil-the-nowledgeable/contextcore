# A2A Contracts Project Plan

> **Status**: Complete. All 12 tasks delivered in the 7-day rollout. The implemented architecture is documented in [A2A Communications Design](design/contextcore-a2a-comms-design.md). Post-rollout additions include the pipeline integrity checker and Three Questions diagnostic.

## Goal

Roll out contract-first A2A execution so developers and agents have a shared, interoperable operating model for task/subtask traces, handoffs, artifact intents, and gate decisions.

## Scope

- Introduce usage docs and examples
- Integrate schema validation at key boundaries
- Pilot in one high-value feature path (`PI-101-002`)
- Measure whether failures are detected earlier and with clearer ownership

---

## Workstreams

### WS1: Documentation and enablement

- Publish contracts overview and quickstart
- Add examples for each contract in developer-facing docs
- Add "when to promote artifact as task" guidance

### WS2: Validation integration

- Add schema validation utility wrappers
- Validate outbound handoffs and inbound handoffs
- Validate gate payloads before phase transitions

### WS3: Pilot implementation (`PI-101-002`)

- Map existing spans/tasks to contract model
- Add phase gates and block semantics
- Add artifact intent records for planned artifacts

### WS4: Observability and dashboarding

- Add baseline queries for blocked phases, dropped artifacts, and gate failures
- Add minimal dashboard panels for pilot telemetry

### WS5: Adoption and governance

- Define ownership for schema changes
- Define versioning/release process for contracts
- Establish "add new field" policy tied to query value

---

## Task List (Execution Backlog)

| ID | Task | Status | Output | Exit criteria |
| --- | --- | --- | --- | --- |
| A2A-001 | Publish schema README and examples | ✓ Done | `schemas/contracts/README.md` | Reviewed and linked from docs index |
| A2A-002 | Create design doc for contract model | ✓ Done | `docs/A2A_CONTRACTS_DESIGN.md` | Approved by workflow owners |
| A2A-003 | Create rollout project plan | ✓ Done | `docs/A2A_CONTRACTS_PROJECT_PLAN.md` | Task owners assigned |
| A2A-004 | Implement JSON schema validator helper | ✓ Done | `src/contextcore/contracts/a2a/validator.py` | 50 tests pass |
| A2A-005 | Validate outbound `HandoffContract` | ✓ Done | `src/contextcore/contracts/a2a/boundary.py` | `validate_outbound()` enforced |
| A2A-006 | Validate inbound `HandoffContract` | ✓ Done | `src/contextcore/contracts/a2a/boundary.py` | `validate_inbound()` enforced |
| A2A-007 | Emit and validate `GateResult` at phase boundaries | ✓ Done | `src/contextcore/contracts/a2a/gates.py` | Downstream phase blocked on fail |
| A2A-008 | Add `ArtifactIntent` generation in planning path | ✓ Done | `src/contextcore/contracts/a2a/models.py` | Intent model + schema |
| A2A-009 | Apply model to `PI-101-002` pilot | ✓ Done | `src/contextcore/contracts/a2a/pilot.py` | 21 tests pass |
| A2A-010 | Build pilot observability views | ✓ Done | `src/contextcore/contracts/a2a/queries.py` + dashboard JSON | 24 tests pass |
| A2A-011 | Write dev + agent onboarding guide | ✓ Done | `docs/A2A_QUICKSTART.md` | New contributor can execute pilot end-to-end |
| A2A-012 | Define v1 governance and versioning policy | ✓ Done | `docs/A2A_V1_GOVERNANCE_POLICY.md` | Schema evolution path agreed |

### Post-rollout additions

| ID | Task | Status | Output |
| --- | --- | --- | --- |
| A2A-013 | Pipeline integrity checker (6 gates on real export output) | ✓ Done | `pipeline_checker.py`, 34 tests |
| A2A-014 | Three Questions diagnostic (stop-at-first-failure) | ✓ Done | `three_questions.py`, 25 tests |
| A2A-015 | CLI commands: `a2a-check-pipeline`, `a2a-diagnose` | ✓ Done | `cli/contract.py` |

---

## Timeline (High-Level)

- **Week 1**: WS1 complete (docs and contract examples)
- **Week 2**: WS2 core validation hooks + unit tests
- **Week 3**: WS3 pilot instrumentation on `PI-101-002`
- **Week 4**: WS4 dashboards + WS5 governance sign-off

---

## Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Over-instrumentation | Noise and maintenance burden | Enforce minimal required fields and promotion rules |
| Validation friction | Slower development initially | Provide helper library and clear errors |
| Inconsistent adoption across agents | Broken interoperability | Make validation mandatory at boundaries |
| Schema churn | Version confusion | Pin `schema_version=v1`, additive changes via `v2` |

---

## Success metrics

- % of handoffs validated before execution
- % of phase transitions with `GateResult`
- Mean time to root cause for pilot failures
- % of finalize failures preceded by earlier gate failures (should increase early detection)
- Ratio of promoted artifact tasks vs event-only records (should stay intentional)

---

## Usage guidance for developers and agents

### For developers

- Use contracts when data crosses module/process boundaries.
- Validate at write-time and read-time.
- Keep schema changes rare and versioned.
- Add fields only when a concrete query/alert depends on them.

### For agent implementers

- Emit `HandoffContract` for every delegation.
- Emit `GateResult` for every boundary decision.
- Use `ArtifactIntent` for planned artifact work; promote to task only when policy criteria are met.
- Keep local debugging as span events, not contract fields.

---

## Next steps

All original tasks and post-rollout additions are complete. Future work should follow the governance policy's new-field approval rule (§2) before expanding contract schemas.
