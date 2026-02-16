# REQ-5E: Delegation Authority (Enhanced Capability/Permission Propagation)

**Status:** Draft
**Date:** 2026-02-15
**Author:** Force Multiplier Labs
**Companion Document:** [CONTEXT_CORRECTNESS_EXTENSIONS.md](../CONTEXT_CORRECTNESS_EXTENSIONS.md) -- Concern 5e
**Implementation Estimate:** ~250 lines + tests
**Priority Tier:** Tier 2 (Medium Value, Medium Complexity)

---

## Problem Statement

Agent pipelines require delegation between agents and roles. Four frameworks
independently solve fragments of this problem:

- **AutoGen** uses role-based delegation without formal contracts. An assistant
  agent can delegate to a code_executor agent, but there is no declaration of
  which roles may delegate to which other roles, and no audit trail when
  delegation is rejected.

- **CrewAI** uses guardrails that check authorization before execution. But
  guardrail failures are internal -- they produce no queryable evidence and
  use no standardized taxonomy of rejection reasons.

- **Semantic Kernel** maintains a capability registry with semantic
  descriptions. But the registry is runtime-focused -- it tracks what
  capabilities exist, not what governance rules apply to them (risk tier,
  required gates, ownership).

- **OpenAI Agents SDK** controls tool access at the platform level. But this
  is platform-specific and does not compose with cross-boundary capability
  flow.

None of these frameworks formally declare **who can delegate what to whom**,
classify capabilities by risk tier with required governance gates, or produce
queryable OTel evidence when delegation is approved or rejected. ContextCore
addresses this gap with a `delegation_authority` contract model that plugs
into the existing Layer 3 (Pre-Flight Verification) and Layer 4 (Runtime
Boundary Checks) architecture.

---

## Requirements

### Pydantic Models

#### REQ-5E-001: DelegationAuthoritySpec Pydantic Model

**Priority:** P1
**Description:** Define a `DelegationAuthoritySpec` Pydantic model that
declares which roles or agents may delegate which capabilities to which
target roles or agents. The model must use `ConfigDict(extra="forbid")` per
project convention and compose with the existing `ContextContract` schema.

**Acceptance Criteria:**
- Model has fields: `from_role` (str), `to_roles` (list[str]),
  `capabilities` (list[str]), `requires_approval` (bool, default False),
  `approval_policy` (Optional[str], default None)
- Uses `ConfigDict(extra="forbid")`
- Can be loaded from YAML via the existing `ContractLoader` pattern
- Validates that `to_roles` is non-empty
- Validates that `capabilities` is non-empty
- Validates that `approval_policy` is set when `requires_approval` is True

**Affected Files:**
- `src/contextcore/contracts/delegation/schema.py` (new)
- `src/contextcore/contracts/propagation/schema.py` (extend ContextContract
  with optional `delegation_authority` field)


#### REQ-5E-002: CapabilityRiskTier Pydantic Model

**Priority:** P1
**Description:** Define a `CapabilityRiskTier` Pydantic model that classifies
capabilities by risk level and declares required governance gates. This is
governance metadata separate from the runtime capability registry.

**Acceptance Criteria:**
- Model has fields: `capability_id` (str), `risk_tier` (RiskTierLevel enum:
  low/medium/high), `required_gates` (list[str], default empty),
  `owner` (str), `slo_handoff_success_rate` (Optional[float], ge=0.0, le=1.0)
- Uses `ConfigDict(extra="forbid")`
- `RiskTierLevel` enum added to `contracts/types.py`
- Can be loaded from YAML alongside `DelegationAuthoritySpec`

**Affected Files:**
- `src/contextcore/contracts/delegation/schema.py` (new)
- `src/contextcore/contracts/types.py` (add `RiskTierLevel` enum)


#### REQ-5E-003: ToolAccessPolicy Pydantic Model

**Priority:** P2
**Description:** Define a `ToolAccessPolicy` Pydantic model that declares
rate limits and access control lists for tool/capability invocation. This
extends the delegation model with operational constraints beyond
authorization.

**Acceptance Criteria:**
- Model has fields: `capability_id` (str), `rate_limit_per_minute`
  (Optional[int], default None), `allowed_agents` (list[str], default empty
  meaning all), `denied_agents` (list[str], default empty),
  `max_concurrent` (Optional[int], default None)
- Uses `ConfigDict(extra="forbid")`
- Denied agents take precedence over allowed agents when both are specified
- Can be included in the delegation contract YAML

**Affected Files:**
- `src/contextcore/contracts/delegation/schema.py` (new)


#### REQ-5E-004: DelegationContract Container Model

**Priority:** P1
**Description:** Define a top-level `DelegationContract` Pydantic model that
aggregates delegation authority rules, capability risk tiers, and tool access
policies into a single contract document. This model serves as the root
schema for `delegation-authority.yaml` contract files.

**Acceptance Criteria:**
- Model has fields: `schema_version` (str, default "1.0.0"),
  `contract_type` (Literal["delegation_authority"]),
  `delegation_authority` (list[DelegationAuthoritySpec]),
  `capability_risk_tiers` (list[CapabilityRiskTier], default empty),
  `tool_access_policies` (list[ToolAccessPolicy], default empty)
- Uses `ConfigDict(extra="forbid")`
- Provides `get_authority(from_role, capability)` lookup method
- Provides `get_risk_tier(capability_id)` lookup method
- Provides `get_access_policy(capability_id)` lookup method

**Affected Files:**
- `src/contextcore/contracts/delegation/schema.py` (new)


### Rejection Reason Taxonomy

#### REQ-5E-005: DelegationRejectionReason Enum

**Priority:** P1
**Description:** Define a `DelegationRejectionReason` enum with standardized
codes for delegation failures. Each code must have a stable string value
suitable for OTel span event attributes and Grafana queries.

**Acceptance Criteria:**
- Enum values: `unauthorized_role`, `capacity_exceeded`,
  `validation_failed`, `timeout`, `policy_violation`,
  `escalation_required`
- Added to `contracts/types.py` as the single source of truth
- Convenience list `DELEGATION_REJECTION_REASON_VALUES` added
- Each enum value is a `str` member (follows `str, Enum` pattern)

**Affected Files:**
- `src/contextcore/contracts/types.py`


#### REQ-5E-006: DelegationDecision Enum

**Priority:** P1
**Description:** Define a `DelegationDecision` enum that represents the
outcome of a delegation authority check. This is the top-level decision
before any rejection reason is consulted.

**Acceptance Criteria:**
- Enum values: `approved`, `rejected`, `escalated`
- Added to `contracts/types.py` as the single source of truth
- Convenience list `DELEGATION_DECISION_VALUES` added
- Each enum value is a `str` member (follows `str, Enum` pattern)

**Affected Files:**
- `src/contextcore/contracts/types.py`


### Delegation Authority Checker

#### REQ-5E-007: DelegationAuthorityChecker Class

**Priority:** P1
**Description:** Implement a `DelegationAuthorityChecker` class that
evaluates a proposed delegation against the `DelegationContract`. The
checker must determine whether the delegation is approved, rejected (with
reason), or requires escalation. It produces a structured
`DelegationCheckResult`.

**Acceptance Criteria:**
- Constructor accepts a `DelegationContract`
- `check(from_role, to_role, capability_id)` method returns
  `DelegationCheckResult`
- Returns `rejected` with `unauthorized_role` when no matching authority
  rule exists
- Returns `rejected` with `unauthorized_role` when `to_role` is not in the
  matching rule's `to_roles`
- Returns `rejected` with `unauthorized_role` when `capability_id` is not
  in the matching rule's `capabilities`
- Returns `escalated` when `requires_approval` is True
- Returns `approved` when a matching rule exists and no approval is needed
- Checks tool access policies (denied agents, rate limits) when available

**Affected Files:**
- `src/contextcore/contracts/delegation/checker.py` (new)


#### REQ-5E-008: DelegationCheckResult Pydantic Model

**Priority:** P1
**Description:** Define a `DelegationCheckResult` Pydantic model that
captures the full result of a delegation authority check, including the
decision, rejection reason (if any), matching rule details, and risk tier
information.

**Acceptance Criteria:**
- Model has fields: `decision` (DelegationDecision),
  `rejection_reason` (Optional[DelegationRejectionReason]),
  `from_role` (str), `to_role` (str), `capability_id` (str),
  `risk_tier` (Optional[RiskTierLevel]),
  `required_gates` (list[str], default empty),
  `requires_approval` (bool, default False),
  `approval_policy` (Optional[str]),
  `message` (str, default empty)
- Uses `ConfigDict(extra="forbid")`
- Provides `passed` property that returns True only when decision is
  `approved`

**Affected Files:**
- `src/contextcore/contracts/delegation/checker.py` (new)


#### REQ-5E-009: Tool Access Policy Enforcement

**Priority:** P2
**Description:** The `DelegationAuthorityChecker` must enforce tool access
policies when checking delegation authority. If a `ToolAccessPolicy` exists
for the capability, the checker must verify that the target agent is not
denied and is within rate limits.

**Acceptance Criteria:**
- If `denied_agents` contains `to_role`, return `rejected` with
  `policy_violation`
- If `allowed_agents` is non-empty and `to_role` is not in it, return
  `rejected` with `policy_violation`
- If rate limit tracking is available and limit is exceeded, return
  `rejected` with `capacity_exceeded`
- Policy check runs after authority check (authority must pass first)
- Access policy violations use `policy_violation` or `capacity_exceeded`
  rejection reasons, not `unauthorized_role`

**Affected Files:**
- `src/contextcore/contracts/delegation/checker.py` (new)


### Layer Integration

#### REQ-5E-010: Layer 3 Pre-Flight -- Verify Delegation Authority Declared

**Priority:** P1
**Description:** Extend the `PreflightChecker` to verify that delegation
authority is declared for all agent-to-agent handoffs referenced in the
contract. At pre-flight time, the checker must confirm that every
`from_role`/`capability_id` pair used by the workflow has a matching
delegation rule. This catches missing authority declarations before any
workflow phase runs.

**Acceptance Criteria:**
- New check type: `delegation_authority` in `PreflightViolation.check_type`
- If the `ContextContract` includes a `delegation_authority` section, the
  checker walks all phases and verifies that any phase with agent handoff
  patterns has a matching delegation rule
- Missing delegation authority for a used capability produces a BLOCKING
  violation
- Unused delegation rules produce an ADVISORY violation (dead authority)
- Check is skipped entirely if the contract has no `delegation_authority`
  section (backward compatible)

**Affected Files:**
- `src/contextcore/contracts/preflight/checker.py` (extend)
- `src/contextcore/contracts/delegation/checker.py` (new)


#### REQ-5E-011: Layer 4 Runtime -- Check Delegation Authority at Boundary

**Priority:** P1
**Description:** Extend the `RuntimeBoundaryGuard` to validate delegation
authority at phase boundaries where agent-to-agent handoffs occur. At
runtime, when a phase delegates to another agent, the guard must check
that the delegation is authorized before the handoff proceeds.

**Acceptance Criteria:**
- `RuntimeBoundaryGuard` accepts an optional `DelegationContract`
- When a phase invokes a handoff, the guard calls
  `DelegationAuthorityChecker.check()` before the handoff proceeds
- In `strict` mode, rejected delegations raise `DelegationViolationError`
  (new exception, subclass of `BoundaryViolationError`)
- In `permissive` mode, rejected delegations are logged but the handoff
  proceeds
- In `audit` mode, all delegation decisions are logged and emitted via OTel
- Delegation check results are recorded in `PhaseExecutionRecord`
- Backward compatible: if no `DelegationContract` is provided, delegation
  checks are skipped

**Affected Files:**
- `src/contextcore/contracts/runtime/guard.py` (extend)
- `src/contextcore/contracts/delegation/checker.py` (new)


### OTel Emission

#### REQ-5E-012: OTel Emission for Delegation Decisions

**Priority:** P1
**Description:** Implement OTel span event emission for delegation authority
decisions (both approved and rejected). Follow the existing
`_add_span_event()` pattern from `contracts/propagation/otel.py` with
`_HAS_OTEL` guard.

**Acceptance Criteria:**
- `emit_delegation_result(result: DelegationCheckResult)` function
- Event name: `context.delegation.approved` or
  `context.delegation.rejected` or `context.delegation.escalated`
  (based on decision)
- Span event attributes include: `delegation.from_role`,
  `delegation.to_role`, `delegation.capability_id`,
  `delegation.decision`, `delegation.rejection_reason` (if rejected),
  `delegation.risk_tier` (if available),
  `delegation.requires_approval`, `delegation.message`
- Guarded by `_HAS_OTEL` -- degrades gracefully when OTel is not installed
- Logs at DEBUG level for approved, WARNING for rejected, INFO for escalated

**Affected Files:**
- `src/contextcore/contracts/delegation/otel.py` (new)


#### REQ-5E-013: OTel Emission for Delegation Audit Summary

**Priority:** P2
**Description:** Implement a summary OTel span event that aggregates all
delegation decisions across a workflow run. Emitted at workflow completion
alongside the existing `context.propagation_summary`.

**Acceptance Criteria:**
- `emit_delegation_summary(results: list[DelegationCheckResult])` function
- Event name: `context.delegation_summary`
- Attributes include: `delegation.total_checks`, `delegation.approved`,
  `delegation.rejected`, `delegation.escalated`,
  `delegation.approval_rate_pct`
- Follows `emit_propagation_summary()` pattern from `propagation/otel.py`
- Guarded by `_HAS_OTEL`

**Affected Files:**
- `src/contextcore/contracts/delegation/otel.py` (new)


### Audit Trail

#### REQ-5E-014: Delegation Audit Record Model

**Priority:** P2
**Description:** Define a `DelegationAuditRecord` Pydantic model that
captures the full audit trail of a delegation decision, including
timestamps, the requesting context, and the governance rule that was
applied.

**Acceptance Criteria:**
- Model has fields: `timestamp` (datetime), `from_role` (str),
  `to_role` (str), `capability_id` (str),
  `decision` (DelegationDecision),
  `rejection_reason` (Optional[DelegationRejectionReason]),
  `risk_tier` (Optional[RiskTierLevel]),
  `required_gates` (list[str]),
  `gates_passed` (list[str], default empty),
  `gates_failed` (list[str], default empty),
  `approval_policy` (Optional[str]),
  `approved_by` (Optional[str]),
  `trace_id` (Optional[str]),
  `span_id` (Optional[str])
- Uses `ConfigDict(extra="forbid")`
- Can be serialized to JSON for Loki structured log emission

**Affected Files:**
- `src/contextcore/contracts/delegation/schema.py` (new)


#### REQ-5E-015: Audit Trail Collection in DelegationAuthorityChecker

**Priority:** P2
**Description:** The `DelegationAuthorityChecker` must maintain an ordered
list of `DelegationAuditRecord` entries for all checks performed during a
workflow run. This audit trail must be accessible for post-execution
analysis and OTel emission.

**Acceptance Criteria:**
- `DelegationAuthorityChecker` has an `audit_trail` property returning
  `list[DelegationAuditRecord]`
- Every call to `check()` appends a `DelegationAuditRecord`
- `reset()` method clears the audit trail (parallels
  `RuntimeBoundaryGuard.reset()`)
- Audit trail includes current OTel trace_id and span_id when available
  (using `_HAS_OTEL` guard)
- Audit records are timestamped with UTC

**Affected Files:**
- `src/contextcore/contracts/delegation/checker.py` (new)


### Integration with Handoff System

#### REQ-5E-016: HandoffManager Delegation Check Integration

**Priority:** P2
**Description:** The existing `HandoffManager.create_handoff()` method
should optionally accept a `DelegationContract` and validate delegation
authority before creating a handoff. When delegation is rejected, the
handoff is not created and a `HandoffStatus.REJECTED` is returned.

**Acceptance Criteria:**
- `HandoffManager.__init__()` accepts optional `delegation_contract`
  parameter
- When `delegation_contract` is set, `create_handoff()` calls
  `DelegationAuthorityChecker.check()` before proceeding
- If delegation is rejected, method raises `DelegationViolationError` or
  returns a rejection result (depending on enforcement mode)
- If delegation requires escalation, the `requires_approval` flag is set
  on the handoff and status starts as `PENDING` with an `escalation`
  event
- OTel span event emitted for the delegation decision within the existing
  handoff creation span
- Backward compatible: if `delegation_contract` is None, no delegation
  check is performed (existing behavior preserved)

**Affected Files:**
- `src/contextcore/agent/handoff.py` (extend)
- `src/contextcore/contracts/delegation/checker.py` (new)


#### REQ-5E-017: Risk-Tier-Gated Handoffs

**Priority:** P3
**Description:** When a capability has a `high` risk tier, the
`DelegationAuthorityChecker` must verify that all `required_gates` have
been satisfied before approving the delegation. Gate satisfaction is
determined by checking the context for gate completion markers.

**Acceptance Criteria:**
- If `risk_tier` is `high` and `required_gates` is non-empty, checker
  verifies gate completion markers exist in the provided context
- Missing gate markers result in `rejected` with `validation_failed`
- Gate check results are recorded in the `DelegationAuditRecord`
  (`gates_passed`, `gates_failed`)
- Medium risk tier logs a warning if gates are missing but does not block
- Low risk tier skips gate checks entirely

**Affected Files:**
- `src/contextcore/contracts/delegation/checker.py` (new)


### Contract Loading

#### REQ-5E-018: YAML Contract Loader for Delegation Authority

**Priority:** P1
**Description:** Implement a contract loader that reads
`delegation-authority.yaml` files and produces a validated
`DelegationContract` instance. Follow the existing `ContractLoader`
pattern from `contracts/propagation/loader.py`.

**Acceptance Criteria:**
- `load_delegation_contract(path)` function that reads YAML and returns
  `DelegationContract`
- Validates against the Pydantic schema (raises `ValidationError` on
  invalid input)
- Supports loading from file path or dict
- Logs loaded contract summary (number of rules, risk tiers, policies)

**Affected Files:**
- `src/contextcore/contracts/delegation/loader.py` (new)

---

## Contract Schema

Example `delegation-authority.yaml`:

```yaml
schema_version: "1.0.0"
contract_type: delegation_authority

delegation_authority:
  - from_role: "orchestrator"
    to_roles: ["code_executor", "researcher", "reviewer"]
    capabilities: ["code_generation", "web_search", "code_review"]
    requires_approval: false

  - from_role: "researcher"
    to_roles: ["code_executor"]
    capabilities: ["code_generation"]
    requires_approval: true
    approval_policy: "human_or_orchestrator"

  - from_role: "reviewer"
    to_roles: ["researcher"]
    capabilities: ["web_search"]
    requires_approval: false

capability_risk_tiers:
  - capability_id: "code_generation"
    risk_tier: high
    required_gates: ["code_review", "test_pass"]
    owner: "platform-team"
    slo_handoff_success_rate: 0.95

  - capability_id: "web_search"
    risk_tier: low
    required_gates: []
    owner: "infrastructure-team"
    slo_handoff_success_rate: 0.99

  - capability_id: "code_review"
    risk_tier: medium
    required_gates: ["lint_pass"]
    owner: "engineering-team"
    slo_handoff_success_rate: 0.97

tool_access_policies:
  - capability_id: "web_search"
    rate_limit_per_minute: 30
    allowed_agents: []  # empty = all allowed
    denied_agents: ["untrusted_agent"]
    max_concurrent: 5

  - capability_id: "code_generation"
    rate_limit_per_minute: 10
    allowed_agents: ["code_executor", "senior_executor"]
    denied_agents: []
    max_concurrent: 2
```

---

## Integration Points

### Fit Within Existing Layer Architecture

The delegation authority contract type plugs into the existing 7-layer
defense-in-depth stack without adding new layers:

```
Layer 7: Regression Prevention
  Gate: delegation approval rate must not decrease below SLO

Layer 6: Observability & Alerting
  Alert: delegation rejection spike, unauthorized role attempts

Layer 5: Post-Execution Validation
  Check: audit trail completeness, gate satisfaction for high-risk caps

Layer 4: Runtime Boundary Checks  <-- REQ-5E-011
  Validates: delegation authority at handoff boundaries

Layer 3: Pre-Flight Verification  <-- REQ-5E-010
  Checks: delegation authority declared for all used capabilities

Layer 2: Static Analysis
  Analyzes: delegation graph for unreachable roles, circular authority

Layer 1: Context Contracts (Declarations)  <-- REQ-5E-001 through REQ-5E-004
  Declares: delegation_authority YAML contracts
```

### Shared Primitives

All delegation authority functionality uses the same four primitives from the
parent Context Correctness by Construction document:

| Primitive | Delegation Authority Usage |
|-----------|--------------------------|
| **Declare** | `DelegationContract` YAML with authority rules, risk tiers, access policies |
| **Validate** | `DelegationAuthorityChecker.check()` at phase boundaries |
| **Track** | `DelegationAuditRecord` with timestamps, trace correlation |
| **Emit** | `emit_delegation_result()` and `emit_delegation_summary()` span events |

### Composability with Other Concerns

| Concern | Composition |
|---------|------------|
| Concern 1 (Propagation) | Delegation authority is checked BEFORE context propagation begins |
| Concern 6e (Multi-Budget) | Delegation can be rejected when budget is exhausted (`capacity_exceeded`) |
| Concern 9 (Quality) | High-risk delegations can require quality gate satisfaction |
| Concern 10 (Checkpoint) | Delegation authority must be re-validated on checkpoint resume |
| Concern 13 (Evaluation) | Evaluation gates can serve as `required_gates` for high-risk capabilities |

### Existing Module Dependencies

```
contracts/delegation/schema.py
  imports: contracts/types.py (RiskTierLevel, DelegationRejectionReason, DelegationDecision)
  pattern: Pydantic BaseModel with ConfigDict(extra="forbid")

contracts/delegation/checker.py
  imports: contracts/delegation/schema.py
  imports: contracts/types.py
  pattern: Stateful checker with reset(), parallels RuntimeBoundaryGuard

contracts/delegation/otel.py
  imports: contracts/delegation/checker.py (DelegationCheckResult)
  imports: contracts/types.py
  pattern: _HAS_OTEL guard + _add_span_event(), parallels propagation/otel.py

contracts/delegation/loader.py
  imports: contracts/delegation/schema.py
  pattern: YAML load + Pydantic validation, parallels propagation/loader.py

agent/handoff.py  (extended)
  imports: contracts/delegation/checker.py (optional)
```

---

## Test Requirements

### Unit Tests

| Test Area | Minimum Tests | Description |
|-----------|--------------|-------------|
| `DelegationAuthoritySpec` validation | 5 | Valid construction, empty to_roles rejected, empty capabilities rejected, approval_policy required when requires_approval=True, extra fields rejected |
| `CapabilityRiskTier` validation | 4 | Valid construction, SLO bounds (0.0-1.0), enum validation, extra fields rejected |
| `ToolAccessPolicy` validation | 3 | Valid construction, denied precedence over allowed, extra fields rejected |
| `DelegationContract` lookup methods | 4 | `get_authority()`, `get_risk_tier()`, `get_access_policy()`, missing lookups return None |
| `DelegationAuthorityChecker.check()` | 8 | Approved (matching rule), rejected (no rule), rejected (wrong to_role), rejected (wrong capability), escalated (requires_approval), policy_violation (denied agent), capacity_exceeded, validation_failed (missing gates) |
| `DelegationCheckResult` | 3 | `passed` property, serialization, extra fields rejected |
| OTel emission | 4 | Approved event, rejected event, escalated event, summary event |
| Audit trail | 3 | Records appended, reset clears, trace correlation captured |
| YAML loader | 3 | Valid load, invalid schema rejected, file-not-found handled |
| Layer 3 integration | 3 | Missing authority violation, unused authority advisory, no delegation section skipped |
| Layer 4 integration | 4 | Strict mode raises, permissive mode logs, audit mode emits, no contract skips check |
| HandoffManager integration | 3 | Delegation approved proceeds, delegation rejected blocks, no contract backward compat |

**Total minimum: ~47 tests**

### Test Patterns

Tests must follow existing conventions:
- Mock OTel with `_HAS_OTEL = False` or patched tracer
- Use `ConfigDict(extra="forbid")` validation tests (ensure invalid fields
  are rejected)
- Test both `approved` and `rejected` paths with specific rejection reasons
- Verify OTel span event attribute names and types match the specification

### Test File Locations

```
tests/unit/contextcore/contracts/delegation/test_schema.py
tests/unit/contextcore/contracts/delegation/test_checker.py
tests/unit/contextcore/contracts/delegation/test_otel.py
tests/unit/contextcore/contracts/delegation/test_loader.py
tests/unit/contextcore/contracts/preflight/test_delegation_preflight.py
tests/unit/contextcore/contracts/runtime/test_delegation_runtime.py
tests/unit/contextcore/agent/test_handoff_delegation.py
```

---

## Non-Requirements

The following are explicitly out of scope for this concern:

1. **Runtime capability discovery.** This concern declares and validates
   delegation authority. It does NOT implement a capability registry or
   service mesh. Use Semantic Kernel or similar for runtime discovery; use
   this concern to govern what discovered capabilities may be delegated.

2. **Workflow orchestration.** Delegation authority checks whether a
   delegation is allowed. It does NOT orchestrate the delegation itself.
   That remains the responsibility of `HandoffManager` and the runtime
   framework (LangGraph, AutoGen, etc.).

3. **Authentication/identity verification.** This concern trusts that
   `from_role` and `to_role` are accurately reported. It does NOT verify
   agent identity. Identity verification is an infrastructure concern
   (mTLS, API keys) outside the contract model.

4. **Dynamic policy changes during execution.** The `DelegationContract`
   is loaded once and used for the duration of a workflow run. Hot-reloading
   of delegation policies mid-execution is not supported. To change
   policies, restart the workflow with an updated contract.

5. **Cross-project delegation.** Delegation authority is scoped to a single
   `DelegationContract` within a single project. Cross-project capability
   delegation (e.g., agent in project A delegating to agent in project B)
   requires a federation mechanism not covered here. See REQ-8 in
   `docs/plans/WEAVER_CROSS_REPO_ALIGNMENT_REQUIREMENTS.md` for
   cross-project considerations.

6. **Billing or cost attribution for delegations.** While `capacity_exceeded`
   is a rejection reason, actual cost tracking and billing for delegated
   capability usage is handled by contextcore-beaver (Amik), not by the
   delegation authority contract.

7. **Delegation chain depth limits.** This concern checks single-hop
   delegation (A delegates to B). Multi-hop delegation chains (A delegates
   to B, B re-delegates to C) are not validated for depth or circularity in
   this version. This is a candidate for future extension.
