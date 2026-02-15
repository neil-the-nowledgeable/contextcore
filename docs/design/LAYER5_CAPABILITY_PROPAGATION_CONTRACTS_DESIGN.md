# Capability and Permission Propagation Contracts — Layer 5 Design

**Status:** Draft
**Date:** 2026-02-15
**Author:** Force Multiplier Labs
**Confidence:** 0.78
**Implementation:** `src/contextcore/contracts/capability/` (planned)
**Related:**
- [Context Correctness by Construction](CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md) — theoretical foundation
- [Context Propagation Contracts (Layer 1)](CONTEXT_PROPAGATION_CONTRACTS_DESIGN.md) — foundational contract layer
- [ADR-001: Tasks as Spans](../adr/001-tasks-as-spans.md) — foundational architecture
- [A2A Contracts Design](A2A_CONTRACTS_DESIGN.md) — contract-first agent coordination
- [Semantic Conventions](../semantic-conventions.md) — attribute naming standards

---

## 1. Problem

Capabilities and permissions must travel with call chains across service and
agent boundaries. In practice, they routinely do not — and the failures are
uniquely dangerous because they bifurcate into two failure modes that are both
silent and opposite in character.

### 1.1 The Lost Permission (Under-Permissive Failure)

A user with the `admin` scope authenticates to Service A. Service A calls
Service B on the user's behalf, forwarding the JWT. Service B calls Service C.
Service C needs `admin` scope to perform a privileged database migration. But
Service B stripped the scope when constructing its outbound request — it copied
the user ID but not the authorization claims. Service C receives a request with
no `admin` scope, defaults to denying the operation, and returns a 403.

The user sees: **"Permission denied."**

The user *has* the permission. The permission was present at the entry point.
It was lost at the B-to-C boundary. No system declared that the A → B → C call
chain requires `admin` scope to survive all three hops. No system can tell the
user *where* the permission was lost. The 403 is correct from C's local
perspective and entirely wrong from the end-to-end perspective.

Debugging requires a developer to trace through B's code, find the outbound
request construction, and discover that authorization headers were not
forwarded. This is exactly the same failure mode as context propagation — a
required field was dropped at an intermediate hop.

### 1.2 The Phantom Permission (Over-Permissive Failure)

More insidious. Service A receives a request with `read_only` scope. It calls
Service B, which calls Service C. Service B drops the scope from its outbound
request. Service C has no scope information and falls back to `default-allow` —
a common pattern in internal services that assume all callers are trusted.
Service C performs a privileged write operation that the original user was not
authorized to perform.

No error is raised. No alert fires. The operation succeeds. An unauthorized
mutation has occurred. The audit trail shows C performed the write but cannot
explain *why* the scope check was bypassed, because C never received scope
information to check.

This is the security dual of silent degradation: instead of reduced quality,
you get **reduced security** — silently.

### 1.3 Agent Pipeline Capabilities

The problem extends beyond traditional services into agent pipelines. Agent A
has `code_write` capability — it is authorized to create and modify source
files. Agent A delegates to Agent B for code generation. Agent B delegates to
Agent C for test writing. The pipeline has no declaration of capability
requirements:

- Does Agent C inherit `code_write`? It is writing test files, which are source
  files. Should it be allowed to write *any* file, or only test files?
- If Agent B has `code_write` but Agent C does not, should C's test file
  generation succeed? It produces files that B integrates — does B's capability
  cover C's output?
- If Agent A revokes `code_write` mid-pipeline (e.g., a human reviewer
  intervenes), how does the revocation propagate to B and C?

Without a capability contract, agent pipelines inherit the worst of both
failure modes: agents either operate with maximum privilege (no boundary checks)
or refuse operations that should succeed (overly conservative default-deny).

### 1.4 The Structural Diagnosis

All three scenarios share the same root cause: **no declaration of end-to-end
capability requirements**. The mechanisms exist — OAuth2 scopes, JWT claims,
RBAC policies, API keys, agent capability manifests. What is missing is a
*contract* that says:

- "This call chain REQUIRES scope X to reach service D"
- "This agent pipeline REQUIRES capability Y to propagate from Agent A to Agent C"
- "Capability Z MUST be attenuated (narrowed) at the B boundary, not dropped"

This is structurally identical to Layer 1 context propagation. A capability is
a metadata field that must survive a channel of intermediate hops. The channel
can drop it, corrupt it, or widen it. The contract declares what should happen.
The validator verifies that it did.

---

## 2. Solution Overview

A contract system that treats capability propagation like a typed information
flow. Pipelines declare what capabilities are required at each boundary, how
capabilities may be attenuated as they flow, and what constitutes a capability
violation. The system uses the same four primitives as Layer 1 — Declare,
Validate, Track, Emit — extended with capability-specific semantics.

```
                    YAML Contract
                  (artisan-pipeline.capability.yaml)
                         |
                    ContractLoader
                     (parse + cache)
                         |
              +----------+-----------+
              v          v           v
     CapabilityValidator     CapabilityTracker
     (entry/exit/boundary)   (stamp + attenuation)
              |                      |
              v                      v
CapabilityValidationResult   CapabilityChainResult
(passed, cap_results,        (INTACT/ATTENUATED/
 missing_caps,                ESCALATION_BLOCKED/
 escalation_attempts)         BROKEN)
              |                      |
              +-----------+----------+
                          v
               OTel Span Event Emission
               (capability.verified,
                capability.missing,
                capability.attenuated,
                capability.escalation_blocked)
```

### Split Placement

Following the Layer 1 pattern, the framework lives in **ContextCore** and
concrete pipeline contracts live in the consuming repo.

| Component | Repo | Path |
|---|---|---|
| Schema models | ContextCore | `src/contextcore/contracts/capability/schema.py` |
| YAML loader | ContextCore | `src/contextcore/contracts/capability/loader.py` |
| Capability validator | ContextCore | `src/contextcore/contracts/capability/validator.py` |
| Capability tracker | ContextCore | `src/contextcore/contracts/capability/tracker.py` |
| OTel emission | ContextCore | `src/contextcore/contracts/capability/otel.py` |
| Pipeline capability contract | startd8-sdk | `src/startd8/contractors/contracts/artisan-pipeline.capability.yaml` |
| Validation wrapper | startd8-sdk | `src/startd8/contractors/capability_schema.py` |
| Orchestrator wiring | startd8-sdk | `src/startd8/contractors/artisan_contractor.py` |

---

## 3. Contract Format

Contracts are YAML files validated against Pydantic v2 models
(`CapabilityContract`). All models use `extra="forbid"` to reject unknown keys
at parse time, following the Layer 1 convention.

### 3.1 Top-Level Structure

```yaml
schema_version: "0.1.0"        # SemVer, starts at 0.1.0 per Weaver convention
contract_type: capability_propagation
pipeline_id: artisan            # Which pipeline this governs
description: >
  Capability propagation contract for the Artisan code generation pipeline.
  Declares required capabilities per phase and end-to-end capability chains
  that must survive the pipeline.

capabilities:                   # Capability definitions (registry)
  - name: code_write
    description: "Permission to write/modify source files"
    scope: filesystem
  - name: test_execute
    description: "Permission to run test suites"
    scope: subprocess
  - name: code_read
    description: "Permission to read source files for analysis"
    scope: filesystem

phases:                         # Per-phase capability requirements
  plan:
    requires: [code_read]
    provides: [code_read]       # Passes through
    attenuations: []
  implement:
    requires: [code_write, code_read]
    provides: [code_write]      # Passes through for downstream
    attenuations: []
  test:
    requires: [test_execute, code_read]
    provides: []                # Terminal — no downstream capabilities
    attenuations:
      - capability: code_write
        narrowed_to: test_write # Attenuate code_write to test-only writes
        reason: "Tests should only write to test directories"

capability_chains:              # End-to-end capability flow declarations
  - chain_id: code_write_through_pipeline
    description: >
      code_write must flow from plan (where user approval grants it)
      to implement (where file generation consumes it).
    capability: code_write
    source:
      phase: plan
      granted_by: user_approval
    waypoints:
      - phase: scaffold
    destination:
      phase: implement
      required_for: file_generation
    severity: blocking
    attenuation_policy: narrow_only

  - chain_id: test_execute_to_test
    description: >
      test_execute must be present at the test phase.
    capability: test_execute
    source:
      phase: plan
      granted_by: pipeline_config
    destination:
      phase: test
      required_for: test_suite_execution
    severity: blocking
    attenuation_policy: narrow_only
```

### 3.2 Capability Definitions

Each capability in the registry is a `CapabilityDefinition`:

| Property | Type | Required | Description |
|---|---|---|---|
| `name` | str | Yes | Unique capability identifier (e.g. `code_write`) |
| `description` | str | No | Human-readable description |
| `scope` | str | No | Scope domain: `filesystem`, `network`, `subprocess`, `data`, `admin` |
| `parent` | str | No | Parent capability — establishes hierarchy (e.g., `code_write` is a child of `filesystem_access`) |
| `attenuable` | bool | No | Whether this capability can be narrowed. Default: `true` |

Capability names use snake_case and follow the pattern `{domain}_{action}`:
`code_write`, `code_read`, `test_execute`, `data_read`, `admin_manage`. This
mirrors OAuth2 scope naming conventions while staying readable.

### 3.3 Phase Capability Contracts

Each phase declares capabilities in three lists:

| Property | Type | Description |
|---|---|---|
| `requires` | list[str] | Capabilities that MUST be present for the phase to execute |
| `provides` | list[str] | Capabilities that the phase passes through or introduces for downstream |
| `attenuations` | list[AttenuationSpec] | Capabilities narrowed at this boundary |

A phase cannot **provide** a capability it does not **require** or receive from
upstream. This is the monotonicity constraint — capabilities flow downstream
but cannot be fabricated mid-pipeline.

### 3.4 Attenuation Specifications

```yaml
attenuations:
  - capability: code_write          # Which capability is narrowed
    narrowed_to: test_write         # The attenuated form
    reason: "Tests should only write to test directories"
    constraints:                    # Optional — machine-checkable constraints
      path_prefix: "tests/"
      file_extensions: [".py", ".yaml"]
```

| Property | Type | Required | Description |
|---|---|---|---|
| `capability` | str | Yes | The capability being attenuated |
| `narrowed_to` | str | Yes | The narrower capability it becomes |
| `reason` | str | No | Human-readable justification |
| `constraints` | dict | No | Machine-checkable narrowing constraints |

### 3.5 Capability Chain Specifications

Chains declare end-to-end capability flow, following the same structure as
Layer 1's `PropagationChainSpec`:

| Property | Type | Required | Description |
|---|---|---|---|
| `chain_id` | str | Yes | Unique identifier (used in OTel events, dashboards) |
| `description` | str | No | Human-readable purpose |
| `capability` | str | Yes | The capability being tracked |
| `source` | CapabilityEndpoint | Yes | Where the capability originates |
| `waypoints` | list[CapabilityEndpoint] | No | Intermediate phases |
| `destination` | CapabilityEndpoint | Yes | Where the capability must arrive |
| `severity` | ConstraintSeverity | No | Default: `blocking` (capabilities are load-bearing by default) |
| `attenuation_policy` | str | No | `narrow_only` (default), `exact`, or `any` |

**Attenuation policies:**

| Policy | Meaning |
|---|---|
| `narrow_only` | Capability can be narrowed but never widened at any hop |
| `exact` | Capability must arrive with identical scope — no attenuation allowed |
| `any` | No attenuation checking — only presence is verified |

The default `narrow_only` implements the **principle of attenuation** from
macaroon-based systems: a capability can only become more restrictive as it
propagates, never more permissive.

---

## 4. Capability Model

Capabilities in the contract system have three dimensions, each of which must
propagate correctly across boundaries.

### 4.1 Identity (WHO)

The entity that holds the capability. Three entity types:

| Entity Type | Examples | Representation |
|---|---|---|
| **User** | Human operator, reviewer | `user:{user_id}` |
| **Agent** | LLM agent, automation | `agent:{agent_id}` |
| **Service** | Service account, system | `service:{service_name}` |

Identity travels with the capability and determines audit attribution. When
Agent A delegates to Agent B, the capability chain records both
`granted_to: agent:A` and `delegated_to: agent:B`. This is critical for the
audit question: "Who authorized this operation?"

### 4.2 Permission (WHAT)

The specific authorization being granted. Permissions form a hierarchy:

```
filesystem_access
  +-- code_read
  +-- code_write
  |     +-- test_write
  |     +-- src_write
  +-- config_write
subprocess_access
  +-- test_execute
  +-- build_execute
data_access
  +-- data_read
  +-- data_write
admin
  +-- admin_manage
  +-- admin_audit
```

A capability at a parent level implies all child capabilities. `code_write`
implies both `test_write` and `src_write`. The validator checks the hierarchy
when verifying requirements — a phase that requires `test_write` is satisfied
by `code_write`.

### 4.3 Attenuation (HOW MUCH)

Capabilities can be narrowed — never widened — as they propagate. This follows
the macaroon principle (Birgisson et al., 2014): a bearer token can add
caveats (restrictions) but cannot remove them.

In the contract system, attenuation manifests as:

1. **Scope narrowing**: `code_write` becomes `test_write` at the test phase
2. **Path restriction**: `code_write(path=/*)` becomes `code_write(path=/tests/*)`
3. **Time bounding**: A capability with 1-hour expiry becomes one with 15-minute expiry
4. **Operation restriction**: `data_read_write` becomes `data_read`

The `CapabilityTracker` records each attenuation step, creating a provenance
trail that answers: "How was this capability narrowed as it traveled through
the pipeline?"

### 4.4 The Attenuation Invariant

The fundamental safety property:

> At every boundary in the pipeline, the set of capabilities exiting the
> boundary must be a **subset** of the capabilities entering the boundary.

Formally: for any boundary B, `capabilities_out(B) ⊆ capabilities_in(B)`

A violation of this invariant — where capabilities are wider at the exit than
at the entry — indicates a **privilege escalation**. The validator treats this
as a `BLOCKING` failure regardless of the chain's declared severity, because
privilege escalation is always a security defect.

---

## 5. Pydantic Models

All models follow the Layer 1 convention: `extra="forbid"`, Pydantic v2,
reusing `ConstraintSeverity` from `contracts/types.py`.

### 5.1 Schema Models

```python
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class AttenuationPolicy(str, Enum):
    """How capabilities may be narrowed along a chain."""

    NARROW_ONLY = "narrow_only"  # Can narrow, never widen
    EXACT = "exact"              # No attenuation allowed
    ANY = "any"                  # Only presence checked


class CapabilityScope(str, Enum):
    """Scope domains for capabilities."""

    FILESYSTEM = "filesystem"
    NETWORK = "network"
    SUBPROCESS = "subprocess"
    DATA = "data"
    ADMIN = "admin"
    CUSTOM = "custom"


class CapabilityDefinition(BaseModel, extra="forbid"):
    """A named capability in the contract registry."""

    name: str
    description: str = ""
    scope: str = "custom"
    parent: str | None = None
    attenuable: bool = True


class AttenuationSpec(BaseModel, extra="forbid"):
    """Declares how a capability is narrowed at a boundary."""

    capability: str
    narrowed_to: str
    reason: str = ""
    constraints: dict[str, Any] = Field(default_factory=dict)


class PhaseCapabilityContract(BaseModel, extra="forbid"):
    """Capability requirements for a single phase."""

    description: str = ""
    requires: list[str] = Field(default_factory=list)
    provides: list[str] = Field(default_factory=list)
    attenuations: list[AttenuationSpec] = Field(default_factory=list)


class CapabilityEndpoint(BaseModel, extra="forbid"):
    """Source or destination of a capability chain."""

    phase: str
    granted_by: str = ""     # For sources: who/what grants this capability
    required_for: str = ""   # For destinations: what operation needs it


class CapabilityChainSpec(BaseModel, extra="forbid"):
    """End-to-end capability flow declaration."""

    chain_id: str
    description: str = ""
    capability: str
    source: CapabilityEndpoint
    waypoints: list[CapabilityEndpoint] = Field(default_factory=list)
    destination: CapabilityEndpoint
    severity: ConstraintSeverity = Field(ConstraintSeverity.BLOCKING)
    attenuation_policy: AttenuationPolicy = Field(
        AttenuationPolicy.NARROW_ONLY
    )


class CapabilityContract(BaseModel, extra="forbid"):
    """Top-level capability propagation contract."""

    schema_version: str = "0.1.0"
    contract_type: str = "capability_propagation"
    pipeline_id: str
    description: str = ""
    capabilities: list[CapabilityDefinition] = Field(default_factory=list)
    phases: dict[str, PhaseCapabilityContract] = Field(default_factory=dict)
    capability_chains: list[CapabilityChainSpec] = Field(default_factory=list)
```

### 5.2 Validation Result Models

```python
class CapabilityChainStatus(str, Enum):
    """End-to-end capability chain status."""

    INTACT = "intact"                     # Capability flowed correctly
    ATTENUATED = "attenuated"             # Capability narrowed (expected behavior)
    ESCALATION_BLOCKED = "escalation_blocked"  # Widening attempt rejected
    BROKEN = "broken"                     # Capability did not flow


class CapabilityValidationResult(BaseModel, extra="forbid"):
    """Result of validating capabilities at a phase boundary."""

    phase: str
    direction: str  # "entry" or "exit"
    passed: bool
    capability_results: list[CapabilityFieldResult] = Field(
        default_factory=list
    )
    missing_capabilities: list[str] = Field(default_factory=list)
    escalation_attempts: list[str] = Field(default_factory=list)
    message: str = ""


class CapabilityFieldResult(BaseModel, extra="forbid"):
    """Result for a single capability check."""

    capability: str
    present: bool
    severity: ConstraintSeverity
    attenuated: bool = False
    attenuated_from: str | None = None
    message: str = ""


class CapabilityChainResult(BaseModel, extra="forbid"):
    """Result of checking a single capability chain."""

    chain_id: str
    status: CapabilityChainStatus
    capability: str
    source_present: bool
    destination_present: bool
    waypoints_present: list[bool] = Field(default_factory=list)
    attenuations_applied: list[str] = Field(default_factory=list)
    escalation_detected: bool = False
    message: str = ""
```

---

## 6. Validation Flow

### 6.1 Per-Phase Capability Validation

At each phase transition, capability validation mirrors the Layer 1 boundary
validation pattern:

```
Phase N-1 completes
       |
       v
+---------------------------------+
| validate_phase_capabilities()    |   Check: are required capabilities
| Checks: required capabilities    |   present in the context's capability
| present in capability context    |   set?
+---------------------------------+
       | (passes)
       v
+---------------------------------+
| check_attenuation_invariant()    |   Check: were any capabilities widened
| Checks: capabilities_out is a   |   relative to capabilities_in?
| subset of capabilities_in        |   If so, BLOCKING failure.
+---------------------------------+
       | (passes)
       v
   Phase N executes
       |
       v
+---------------------------------+
| validate_exit_capabilities()     |   Check: does the phase provide what
| Checks: provided capabilities    |   it declared in the contract?
| match contract declaration       |   Prevents capability fabrication.
+---------------------------------+
```

### 6.2 Capability Resolution

Capabilities in the context travel as a set under the reserved key
`_cc_capabilities`:

```python
context = {
    "tasks": [...],
    "design_results": {...},
    # Capability metadata — travels with the context
    "_cc_capabilities": {
        "active": {"code_write", "code_read", "test_execute"},
        "attenuations": [
            {
                "original": "code_write",
                "attenuated_to": "test_write",
                "at_phase": "test",
                "reason": "Tests should only write to test directories",
            }
        ],
        "identity": "agent:artisan-orchestrator",
        "granted_at": "2026-02-15T10:30:00+00:00",
    },
    # Layer 1 provenance (coexists)
    "_cc_propagation": { ... },
}
```

**Why store capabilities in the context dict?** For the same reason Layer 1
stores provenance there — capabilities must travel with the data they protect,
through the same channel, subject to the same propagation dynamics. External
capability stores introduce a synchronization problem: the data arrives but
the capability lookup fails (network partition, cache miss, stale token).

### 6.3 Phase Entry Validation Algorithm

```
validate_phase_capabilities(phase, context, contract):
    1. Get phase contract from YAML
    2. Get active capabilities from context["_cc_capabilities"]["active"]
    3. Get capability hierarchy from contract.capabilities

    for each required_cap in phase_contract.requires:
        # Check direct match
        if required_cap in active_caps:
            result = PRESENT

        # Check hierarchy — parent capability satisfies child requirement
        elif any(is_ancestor(cap, required_cap) for cap in active_caps):
            result = PRESENT (via hierarchy)

        else:
            result = MISSING
            if severity == BLOCKING:
                validation.passed = False
                validation.missing_capabilities.append(required_cap)

    return validation
```

### 6.4 Attenuation Invariant Enforcement

```
check_attenuation_invariant(phase, context_before, context_after):
    caps_in = context_before["_cc_capabilities"]["active"]
    caps_out = context_after["_cc_capabilities"]["active"]

    # Check for escalation: any new capability not from attenuation?
    for cap in caps_out:
        if cap not in caps_in:
            # Check if it's a declared attenuation output
            if cap in declared_attenuation_outputs(phase):
                # OK: attenuated capability, record in provenance
                record_attenuation(cap)
            else:
                # ESCALATION: new capability fabricated
                return ESCALATION_BLOCKED
                # This is ALWAYS blocking, regardless of chain severity

    # Check for unexpected drops
    for cap in caps_in:
        if cap not in caps_out:
            if cap in phase_contract.provides:
                # Phase was supposed to pass this through
                return BROKEN ("Capability dropped that contract says to provide")

    return INTACT
```

### 6.5 Cross-Boundary Capability Chain Checking

At pipeline end (or at any checkpoint), `validate_all_capability_chains()`
checks every declared chain:

```
check_capability_chain(chain_spec, context):
    1. Check source phase provided the capability
       - Was the capability present after the source phase?
       - If not → BROKEN ("Source did not provide capability")

    2. Check waypoints
       - At each waypoint, was the capability present?
       - Waypoint absence is informational (same as Layer 1)

    3. Check destination
       - Is the capability present at the destination phase?
       - If not → BROKEN ("Capability did not reach destination")

    4. Check attenuation policy
       if policy == NARROW_ONLY:
           - Was the capability narrowed at any hop?
           - If narrowed: ATTENUATED (valid, expected behavior)
           - If widened: ESCALATION_BLOCKED (always blocking)
       if policy == EXACT:
           - Was the capability modified at all?
           - If modified: BROKEN ("Capability was altered")
       if policy == ANY:
           - Only check presence, ignore attenuation

    5. Return chain result with full attenuation history
```

---

## 7. Capability Provenance

### 7.1 Extending FieldProvenance

Layer 5 extends Layer 1's `FieldProvenance` with capability-specific fields:

```python
@dataclass
class CapabilityProvenance(FieldProvenance):
    """Provenance record for a capability at a point in the pipeline.

    Extends FieldProvenance with capability-specific tracking:
    who granted it, how it was narrowed, and when it expires.
    """

    granted_by: str          # Who/what granted this capability
    attenuations: list[str]  # How it was narrowed at each hop
    expiry: str | None       # ISO 8601 expiry time (None = no expiry)
    identity: str            # Entity holding the capability

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        base.update({
            "granted_by": self.granted_by,
            "attenuations": self.attenuations,
            "expiry": self.expiry,
            "identity": self.identity,
        })
        return base
```

### 7.2 Provenance Storage

Capability provenance is stored alongside Layer 1 provenance in the context
dict, under a separate key to avoid collision:

```python
context = {
    # Layer 1 provenance
    "_cc_propagation": {
        "domain_summary.domain": FieldProvenance(...),
    },
    # Layer 5 capability provenance
    "_cc_capability_provenance": {
        "code_write": CapabilityProvenance(
            origin_phase="plan",
            set_at="2026-02-15T10:30:00+00:00",
            value_hash="a1b2c3d4",
            granted_by="user_approval",
            attenuations=[],
            expiry=None,
            identity="agent:artisan-orchestrator",
        ),
        "test_write": CapabilityProvenance(
            origin_phase="test",
            set_at="2026-02-15T10:31:00+00:00",
            value_hash="e5f6g7h8",
            granted_by="attenuation:code_write",
            attenuations=["code_write -> test_write at phase:test"],
            expiry="2026-02-15T11:30:00+00:00",
            identity="agent:test-runner",
        ),
    },
}
```

### 7.3 Attenuation Trail

The `attenuations` list in `CapabilityProvenance` records the full narrowing
history. Each entry is a human-readable string describing the attenuation step:

```
["code_write -> test_write at phase:test (reason: Tests should only write to test directories)"]
```

This creates an audit trail that answers three critical questions:

1. **Who granted this capability?** → `granted_by`
2. **How was it narrowed?** → `attenuations` list
3. **Is it still valid?** → `expiry` timestamp

---

## 8. OTel Event Semantics

All events follow ContextCore telemetry conventions and are emitted as OTel
span events on the current active span. If OTel is not installed, events are
logged only (no crash), following the `_HAS_OTEL` guard pattern from Layer 1.

### 8.1 Capability Events

**Event name:** `capability.verified`

Emitted when a required capability is confirmed present at a phase boundary.

| Attribute | Type | Description |
|---|---|---|
| `capability.name` | str | Capability that was verified (e.g. `"code_write"`) |
| `capability.phase` | str | Phase where verification occurred |
| `capability.direction` | str | `"entry"` or `"exit"` |
| `capability.identity` | str | Entity holding the capability |
| `capability.granted_by` | str | How the capability was obtained |

**TraceQL query — find capability verifications for a specific phase:**
```traceql
{ name = "capability.verified" && span.capability.phase = "implement" }
```

---

**Event name:** `capability.missing`

Emitted when a required capability is absent at a phase boundary. This is the
capability analog of Layer 1's `context.chain.broken`.

| Attribute | Type | Description |
|---|---|---|
| `capability.name` | str | Capability that was required but absent |
| `capability.phase` | str | Phase where the check failed |
| `capability.direction` | str | `"entry"` or `"exit"` |
| `capability.severity` | str | `"blocking"`, `"warning"`, or `"advisory"` |
| `capability.required_for` | str | Operation that needs this capability |
| `capability.message` | str | Human-readable explanation |

**TraceQL query — find missing capabilities:**
```traceql
{ name = "capability.missing" && span.capability.severity = "blocking" }
```

---

**Event name:** `capability.attenuated`

Emitted when a capability is narrowed at a boundary. This is expected behavior
in `narrow_only` chains — it records the attenuation for audit purposes.

| Attribute | Type | Description |
|---|---|---|
| `capability.name` | str | Original capability |
| `capability.attenuated_to` | str | The narrower capability |
| `capability.phase` | str | Phase where attenuation occurred |
| `capability.reason` | str | Why the attenuation was applied |
| `capability.identity` | str | Entity whose capability was narrowed |

**TraceQL query — find all attenuations in a pipeline run:**
```traceql
{ name = "capability.attenuated" }
```

---

**Event name:** `capability.escalation_blocked`

Emitted when a phase attempts to widen a capability — introducing a capability
not present in its input. This is always a security-relevant event.

| Attribute | Type | Description |
|---|---|---|
| `capability.name` | str | Capability that was fabricated or widened |
| `capability.phase` | str | Phase where the escalation was attempted |
| `capability.identity` | str | Entity that attempted escalation |
| `capability.blocked_reason` | str | `"fabrication"` or `"widening"` |
| `capability.message` | str | Human-readable explanation |

**TraceQL query — find escalation attempts (critical security signal):**
```traceql
{ name = "capability.escalation_blocked" }
```

### 8.2 Summary Event

**Event name:** `capability.propagation_summary`

Emitted once per pipeline run, aggregating all capability chain results.

| Attribute | Type | Description |
|---|---|---|
| `capability.total_chains` | int | Total number of chains checked |
| `capability.intact` | int | Chains where capability flowed correctly |
| `capability.attenuated` | int | Chains where capability was narrowed (valid) |
| `capability.broken` | int | Chains where capability did not flow |
| `capability.escalations_blocked` | int | Privilege escalation attempts blocked |
| `capability.completeness_pct` | float | `(intact + attenuated) / total * 100` |

**TraceQL query — find pipeline runs with capability violations:**
```traceql
{ name = "capability.propagation_summary" && span.capability.broken > 0 }
```

### 8.3 Relationship to Layer 1 Events

Layer 5 events coexist with Layer 1 events. A single pipeline run may emit
both `context.boundary.entry` (Layer 1) and `capability.verified` (Layer 5)
events. They use different prefixes (`context.*` vs `capability.*`) to avoid
collision while remaining queryable in the same trace.

| Layer 1 Event | Layer 5 Analog |
|---|---|
| `context.chain.validated` | `capability.verified` |
| `context.chain.broken` | `capability.missing` |
| `context.chain.degraded` | `capability.attenuated` |
| (no equivalent) | `capability.escalation_blocked` |
| `context.propagation_summary` | `capability.propagation_summary` |

The escalation blocking event has no Layer 1 analog because context fields
cannot "escalate" — they can only be present, absent, or degraded. Capabilities
have directionality (narrow-only), which introduces the escalation failure mode.

---

## 9. Relationship to Layers 1-4

### Layer 1: Context Propagation

Layer 5 is structurally identical to Layer 1. Both track metadata flowing
through a pipeline of phases. The differences are semantic:

| Dimension | Layer 1 | Layer 5 |
|---|---|---|
| **What flows** | Data fields (domain, tasks, config) | Capabilities (permissions, scopes) |
| **Degradation** | Field gets default value | Operation runs unauthorized |
| **Direction** | Any value (no monotonicity) | Narrow-only (attenuation invariant) |
| **Default severity** | `WARNING` (degrade gracefully) | `BLOCKING` (deny by default) |
| **Extra failure mode** | None | Escalation (widening) |

The implementation reuses Layer 1's `FieldSpec` as a base for `CapabilityDefinition`,
`ChainEndpoint` as a base for `CapabilityEndpoint`, and the `PropagationTracker.stamp()`
pattern for `CapabilityTracker.stamp()`. The validator and emitter follow the
same code structure.

### Layer 2: Schema Evolution

Layer 2 validates that service interfaces are compatible. Layer 5 validates
that authorization interfaces are compatible. When Service A calls Service B,
Layer 2 checks "does A's output schema match B's input schema?" while Layer 5
checks "does A's outbound authorization match B's inbound requirement?"

The two layers compose: a call that passes schema validation (Layer 2) but
fails capability validation (Layer 5) means "the data is correct but the caller
is not authorized to send it."

### Layer 3: Semantic Conventions

Layer 3 ensures attribute names are consistent. Layer 5 depends on Layer 3 for
capability naming conventions. If one service calls a capability `admin` and
another calls it `administrator`, the capability chain appears broken even
though the intent is the same. Layer 3's convention enforcement prevents this
naming divergence.

### Layer 4: Causal Ordering

Layer 4 validates that events arrive in the correct order. Layer 5 depends on
ordering for capability revocation — if a capability is revoked at time T, all
operations after T must reflect the revocation. Without Layer 4's ordering
guarantees, a revocation event could arrive after an operation that should have
been denied, creating a time-of-check-to-time-of-use (TOCTOU) vulnerability.

---

## 10. Relationship to Existing Security Systems

Layer 5 does not replace existing authorization systems. It adds a *declaration
layer* on top of them — the same way Layer 1 adds declaration to context
propagation mechanisms that already exist.

### 10.1 OAuth2 Scopes

OAuth2 scopes are the most common capability mechanism in web services. A token
carries scopes (`read`, `write`, `admin`), and services check scopes before
performing operations.

**What OAuth2 provides:** Per-service scope checking.
**What OAuth2 lacks:** End-to-end scope flow declaration. No contract says
"scope X must survive from the API gateway to the database service, passing
through three intermediate services."

**What Layer 5 adds:** A `CapabilityChainSpec` that declares the expected scope
flow. The validator checks at each boundary that the scope survived the hop.
If Service B strips the scope before calling Service C, the validator emits
`capability.missing` — not a 403 from C with no explanation, but a diagnostic
event that says "the `admin` scope was present at B's entry but absent at B's
exit."

### 10.2 JWT Claims

JWT claims carry identity and authorization metadata. They are self-contained
(no lookup needed) but have known propagation problems:

- Services that parse claims and re-issue new JWTs may drop claims
- Claim validation is per-service, with no end-to-end checking
- Expired JWTs cause silent failures when services don't distinguish "no token"
  from "expired token"

**What Layer 5 adds:** The `CapabilityProvenance.expiry` field tracks token
expiry across the chain. If a capability's token expires mid-pipeline, the
validator can signal this specifically rather than producing a generic 401.

### 10.3 RBAC and ABAC

Role-Based Access Control (RBAC) and Attribute-Based Access Control (ABAC)
define authorization policies at the service level. They answer "given this
user's roles/attributes, can they perform this action?"

**What they lack:** Pipeline-level policy. RBAC answers "can user X do action Y
in service Z?" but not "does user X's role survive from service A to service F?"

**What Layer 5 adds:** Declaration of which roles/attributes must propagate
end-to-end. The contract makes the implicit assumption explicit: "this pipeline
requires the `admin` role to be present at every hop."

### 10.4 Macaroons

Macaroons (Birgisson et al., 2014) are bearer tokens with contextual caveats.
Each hop can add caveats (restrictions) but cannot remove them. This is exactly
the attenuation model that Layer 5 implements.

**What macaroons provide:** Mechanism for attenuable capabilities.
**What macaroons lack:** A declaration of expected attenuation patterns. A
macaroon can be attenuated in any way at any hop — there is no contract that
says "this macaroon SHOULD be attenuated at the B boundary to restrict path
access."

**What Layer 5 adds:** `AttenuationSpec` declarations that describe expected
narrowing. The validator verifies that attenuation follows the declared pattern,
not just that it is monotonic.

### 10.5 What ContextCore Uniquely Provides

All existing systems provide **mechanisms** for capability propagation. None
provide a **contract system** that declares end-to-end capability requirements
and validates them at every boundary. The gap is the same as Layer 1's gap for
context propagation:

| Existing System | Mechanism | Missing |
|---|---|---|
| OAuth2 | Scope tokens | End-to-end flow declaration |
| JWT | Self-contained claims | Cross-service propagation verification |
| RBAC | Role-based policies | Pipeline-level role flow contracts |
| ABAC | Attribute policies | Cross-boundary attribute propagation |
| Macaroons | Attenuable tokens | Expected attenuation pattern declaration |
| **ContextCore Layer 5** | **All of the above** | **Declares, validates, tracks, emits** |

---

## 11. Agent Pipeline Focus

Agent-to-agent capability delegation requires special attention because agent
pipelines have unique properties that traditional service chains do not.

### 11.1 Agent Capability Model

In the Artisan pipeline, agents operate with capabilities that control what
side effects they can produce:

| Capability | Description | Agents That Need It |
|---|---|---|
| `code_write` | Create/modify source files | Implement, Scaffold |
| `code_read` | Read source files for analysis | Plan, Design, Review |
| `test_execute` | Execute test suites | Test |
| `config_write` | Modify configuration files | Scaffold |
| `subprocess_execute` | Run arbitrary subprocesses | Test, Build |

### 11.2 Delegation Semantics

When Agent A delegates to Agent B, three questions arise:

**Q1: Does B inherit A's capabilities?**

By default, no. Capabilities are not inherited — they are explicitly declared
in the contract. If the contract says the implement phase requires `code_write`,
then the implement agent has `code_write` during that phase. Inheritance without
declaration violates the principle of least privilege.

**Q2: Can B further delegate?**

Only if the contract declares the downstream phase as requiring the capability.
Agent B cannot delegate `code_write` to Agent C unless the contract explicitly
lists `code_write` in C's phase requirements. This prevents transitive
capability leakage.

**Q3: What happens on revocation?**

If a capability is revoked mid-pipeline (e.g., a human reviewer intervenes
during the review phase and revokes `code_write`), the revocation must
propagate forward. The `CapabilityTracker` records the revocation event and
subsequent phases that require the revoked capability will fail at entry
validation.

### 11.3 Least Privilege for Agent Pipelines

The contract system enforces least privilege structurally:

```yaml
phases:
  plan:
    requires: [code_read]           # Plan only reads, never writes
    provides: [code_read]
  scaffold:
    requires: [code_write, config_write]
    provides: [code_write]          # Config_write not passed through
  implement:
    requires: [code_write]          # Needs write but not config
    provides: [code_write]
  test:
    requires: [test_execute, code_read]
    provides: []                    # Terminal — no downstream capabilities
    attenuations:
      - capability: code_write
        narrowed_to: test_write
        reason: "Tests should only write to test directories"
  review:
    requires: [code_read]           # Review reads, never writes
    provides: []
  finalize:
    requires: []                    # No special capabilities needed
    provides: []
```

This contract makes several security properties visible:

1. **Plan cannot write files** — it only has `code_read`
2. **Scaffold's `config_write` does not leak downstream** — it is not in `provides`
3. **Test cannot write arbitrary source files** — `code_write` is attenuated to `test_write`
4. **Review cannot modify code** — it only has `code_read`
5. **Finalize needs no capabilities** — it only produces a summary

Without the contract, these properties are implicit in the handler code and
invisible to reviewers. With the contract, they are explicit, reviewable in
PRs, and validated at every boundary.

### 11.4 A2A Handoff Integration

The A2A contract system (see [A2A Contracts Design](A2A_CONTRACTS_DESIGN.md))
already declares `ExpectedOutput` for agent handoffs. Layer 5 extends this
with capability metadata:

```python
handoff = CodeGenerationHandoff(
    project_id="myproject",
    agent_id="orchestrator",
    capabilities=["code_write", "code_read"],  # Layer 5: declared capabilities
)

result = handoff.request_code(
    to_agent="code-generator",
    spec=CodeGenerationSpec(
        target_file="src/mymodule.py",
        description="Implement FooBar class",
        max_lines=150,
        required_exports=["FooBar"],
        required_capabilities=["code_write"],  # Layer 5: capability requirement
    ),
)
```

The handoff validator checks that the sending agent has the capabilities that
the receiving agent requires. If Agent A hands off to Agent B with
`required_capabilities: [code_write]` but A's active capability set does not
include `code_write`, the handoff fails with a `capability.missing` event
before any work begins.

---

## 12. Dashboard Integration

### 12.1 Recommended Panels

**Capability Chain Completeness (Stat panel)**
```traceql
{ name = "capability.propagation_summary" }
| select(span.capability.completeness_pct)
```

**Missing Capabilities Over Time (Time series)**
```traceql
{ name = "capability.missing" }
| rate()
```

**Escalation Attempts (Table — critical security panel)**
```traceql
{ name = "capability.escalation_blocked" }
| select(
    span.capability.name,
    span.capability.phase,
    span.capability.identity,
    span.capability.blocked_reason,
    span.capability.message
  )
```

**Capability Attenuation Trail (Table)**
```traceql
{ name = "capability.attenuated" }
| select(
    span.capability.name,
    span.capability.attenuated_to,
    span.capability.phase,
    span.capability.reason
  )
```

**Capability Health by Pipeline Run (Table)**
```traceql
{ name = "capability.propagation_summary" }
| select(
    span.capability.total_chains,
    span.capability.intact,
    span.capability.attenuated,
    span.capability.broken,
    span.capability.escalations_blocked,
    span.capability.completeness_pct
  )
```

### 12.2 Alerting Rules

**Alert: Missing blocking capability**
```yaml
- alert: CapabilityMissing
  expr: |
    count_over_time({job="artisan"} | json
      | event="capability.missing"
      | severity="blocking" [5m]) > 0
  for: 0m
  labels:
    severity: critical
  annotations:
    summary: "A required capability is missing at a phase boundary"
```

**Alert: Privilege escalation attempt**
```yaml
- alert: CapabilityEscalationAttempt
  expr: |
    count_over_time({job="artisan"} | json
      | event="capability.escalation_blocked" [15m]) > 0
  for: 0m
  labels:
    severity: critical
  annotations:
    summary: "Privilege escalation attempt blocked — capability widening detected"
```

**Alert: Capability chain degradation**
```yaml
- alert: CapabilityChainDegraded
  expr: |
    sum(rate({job="artisan"} | json
      | event="capability.propagation_summary"
      | completeness_pct < 100 [5m])) > 0
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Capability propagation chains are not fully intact"
```

---

## 13. Adoption Path

### 13.1 For Existing Pipelines

1. **Audit current capabilities.** Before writing a contract, inventory what
   capabilities each phase actually uses. This is often surprising — phases
   frequently have more access than they need.

2. **Start with declaration only.** Write a YAML contract declaring the
   capabilities. Do not enforce. This is a documentation exercise that
   produces a reviewable artifact.

3. **Add the validator in advisory mode.** Set all capability requirements to
   `ADVISORY` severity. The validator emits OTel events but blocks nothing.
   Run in production. Watch the dashboard.

4. **Promote to warning.** After confirming that the declarations match reality,
   promote capabilities to `WARNING` severity. The validator still does not
   block but logs more prominently.

5. **Promote to blocking.** After confirming no false positives, promote
   critical capabilities to `BLOCKING` severity. The validator now prevents
   phases from running without required capabilities.

6. **Add attenuation rules.** Declare where capabilities should be narrowed.
   The validator checks that narrowing occurs at the declared boundaries.

This mirrors the Layer 1 adoption path: start with `any`, add types
incrementally, turn on strict mode when ready. It also mirrors how
organizations adopt RBAC — start permissive, monitor, tighten.

### 13.2 For New Pipelines

Write the capability contract alongside the pipeline definition. Review the
contract in the same PR as the handler code. This ensures that capability
requirements are a first-class design decision, not an afterthought.

### 13.3 For Non-Agent Pipelines

The framework is generic. Any pipeline that calls services on behalf of a user
can declare a capability contract. The Artisan-specific artifact is
`artisan-pipeline.capability.yaml` — the framework in
`contracts/capability/` works with any pipeline definition.

---

## 14. Consequences

### Positive

1. **Silent permission loss becomes observable.** Every capability drop produces
   a `capability.missing` event — not a cryptic 403 from a downstream service
   with no explanation of where the permission was lost.

2. **Silent over-permissiveness becomes observable.** Every escalation attempt
   produces a `capability.escalation_blocked` event. Default-allow patterns
   that bypass authorization checks are caught when the capability contract
   declares what should be present.

3. **Least privilege is reviewable.** The YAML contract shows exactly what
   capabilities each phase has. A PR reviewer can see "the test phase has
   `code_write` — should it?" This is invisible when capabilities are checked
   in handler code.

4. **Attenuation history is auditable.** The provenance trail answers "how did
   this capability get narrowed?" for every operation. Compliance teams can
   verify that capability narrowing follows declared policies.

5. **Framework is generic.** Not tied to any authorization system — works with
   OAuth2, JWT, RBAC, ABAC, macaroons, or custom capability systems.

6. **Composes with Layer 1.** Uses the same four primitives, same severity
   model, same OTel emission pattern. Operators familiar with Layer 1 can
   adopt Layer 5 without learning a new framework.

### Neutral

1. **Capability contract must be maintained.** When phase capabilities change,
   the contract must be updated. This is the same cost as maintaining IAM
   policies — except the contract is co-located with the code that uses it.

2. **Capability hierarchy must be designed.** The parent-child relationships
   between capabilities require upfront design. Poor hierarchy design leads to
   either overly permissive parent capabilities or excessive granularity.

### Negative

1. **Capability set stored in context dict.** Adding `_cc_capabilities` and
   `_cc_capability_provenance` to the context dict increases its size. For
   pipelines with many capabilities and long attenuation histories, this could
   become significant. The `_cc_` prefix mitigates accidental overwrites.

2. **Hierarchy resolution adds complexity.** Checking "does `code_write` satisfy
   a requirement for `test_write`?" requires traversing the capability tree.
   For deep hierarchies, this adds latency to every boundary check. In
   practice, capability hierarchies are rarely more than 3 levels deep.

3. **False positives during adoption.** When first deploying capability
   contracts, the declared requirements may not match actual usage. Phases
   may use capabilities that the contract does not declare. The advisory-mode
   adoption path mitigates this, but the initial audit requires effort.

4. **No dynamic capability grants.** The contract system validates against
   statically declared capabilities. Dynamic grants (e.g., a human approves
   additional access mid-pipeline) require re-evaluation of the context's
   `_cc_capabilities` set. The contract system does not model dynamic
   authorization flows — it validates a snapshot at each boundary.

---

## 15. Future Work

1. **Open Policy Agent (OPA) integration.** OPA evaluates Rego policies for
   authorization decisions. Layer 5 could delegate complex capability checks
   to OPA while using the contract YAML for declaration and the validator for
   boundary checking. The integration pattern: contract declares what
   capabilities should flow, OPA evaluates whether specific operations are
   permitted given those capabilities.

2. **Capability-based agent sandboxing.** Use capability contracts to define
   sandbox boundaries for agent execution. An agent with `test_write` (but not
   `code_write`) would be restricted to a filesystem sandbox rooted at
   `tests/`. The capability contract becomes the sandbox policy.

3. **Cross-pipeline capability chains.** Capabilities that must flow across
   pipeline boundaries (e.g., a CI pipeline's deployment capability must reach
   the production deployment pipeline). This requires inter-contract references,
   similar to Layer 1's planned cross-pipeline chain support.

4. **Dynamic capability negotiation.** Allow agents to request additional
   capabilities mid-pipeline via a structured protocol. The request would be
   recorded as an OTel event, reviewed by a human or policy engine, and
   granted or denied. This extends the static contract with a dynamic
   authorization workflow.

5. **Capability revocation propagation.** When a capability is revoked (e.g.,
   token expiry, human intervention), propagate the revocation forward through
   the pipeline. In-flight phases that hold the revoked capability would
   receive a revocation event and must either complete without the capability
   or abort. This depends on Layer 4 (causal ordering) for correct revocation
   timing.

6. **SPIFFE/SPIRE integration.** Use SPIFFE Verifiable Identity Documents
   (SVIDs) as the identity component of capabilities, enabling workload
   identity attestation at each boundary. The capability contract would
   declare required SPIFFE IDs alongside required capabilities.

7. **Capability usage analytics.** Track which capabilities are actually used
   (not just required) at each phase. Over time, this reveals over-provisioned
   capabilities that could be narrowed — automated least-privilege refinement.

---

## Appendix A: Planned File Inventory

| File | Estimated Lines | Purpose |
|---|---|---|
| `contracts/capability/__init__.py` | ~80 | Public API and re-exports |
| `contracts/capability/schema.py` | ~200 | Pydantic v2 models for contract format |
| `contracts/capability/loader.py` | ~90 | YAML loader with per-path cache |
| `contracts/capability/validator.py` | ~350 | Phase boundary validation + escalation checking |
| `contracts/capability/tracker.py` | ~280 | Provenance stamping + chain verification |
| `contracts/capability/otel.py` | ~170 | OTel span event emission |
| `contracts/types.py` (modified) | +15 | `CapabilityChainStatus`, `AttenuationPolicy` enums |
| `contracts/__init__.py` (modified) | +12 | Re-exports for new types |
| **Total (estimated)** | **~1,200** | — |

Plus 3 files in startd8-sdk (capability contract YAML, validation wrapper,
orchestrator wiring) and corresponding tests.

## Appendix B: Type Hierarchy

```
CapabilityContract
+-- schema_version: str
+-- contract_type: str
+-- pipeline_id: str
+-- description: str?
+-- capabilities: list[CapabilityDefinition]
|   +-- CapabilityDefinition
|       +-- name: str
|       +-- description: str?
|       +-- scope: str
|       +-- parent: str?
|       +-- attenuable: bool
+-- phases: dict[str, PhaseCapabilityContract]
|   +-- PhaseCapabilityContract
|       +-- description: str?
|       +-- requires: list[str]
|       +-- provides: list[str]
|       +-- attenuations: list[AttenuationSpec]
|           +-- AttenuationSpec
|               +-- capability: str
|               +-- narrowed_to: str
|               +-- reason: str?
|               +-- constraints: dict?
+-- capability_chains: list[CapabilityChainSpec]
    +-- CapabilityChainSpec
        +-- chain_id: str
        +-- description: str?
        +-- capability: str
        +-- source: CapabilityEndpoint {phase, granted_by}
        +-- waypoints: list[CapabilityEndpoint]
        +-- destination: CapabilityEndpoint {phase, required_for}
        +-- severity: ConstraintSeverity  (blocking | warning | advisory)
        +-- attenuation_policy: AttenuationPolicy  (narrow_only | exact | any)
```

## Appendix C: References

### Computer Science Theory

- Dennis, J.B. & Van Horn, E.C. (1966). *Programming Semantics for Multiprogrammed Computations*. CACM 9(3).
  — Capability-based security: unforgeable tokens that travel with the call chain.
- Birgisson, A. et al. (2014). *Macaroons: Cookies with Contextual Caveats for Decentralized Authorization in the Cloud*. NDSS.
  — Bearer tokens with monotonic attenuation (caveats can only be added, never removed).
- Denning, D.E. (1976). *A Lattice Model of Secure Information Flow*. CACM 19(5).
  — Information flow as lattice properties; the theoretical basis for capability ordering.
- Saltzer, J.H. & Schroeder, M.D. (1975). *The Protection of Information in Computer Systems*. Proceedings of the IEEE 63(9).
  — Principle of least privilege: every program should operate with the minimum set of privileges necessary.

### Industry Practice

- IETF RFC 6749. *The OAuth 2.0 Authorization Framework*.
  — Scope-based authorization for delegated access.
- IETF RFC 7519. *JSON Web Token (JWT)*.
  — Self-contained claims for identity and authorization.
- Open Policy Agent (OPA). https://www.openpolicyagent.org/
  — General-purpose policy engine for unified policy enforcement.
- SPIFFE. *Secure Production Identity Framework for Everyone*. https://spiffe.io/
  — Workload identity attestation for zero-trust architectures.
- OpenTelemetry. *Baggage Specification*. https://opentelemetry.io/docs/specs/otel/baggage/
  — Cross-service context propagation mechanism.
