# Schema Evolution and Contract Drift — Layer 2 Design

**Status:** Draft
**Date:** 2026-02-15
**Author:** Force Multiplier Labs
**Confidence:** 0.80
**Implementation:** Planned — `src/contextcore/contracts/schema_compat/`
**Related:**
- [Context Correctness by Construction](CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md) — theoretical foundation (Layer 2 definition)
- [Context Propagation Contracts](CONTEXT_PROPAGATION_CONTRACTS_DESIGN.md) — Layer 1 (implemented, 62 tests)
- [ADR-001: Tasks as Spans](../adr/001-tasks-as-spans.md) — foundational architecture
- [Weaver Cross-Repo Alignment Plan](../plans/WEAVER_CROSS_REPO_ALIGNMENT_PLAN.md) — Layer 3 (semantic conventions)

---

## 1. Problem

Layer 1 answers "did the field propagate?" Layer 2 answers "is it the right
shape?" These are different questions, and answering only the first leaves a
dangerous gap.

Service A produces `{"status": "active"}`. Service B expects
`{"state": "running"}`. Both services validate their own schemas. Both pass.
The integration fails silently because nobody validates the **semantic contract
between them** — the agreement that A's `status: active` means the same thing as
B's `state: running`.

This failure mode is endemic to real systems. Here are four concrete patterns:

### 1.1 Field Renaming

A team renames `user_id` to `account_id` in their response payload. Their own
tests pass (they updated their mocks). The three downstream services that read
`user_id` receive `None` and fall back to anonymous behavior. No error. No
alert. Three services silently degrade.

```
Service A (v2):  {"account_id": "u-123", "status": "active"}
Service B (v1):  expects "user_id" → gets None → anonymous fallback
Service C (v1):  expects "user_id" → gets None → skips personalization
```

### 1.2 Enum Value Drift

Service A changes its status enum from `active/inactive` to
`running/stopped/paused`. Service B maps `active` to green and `inactive` to
red. After the change, B receives `running` — which is not in its mapping — and
renders gray (unknown). The dashboard shows a sea of gray for a fleet of
healthy services.

```
Service A (v1): status ∈ {active, inactive}
Service A (v2): status ∈ {running, stopped, paused}
Service B:      maps {active→green, inactive→red}
                receives "running" → unmapped → gray
```

### 1.3 Type Coercion

Service A serializes a timestamp as an ISO 8601 string
(`"2026-02-15T10:30:00Z"`). Service B expects a Unix epoch integer
(`1739612600`). Both are "timestamps." The JSON schema says "timestamp field
is present" — true in both cases. But the consumer fails to parse and falls
back to `epoch 0`, causing it to treat every record as expired.

```
Service A: {"created_at": "2026-02-15T10:30:00Z"}   # string
Service B: expects created_at as int                  # epoch
           int("2026-02-15T10:30:00Z") → ValueError  → fallback to 0
           → all records appear expired
```

### 1.4 Required Field Addition

Service A adds a required field `region` to its response. The API gateway
validates the response schema and passes. Service B, which never requested
`region`, ignores it — but Service C treats the absence of `region` in its
*own* request to A as a default of `us-east-1`. When A starts requiring
`region` in requests too, C's hardcoded default silently routes all traffic
to one region.

### Why Existing Tools Miss This

**Protobuf/gRPC** enforces wire-format compatibility (field numbers are stable)
but not semantic compatibility. You can rename a field's logical meaning while
keeping the same field number. Proto's `reserved` keyword prevents reuse of
*numbers*, not reuse of *meanings*.

**JSON Schema** validates structure within a single document. It cannot
express "field X in schema A corresponds to field Y in schema B with this
value mapping."

**Pact / Spring Cloud Contract** validates consumer-provider API contracts
at test time. This is the closest existing approach, but it operates at the
HTTP request/response level and doesn't address:
- Cross-boundary semantic mapping (A's `status` → B's `state`)
- Evolution tracking over time (what changed between versions?)
- Runtime validation at every boundary crossing (not just in CI)
- Integration with observability infrastructure (no OTel events)

**The gap is the contract *between* schemas, not the schemas themselves.** Each
service's schema can be perfectly valid. The incompatibility lives at the
integration boundary — and that boundary is nobody's responsibility.

---

## 2. Solution Overview

A contract system that declares the **semantic relationship** between fields
across service boundaries. Where Layer 1 asks "is the field present?", Layer 2
asks "does this field mean the same thing at both ends?"

```
                    YAML Contract
              (order-pipeline.compat.yaml)
                         │
                    ContractLoader
                     (parse + cache)
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
     CompatibilityChecker    EvolutionTracker
     (structural/semantic/    (version history,
      behavioral checks)      breaking change
              │                detection)
              ▼                    │
     CompatibilityResult          ▼
     (level, field_results,  EvolutionCheckResult
      drift_details,         (compatible, breaking_
      overall_status)         changes, migration_path)
              │                    │
              └──────────┬─────────┘
                         ▼
               OTel Span Event Emission
               (schema.compatibility.check,
                schema.compatibility.drift,
                schema.compatibility.breaking)
```

The system uses the same four primitives as Layer 1:

| Primitive | Layer 1 (Propagation) | Layer 2 (Schema Compatibility) |
|---|---|---|
| **Declare** | `PropagationChainSpec` — field must flow A→F | `SchemaCompatibilitySpec` — field X in A means field Y in B |
| **Validate** | `BoundaryValidator` — is the field present? | `CompatibilityChecker` — is the shape correct? |
| **Track** | `PropagationTracker` — provenance stamps | `EvolutionTracker` — version history, drift detection |
| **Emit** | `emit_boundary_result()` — OTel span events | `emit_compatibility_result()` — OTel span events |

### Split Placement

Follows the same split as Layer 1: framework in ContextCore, concrete contracts
in consuming repos.

| Component | Repo | Path |
|---|---|---|
| Schema models | ContextCore | `src/contextcore/contracts/schema_compat/schema.py` |
| YAML loader | ContextCore | `src/contextcore/contracts/schema_compat/loader.py` |
| Compatibility checker | ContextCore | `src/contextcore/contracts/schema_compat/checker.py` |
| Evolution tracker | ContextCore | `src/contextcore/contracts/schema_compat/evolution.py` |
| OTel emission | ContextCore | `src/contextcore/contracts/schema_compat/otel.py` |
| Concrete contracts | Consuming repos | `contracts/order-pipeline.compat.yaml` |

### Pydantic Models

All models use `extra="forbid"` and Pydantic v2, following the pattern
established in `contracts/propagation/schema.py`.

```python
from pydantic import BaseModel, ConfigDict, Field
from contextcore.contracts.types import ConstraintSeverity


class FieldMapping(BaseModel):
    """Maps a field between two service schemas.

    Declares that source_field in source_service has the same semantic
    meaning as target_field in target_service, with an optional value mapping
    for enum translation.
    """

    model_config = ConfigDict(extra="forbid")

    source_service: str = Field(..., min_length=1)
    source_field: str = Field(..., min_length=1, description="Dot-path field name in source")
    source_type: str = Field("str", description="Expected type in source schema")
    source_values: list[str] | None = Field(
        None, description="Allowed values in source (for enums)"
    )
    target_service: str = Field(..., min_length=1)
    target_field: str = Field(..., min_length=1, description="Dot-path field name in target")
    target_type: str = Field("str", description="Expected type in target schema")
    target_values: list[str] | None = Field(
        None, description="Allowed values in target (for enums)"
    )
    mapping: dict[str, str] | None = Field(
        None, description="Value mapping from source to target (for enums)"
    )
    severity: ConstraintSeverity = Field(
        ConstraintSeverity.WARNING,
        description="Severity when mapping fails or drift is detected",
    )
    description: str | None = Field(None)
    bidirectional: bool = Field(
        False, description="If True, mapping must be invertible (1:1)"
    )


class SchemaEvolutionRule(BaseModel):
    """Declares what schema changes are allowed for a scope.

    Evolution rules define the compatibility contract for how a schema
    may change over time — additive only, backward compatible, or full
    (breaking changes allowed with version bump).
    """

    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(..., min_length=1)
    scope: str = Field(
        ..., min_length=1,
        description="What this rule governs (api_v2, events_v1, etc.)",
    )
    policy: str = Field(
        ..., description="Evolution policy: additive_only | backward_compatible | full"
    )
    allowed_changes: list[str] = Field(
        default_factory=list,
        description="Explicit change types allowed (add_field, add_enum_value, etc.)",
    )
    forbidden_changes: list[str] = Field(
        default_factory=list,
        description="Explicit change types forbidden (remove_field, rename_field, etc.)",
    )
    description: str | None = Field(None)


class SchemaVersion(BaseModel):
    """A snapshot of a service schema at a point in time."""

    model_config = ConfigDict(extra="forbid")

    service: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1, description="SemVer version string")
    fields: dict[str, str] = Field(
        ..., description="Field name → type mapping for this version"
    )
    enums: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Field name → allowed values for enum fields",
    )
    required_fields: list[str] = Field(
        default_factory=list,
        description="Fields that must be present in this version",
    )
    deprecated_fields: list[str] = Field(
        default_factory=list,
        description="Fields that are deprecated but still present",
    )
    timestamp: str | None = Field(None, description="ISO 8601 when this version was recorded")


class SchemaCompatibilitySpec(BaseModel):
    """Root model for a schema compatibility contract YAML file.

    Declares the semantic contract between two or more services — how their
    fields relate, what value mappings apply, and how their schemas may evolve.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        ..., min_length=1, description="Contract schema version (e.g. 0.1.0)"
    )
    contract_type: str = Field(
        "schema_compatibility",
        description="Must be 'schema_compatibility'",
    )
    description: str | None = Field(None)
    mappings: list[FieldMapping] = Field(
        default_factory=list,
        description="Cross-service field mappings",
    )
    evolution_rules: list[SchemaEvolutionRule] = Field(
        default_factory=list,
        description="Rules governing how schemas may change",
    )
    versions: list[SchemaVersion] = Field(
        default_factory=list,
        description="Version history for tracked schemas",
    )


class CompatibilityResult(BaseModel):
    """Result of checking compatibility between two schemas.

    Returned by CompatibilityChecker for each mapping or evolution rule check.
    """

    model_config = ConfigDict(extra="forbid")

    compatible: bool = Field(..., description="Whether the check passed")
    level: str = Field(
        ..., description="Compatibility level checked: structural | semantic | behavioral"
    )
    source_service: str = Field(...)
    target_service: str = Field(...)
    field_results: list[dict] = Field(
        default_factory=list,
        description="Per-field compatibility results",
    )
    drift_details: list[str] = Field(
        default_factory=list,
        description="Human-readable descriptions of detected drift",
    )
    severity: ConstraintSeverity = Field(ConstraintSeverity.WARNING)
    message: str = Field("", description="Summary message")
```

---

## 3. Contract Format

Contracts are YAML files validated against the `SchemaCompatibilitySpec`
Pydantic model. Like Layer 1 contracts, they use `extra="forbid"` to reject
unknown keys at parse time.

### 3.1 Minimal Contract

The simplest contract declares a single field mapping between two services:

```yaml
schema_version: "0.1.0"
contract_type: schema_compatibility
description: "Order status mapping between OrderService and FulfillmentService"

mappings:
  - source_service: order_service
    source_field: status
    source_values: [active, inactive, pending_review]
    target_service: fulfillment_service
    target_field: state
    target_values: [running, stopped, review]
    mapping:
      active: running
      inactive: stopped
      pending_review: review
    severity: warning
    description: "Order status must map to fulfillment state"
```

### 3.2 Full Contract with Evolution Rules

A complete contract includes field mappings, evolution rules, and version
history:

```yaml
schema_version: "0.1.0"
contract_type: schema_compatibility
description: >
  Schema compatibility contract for the order processing pipeline.
  Declares how OrderService, FulfillmentService, and NotificationService
  schemas relate and how they may evolve.

mappings:
  # Status field mapping
  - source_service: order_service
    source_field: status
    source_type: str
    source_values: [active, inactive, pending_review]
    target_service: fulfillment_service
    target_field: state
    target_type: str
    target_values: [running, stopped, review]
    mapping:
      active: running
      inactive: stopped
      pending_review: review
    severity: warning
    description: "Order lifecycle status to fulfillment state"
    bidirectional: true

  # Identifier field mapping (renamed field)
  - source_service: order_service
    source_field: user_id
    source_type: str
    target_service: notification_service
    target_field: account_id
    target_type: str
    severity: blocking
    description: "User identifier — renamed in notification_service v2"

  # Timestamp format mapping (type coercion)
  - source_service: order_service
    source_field: created_at
    source_type: str
    target_service: analytics_service
    target_field: created_at
    target_type: int
    severity: warning
    description: "ISO 8601 string in source, Unix epoch int in target"

evolution_rules:
  - rule_id: order_api_v2
    scope: order_service.api_v2
    policy: additive_only
    allowed_changes:
      - add_optional_field
      - add_enum_value
      - add_endpoint
    forbidden_changes:
      - remove_field
      - rename_field
      - remove_enum_value
      - change_field_type
    description: "OrderService v2 API is additive-only — no breaking changes"

  - rule_id: fulfillment_events
    scope: fulfillment_service.events_v1
    policy: backward_compatible
    allowed_changes:
      - add_optional_field
      - add_enum_value
      - deprecate_field
    forbidden_changes:
      - remove_field
      - change_field_type
    description: "Fulfillment event schema must remain backward compatible"

versions:
  - service: order_service
    version: "2.0.0"
    fields:
      order_id: str
      user_id: str
      status: str
      created_at: str
      total_amount: float
      region: str
    enums:
      status: [active, inactive, pending_review]
    required_fields: [order_id, user_id, status, created_at]
    deprecated_fields: []
    timestamp: "2026-01-15T00:00:00Z"

  - service: order_service
    version: "2.1.0"
    fields:
      order_id: str
      user_id: str
      status: str
      created_at: str
      total_amount: float
      region: str
      priority: str           # Added in 2.1.0
    enums:
      status: [active, inactive, pending_review]
      priority: [standard, express, overnight]
    required_fields: [order_id, user_id, status, created_at]
    deprecated_fields: []
    timestamp: "2026-02-01T00:00:00Z"

  - service: fulfillment_service
    version: "1.3.0"
    fields:
      fulfillment_id: str
      order_id: str
      state: str
      assigned_at: int
    enums:
      state: [running, stopped, review]
    required_fields: [fulfillment_id, order_id, state]
    deprecated_fields: []
    timestamp: "2026-01-20T00:00:00Z"
```

### 3.3 Field Mapping Specification

Each mapping in the contract is a `FieldMapping`:

| Property | Type | Required | Description |
|---|---|---|---|
| `source_service` | str | Yes | Service producing the field |
| `source_field` | str | Yes | Dot-path field name in source schema |
| `source_type` | str | No | Expected type in source. Default: `"str"` |
| `source_values` | list[str] | No | Allowed values for enum fields |
| `target_service` | str | Yes | Service consuming the field |
| `target_field` | str | Yes | Dot-path field name in target schema |
| `target_type` | str | No | Expected type in target. Default: `"str"` |
| `target_values` | list[str] | No | Allowed values for enum fields |
| `mapping` | dict[str,str] | No | Value translation from source to target |
| `severity` | enum | No | `blocking` / `warning` / `advisory`. Default: `warning` |
| `description` | str | No | Human-readable description |
| `bidirectional` | bool | No | If `true`, mapping must be invertible. Default: `false` |

**Bidirectional mappings** require that the value mapping is 1:1 (injective).
If `active → running`, then `running → active` must also hold. This is
validated at contract load time — a bidirectional mapping with a non-injective
value map is a contract parse error.

### 3.4 Evolution Rule Specification

| Property | Type | Required | Description |
|---|---|---|---|
| `rule_id` | str | Yes | Unique identifier for this rule |
| `scope` | str | Yes | What this rule governs (e.g. `order_service.api_v2`) |
| `policy` | str | Yes | `additive_only` / `backward_compatible` / `full` |
| `allowed_changes` | list[str] | No | Explicit allowed change types |
| `forbidden_changes` | list[str] | No | Explicit forbidden change types |
| `description` | str | No | Human-readable description |

**Policy semantics:**

| Policy | Meaning | Typical Use |
|---|---|---|
| `additive_only` | Only new optional fields and new enum values. No removals, no renames, no type changes. | Public APIs, stable contracts |
| `backward_compatible` | New optional fields, new enum values, deprecation allowed. No removal of non-deprecated fields. | Internal APIs, event schemas |
| `full` | Any change allowed, including breaking. Requires version bump. | Development APIs, prototyping |

---

## 4. Compatibility Levels

Schema compatibility is not binary — two schemas can agree at one level but
diverge at another. Layer 2 defines three compatibility levels, each mapped to
a `ConstraintSeverity` from `contracts/types.py`.

### 4.1 Level Definitions

```
Level 3: BEHAVIORAL    ─── Do they use the field the same way?    (BLOCKING)
         │
Level 2: SEMANTIC      ─── Do the values mean the same thing?     (WARNING)
         │
Level 1: STRUCTURAL    ─── Do the field names and types match?    (ADVISORY)
```

| Level | Question | Checks | Severity | Example Violation |
|---|---|---|---|---|
| **STRUCTURAL** | Do field names and types match? | Field exists, type matches, required/optional alignment | `ADVISORY` | Source has `user_id: str`, target has `userId: str` |
| **SEMANTIC** | Do field values have equivalent meaning? | Enum value mapping is complete, no unmapped values | `WARNING` | Source sends `active`, target has no mapping for it |
| **BEHAVIORAL** | Do both sides use the field the same way? | Value ranges, nullability contracts, default behavior | `BLOCKING` | Source treats `null` as "use default", target treats `null` as "delete" |

### 4.2 Why Three Levels

Structural compatibility catches the obvious problems — renamed fields, changed
types. But it misses the subtle ones. Two services can have structurally
identical schemas (`{"status": str}`) and still be semantically incompatible
(`"active"` vs `"running"`).

Semantic compatibility catches the mapping problems — enum drift, value
translation. But it misses behavioral divergence. Two services can agree that
`status: active` maps to `state: running` and still disagree on what happens
when the field is `null` — one treats it as "use the last known value," the
other treats it as "set to default."

Behavioral compatibility is the hardest to declare and check, but it catches
the failures that produce the most confusing symptoms.

### 4.3 Relationship to Layer 1 Severity

The three compatibility levels compose with Layer 1's three severity levels:

```
Layer 1 (Propagation):    BLOCKING     WARNING      ADVISORY
                          field must   field should  field may
                          be present   propagate     be present
                              │            │             │
Layer 2 (Compatibility):  BEHAVIORAL   SEMANTIC     STRUCTURAL
                          usage must   values must   names must
                          match        map           align
```

A field can be `BLOCKING` in Layer 1 (must be present) but only `ADVISORY` in
Layer 2 (structural check only — we trust the types match). Conversely, a field
can be `ADVISORY` in Layer 1 (nice to have) but `BLOCKING` in Layer 2 (if it IS
present, the behavioral contract must hold).

The layers are independent. You can run Layer 1 without Layer 2, or Layer 2
without Layer 1. But together, they answer the complete question: "Is the field
present (L1), and is it the right shape (L2)?"

---

## 5. Validation Flow

### 5.1 Static Analysis (CI Time)

At CI time, the `CompatibilityChecker` compares schema versions declared in the
contract against actual service schemas (extracted from code, OpenAPI specs, or
Protobuf definitions).

```
PR changes service A's schema
             │
             ▼
┌─────────────────────────────────┐
│ schema_compat_check CI step     │
│                                 │
│ 1. Load compat contract YAML    │
│ 2. Extract current schema from  │
│    code / OpenAPI / Proto        │
│ 3. Compare against declared     │
│    versions in contract          │
│ 4. Check evolution rules         │
│ 5. Verify all mappings still     │
│    hold with new schema          │
└─────────────────────────────────┘
             │
     ┌───────┼───────┐
     ▼       ▼       ▼
  PASS    WARNING   FAIL
  (all     (drift    (breaking
  levels   at        change
  OK)     semantic   violates
          level)     evolution
                     rule)
```

**Static checks performed:**

| Check | Level | What It Validates |
|---|---|---|
| Field presence | STRUCTURAL | All mapped source/target fields exist in their schemas |
| Type alignment | STRUCTURAL | Source and target field types are compatible |
| Enum coverage | SEMANTIC | All source enum values have a target mapping |
| Value mapping completeness | SEMANTIC | No unmapped values in either direction (if bidirectional) |
| Evolution rule compliance | SEMANTIC | Schema change between versions respects declared policy |
| Nullability contract | BEHAVIORAL | Source and target agree on null handling |
| Default agreement | BEHAVIORAL | Default values are semantically equivalent |

### 5.2 Runtime Validation (Boundary Crossing)

At runtime, when data crosses a service boundary, the `CompatibilityChecker`
validates the actual payload against the declared mappings:

```
Service A produces response
             │
             ▼
┌─────────────────────────────────┐
│ check_compatibility()           │
│                                 │
│ 1. Resolve source field value   │
│ 2. Look up mapping for field    │
│ 3. Translate value via mapping  │
│ 4. Check result matches target  │
│    schema expectations          │
│ 5. Emit OTel event              │
└─────────────────────────────────┘
             │
             ▼
    CompatibilityResult
    (compatible: bool,
     level: str,
     drift_details: [...])
```

Runtime validation is **read-only** — it does not transform the payload. The
checker inspects and reports but does not modify. This is a deliberate
difference from Layer 1, where the `BoundaryValidator` applies defaults. In
Layer 2, transformation is the service's responsibility; the contract system
only verifies that the transformation was correct.

**Why not transform at runtime?** Because value mapping can be lossy (`active`
and `pending_review` might both map to `running`), and the correct
transformation depends on business logic that the contract system should not
encode. The contract declares what the mapping *should be*. The service
implements it. The checker verifies it was implemented correctly.

### 5.3 Integration with Layer 1

When both layers are active, validation happens in sequence:

```
Phase N-1 completes
       │
       ▼
Layer 1: validate_phase_boundary()    ← "Is the field present?"
       │ (passes)
       ▼
Layer 2: check_compatibility()        ← "Is it the right shape?"
       │ (passes)
       ▼
Phase N executes
```

If Layer 1 fails (field absent), Layer 2 is skipped for that field — there is
nothing to check compatibility on. Layer 1 is always the prerequisite.

---

## 6. Evolution Tracking

### 6.1 Version Comparison Algorithm

The `EvolutionTracker` compares consecutive `SchemaVersion` entries to detect
changes and check them against evolution rules.

```
compare_versions(v_old: SchemaVersion, v_new: SchemaVersion):
    changes = []

    # Field additions
    for field in v_new.fields - v_old.fields:
        changes.append(Change(type="add_field", field=field))

    # Field removals
    for field in v_old.fields - v_new.fields:
        changes.append(Change(type="remove_field", field=field))

    # Type changes
    for field in v_old.fields & v_new.fields:
        if v_old.fields[field] != v_new.fields[field]:
            changes.append(Change(type="change_field_type", field=field,
                                  old=v_old.fields[field], new=v_new.fields[field]))

    # Enum value additions
    for field in v_old.enums & v_new.enums:
        added = set(v_new.enums[field]) - set(v_old.enums[field])
        removed = set(v_old.enums[field]) - set(v_new.enums[field])
        for val in added:
            changes.append(Change(type="add_enum_value", field=field, value=val))
        for val in removed:
            changes.append(Change(type="remove_enum_value", field=field, value=val))

    # Required field changes
    new_required = set(v_new.required_fields) - set(v_old.required_fields)
    for field in new_required:
        if field in v_old.fields:
            changes.append(Change(type="make_required", field=field))

    return changes
```

### 6.2 Change Classification

Each detected change is classified as compatible or breaking based on the
applicable evolution rule:

| Change Type | `additive_only` | `backward_compatible` | `full` |
|---|---|---|---|
| `add_optional_field` | Allowed | Allowed | Allowed |
| `add_required_field` | **Forbidden** | **Forbidden** | Allowed |
| `add_enum_value` | Allowed | Allowed | Allowed |
| `remove_field` | **Forbidden** | **Forbidden** (unless deprecated) | Allowed |
| `rename_field` | **Forbidden** | **Forbidden** | Allowed |
| `change_field_type` | **Forbidden** | **Forbidden** | Allowed |
| `remove_enum_value` | **Forbidden** | **Forbidden** | Allowed |
| `make_required` | **Forbidden** | **Forbidden** | Allowed |
| `deprecate_field` | **Forbidden** | Allowed | Allowed |

### 6.3 Breaking Change Detection

When a change violates an evolution rule, the tracker produces a
`EvolutionCheckResult`:

```python
class EvolutionCheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    compatible: bool = Field(..., description="Whether all changes respect rules")
    service: str = Field(...)
    old_version: str = Field(...)
    new_version: str = Field(...)
    total_changes: int = Field(0)
    breaking_changes: list[dict] = Field(
        default_factory=list,
        description="Changes that violate evolution rules",
    )
    compatible_changes: list[dict] = Field(
        default_factory=list,
        description="Changes that respect evolution rules",
    )
    applicable_rule: str | None = Field(
        None, description="rule_id of the evolution rule applied"
    )
    message: str = Field("")
```

### 6.4 Migration Path Validation

When a breaking change is detected, the tracker checks whether a migration path
exists in the contract. A migration path is a sequence of version transitions
where each step respects its evolution rule:

```
v1.0 ──(additive_only)──→ v1.1 ──(additive_only)──→ v1.2
                                                        │
                                              (version bump to v2.0)
                                                        │
v2.0 ──(backward_compatible)──→ v2.1

Valid: v1.0 → v1.1 → v1.2 → v2.0 (version bump allowed) → v2.1
Invalid: v1.0 → v2.0 (skipping intermediate versions, no bump declared)
```

---

## 7. OTel Event Semantics

All events follow ContextCore telemetry conventions and are emitted as OTel span
events on the current active span. If OTel is not installed, events are logged
only (no crash). This follows the `_HAS_OTEL` guard pattern from
`contracts/propagation/otel.py`.

### 7.1 Compatibility Check Event

**Event name:** `schema.compatibility.check`

Emitted whenever a compatibility check passes — all mappings hold, types align,
values map correctly.

| Attribute | Type | Description |
|---|---|---|
| `schema.source_service` | str | Service producing the data |
| `schema.target_service` | str | Service consuming the data |
| `schema.level` | str | `structural` / `semantic` / `behavioral` |
| `schema.compatible` | bool | Whether the check passed |
| `schema.fields_checked` | int | Number of field mappings verified |
| `schema.drift_count` | int | Number of drift items detected (0 for pass) |
| `schema.message` | str | Human-readable summary |

**TraceQL query — find all compatibility checks:**
```traceql
{ name = "schema.compatibility.check" }
```

**TraceQL query — find passing checks for a specific service pair:**
```traceql
{ name = "schema.compatibility.check"
  && span.schema.source_service = "order_service"
  && span.schema.target_service = "fulfillment_service"
  && span.schema.compatible = true }
```

### 7.2 Drift Detection Event

**Event name:** `schema.compatibility.drift`

Emitted when semantic drift is detected — a field mapping is incomplete, an
enum value is unmapped, or a type coercion is needed.

| Attribute | Type | Description |
|---|---|---|
| `schema.source_service` | str | Service producing the data |
| `schema.target_service` | str | Service consuming the data |
| `schema.level` | str | `structural` / `semantic` / `behavioral` |
| `schema.compatible` | bool | `false` |
| `schema.drift_type` | str | `unmapped_value` / `type_mismatch` / `missing_field` / `extra_field` |
| `schema.drift_field` | str | Field where drift was detected |
| `schema.drift_detail` | str | Human-readable drift description |
| `schema.severity` | str | `blocking` / `warning` / `advisory` |

**TraceQL query — find semantic drift:**
```traceql
{ name = "schema.compatibility.drift" && span.schema.level = "semantic" }
```

**TraceQL query — find unmapped enum values:**
```traceql
{ name = "schema.compatibility.drift" && span.schema.drift_type = "unmapped_value" }
```

### 7.3 Breaking Change Event

**Event name:** `schema.compatibility.breaking`

Emitted when a schema evolution violates a declared evolution rule. This is the
highest-severity event — it indicates a contract violation, not just drift.

| Attribute | Type | Description |
|---|---|---|
| `schema.service` | str | Service whose schema changed |
| `schema.old_version` | str | Previous schema version |
| `schema.new_version` | str | New schema version |
| `schema.rule_id` | str | Evolution rule that was violated |
| `schema.change_type` | str | What changed (`remove_field`, `change_field_type`, etc.) |
| `schema.change_field` | str | Field affected by the change |
| `schema.policy` | str | Evolution policy that was violated |
| `schema.message` | str | Human-readable explanation |

**TraceQL query — find breaking changes:**
```traceql
{ name = "schema.compatibility.breaking" }
```

**TraceQL query — find breaking changes in a specific service:**
```traceql
{ name = "schema.compatibility.breaking"
  && span.schema.service = "order_service" }
```

### 7.4 Relationship to Layer 1 Events

Layer 1 and Layer 2 events are complementary and can appear on the same span:

| Layer 1 Event | Layer 2 Event | Combined Meaning |
|---|---|---|
| `context.boundary.entry` (passed) | `schema.compatibility.check` (passed) | Field present AND correct shape |
| `context.boundary.enrichment` (defaulted) | — (skipped) | Field absent, default applied, no shape to check |
| `context.chain.validated` (intact) | `schema.compatibility.check` (passed) | Full pipeline flow AND compatible at every boundary |
| `context.chain.degraded` | `schema.compatibility.drift` | Field has default value AND drift detected |
| `context.chain.broken` | — (skipped) | Field missing entirely, no shape to check |

---

## 8. Relationship to Layer 1

Layer 1 and Layer 2 address orthogonal failure modes that often co-occur.

### 8.1 What Each Layer Catches

```
                    Layer 1                      Layer 2
                    (Propagation)                (Schema Compat)
                    ─────────────                ────────────────
Does the field      ✓ Yes                        ─ Not its concern
reach destination?

Is the field name   ─ Not its concern            ✓ Yes (structural)
correct?

Do the values       ─ Not its concern            ✓ Yes (semantic)
translate?

Is the field used   ─ Not its concern            ✓ Yes (behavioral)
correctly?

Did the field       ✓ Yes (provenance stamps)    ─ Not its concern
change in transit?
```

### 8.2 Composition Example

Consider the order pipeline: `OrderService → FulfillmentService →
NotificationService`.

**Layer 1 contract** declares:
```yaml
propagation_chains:
  - chain_id: order_status_to_notification
    source: { phase: order, field: status }
    destination: { phase: notification, field: status }
    severity: warning
```

**Layer 2 contract** declares:
```yaml
mappings:
  - source_service: order_service
    source_field: status
    source_values: [active, inactive]
    target_service: fulfillment_service
    target_field: state
    target_values: [running, stopped]
    mapping:
      active: running
      inactive: stopped
```

With both layers:
1. Layer 1 verifies: "The `status` field left OrderService and arrived at
   NotificationService" → INTACT
2. Layer 2 verifies: "OrderService's `status: active` was correctly translated
   to FulfillmentService's `state: running`" → compatible

Without Layer 1: You know the mapping is correct, but not whether the field
actually arrived.

Without Layer 2: You know the field arrived, but not whether it was correctly
translated at the FulfillmentService boundary.

### 8.3 Shared Infrastructure

Both layers share the same foundation from `contracts/types.py`:

| Shared Type | Layer 1 Usage | Layer 2 Usage |
|---|---|---|
| `ConstraintSeverity` | Field absence severity | Mapping drift severity |
| `PropagationStatus` | Overall boundary result | Not directly used (but compatible) |
| `ChainStatus` | End-to-end flow status | Not directly used (but compatible) |

Both layers use the same `_HAS_OTEL` guard pattern, the same `_add_span_event`
helper pattern, and the same `extra="forbid"` model convention. A future
`ContextCoreContract` super-type could unify `ContextContract` (Layer 1) and
`SchemaCompatibilitySpec` (Layer 2) under a common interface.

---

## 9. Relationship to Existing Tools

Layer 2 does not replace existing schema tooling. It fills the gap between
per-service schema validation and cross-service contract verification.

### 9.1 Comparison Matrix

| Tool | Structural | Semantic | Behavioral | Runtime | CI | Cross-Service | OTel |
|---|---|---|---|---|---|---|---|
| **Protobuf/gRPC** | Wire format | No | No | No | Yes | Partial (IDL) | No |
| **JSON Schema** | Yes | No | No | Yes | Yes | No | No |
| **Avro** | Wire format | No | No | Yes | Yes | Partial (registry) | No |
| **Pact** | Yes | Partial | No | No | Yes | Yes | No |
| **OpenAPI** | Yes | Partial | No | No | Yes | No | No |
| **Layer 2** | Yes | Yes | Yes | Yes | Yes | Yes | Yes |

### 9.2 What Each Tool Does Well

**Protobuf/gRPC:** Excellent wire-format backward compatibility. Field numbers
are stable, so adding fields is always safe. But Proto doesn't track *semantic*
compatibility — field 5 can change from "user's active status" to "account
deletion flag" with the same type (`bool`) and no wire-format break.

**JSON Schema:** Validates individual documents against a schema. Cannot express
cross-schema relationships. "This document is valid JSON Schema" and "this
document is compatible with that service's expectations" are different
statements.

**Avro:** Schema evolution with compatibility modes (BACKWARD, FORWARD, FULL).
The closest existing analog to Layer 2's evolution rules. But Avro operates on
binary serialization format — it doesn't address semantic value mapping (e.g.,
`active → running`), only structural changes (field added/removed/renamed).

**Pact:** Consumer-driven contract testing. Verifies that a provider's response
matches a consumer's expectations at test time. Strong cross-service validation,
but:
- Test-time only (not runtime)
- HTTP request/response only (not event-driven)
- No value mapping (assumes same field names and values)
- No evolution tracking (each test is a point-in-time check)
- No observability integration (results are in test reports, not OTel)

### 9.3 What Layer 2 Adds

1. **Semantic value mapping.** "A's `active` means B's `running`." No existing
   tool declares this. It lives in code comments, wiki pages, or tribal
   knowledge. Layer 2 makes it a machine-parseable YAML artifact.

2. **Runtime + CI validation.** Pact runs at test time. JSON Schema runs at
   validation time. Layer 2 runs at both *and* at every boundary crossing in
   production, emitting OTel events.

3. **Evolution tracking.** Avro has compatibility modes. Layer 2 has evolution
   rules that are scoped per service, per API version, with explicit
   allowed/forbidden change lists. The version history is part of the contract,
   not a separate registry.

4. **Three-level compatibility model.** No existing tool distinguishes structural
   (names match), semantic (values map), and behavioral (usage matches). This
   matters because two schemas can be structurally and semantically compatible
   but behaviorally incompatible.

5. **Observability integration.** Schema compatibility results are OTel span
   events, queryable via TraceQL, dashboardable in Grafana, alertable via
   Alertmanager. This is the ContextCore differentiator — contract verification
   results live in the same infrastructure as runtime telemetry.

---

## 10. Adoption Path

### 10.1 Phase 1: Declare (Week 1)

Write `SchemaCompatibilitySpec` YAML for one service pair. This is a
documentation exercise that happens to be machine-parseable.

```yaml
# Start with the most critical mapping
schema_version: "0.1.0"
contract_type: schema_compatibility
mappings:
  - source_service: order_service
    source_field: status
    target_service: fulfillment_service
    target_field: state
    mapping:
      active: running
      inactive: stopped
```

**Cost:** One YAML file. Reviewed in a PR.
**Benefit:** The mapping is no longer tribal knowledge.

### 10.2 Phase 2: Check at CI (Week 2-3)

Add a CI step that loads the contract and compares it against service schemas
extracted from code or OpenAPI specs.

```yaml
# .github/workflows/schema-compat.yml
- name: Check schema compatibility
  run: |
    contextcore contract schema-check \
      --contract contracts/order-fulfillment.compat.yaml \
      --source-schema order_service/openapi.yaml \
      --target-schema fulfillment_service/openapi.yaml
```

**Cost:** One CI step.
**Benefit:** PRs that break schema compatibility are caught before merge.

### 10.3 Phase 3: Monitor at Runtime (Week 4-6)

Wire the `CompatibilityChecker` into service boundary code. Emit OTel events
for every compatibility check.

```python
from contextcore.contracts.schema_compat import (
    CompatibilityChecker,
    emit_compatibility_result,
)

checker = CompatibilityChecker(contract_path="contracts/order-fulfillment.compat.yaml")

# At the boundary between services
result = checker.check(
    source_service="order_service",
    target_service="fulfillment_service",
    payload=response_data,
)
emit_compatibility_result(result)
```

**Cost:** A few lines of code at each boundary.
**Benefit:** Schema drift is observable in Grafana.

### 10.4 Phase 4: Track Evolution (Week 7-8)

Start recording schema versions in the contract. Add evolution rules. Run
version comparison on each schema change.

**Cost:** Version entries in YAML. Evolution rules.
**Benefit:** Breaking changes are caught and historically tracked.

### 10.5 Phase 5: Tighten (Ongoing)

As confidence grows:
- Promote mappings from `advisory` → `warning` → `blocking`
- Add behavioral checks for critical fields
- Add bidirectional requirements for fields that flow both ways
- Connect Layer 2 events to alerting rules

This follows the same progressive adoption path as Layer 1 and TypeScript's
type strictness.

---

## 11. Dashboard Integration

### 11.1 Recommended Panels

**Schema Compatibility Status (Stat panel)**
```traceql
{ name = "schema.compatibility.check" }
| select(span.schema.compatible)
```

**Drift Events Over Time (Time series)**
```traceql
{ name = "schema.compatibility.drift" }
| rate()
```

**Breaking Changes (Table)**
```traceql
{ name = "schema.compatibility.breaking" }
| select(
    span.schema.service,
    span.schema.old_version,
    span.schema.new_version,
    span.schema.change_type,
    span.schema.change_field,
    span.schema.rule_id,
    span.schema.message
  )
```

**Drift by Service Pair (Bar gauge)**
```traceql
{ name = "schema.compatibility.drift" }
| select(span.schema.source_service, span.schema.target_service)
| count() by (span.schema.source_service, span.schema.target_service)
```

**Unmapped Values (Logs panel)**
```traceql
{ name = "schema.compatibility.drift" && span.schema.drift_type = "unmapped_value" }
| select(span.schema.drift_field, span.schema.drift_detail)
```

### 11.2 PromQL Queries (via Loki Recording Rules)

If schema events are also emitted as structured logs (dual-emit pattern), Loki
recording rules can derive Prometheus metrics:

```yaml
groups:
  - name: contextcore_schema_compat
    rules:
      - record: contextcore_schema_drift_total
        expr: |
          sum(count_over_time(
            {job="contextcore"} | json | event="schema.compatibility.drift" [5m]
          )) by (source_service, target_service, drift_type)

      - record: contextcore_schema_breaking_total
        expr: |
          sum(count_over_time(
            {job="contextcore"} | json | event="schema.compatibility.breaking" [5m]
          )) by (service, change_type)

      - record: contextcore_schema_compat_ratio
        expr: |
          sum(count_over_time(
            {job="contextcore"} | json | event="schema.compatibility.check" | compatible="true" [1h]
          ))
          /
          sum(count_over_time(
            {job="contextcore"} | json | event="schema.compatibility.check" [1h]
          ))
```

### 11.3 Alerting Rules

**Alert: Schema drift detected**
```yaml
- alert: SchemaCompatibilityDrift
  expr: |
    sum(rate(contextcore_schema_drift_total[15m])) > 0
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Schema drift detected between services"
    description: |
      At least one field mapping between services has drifted.
      Check the Schema Compatibility dashboard for details.
```

**Alert: Breaking schema change**
```yaml
- alert: SchemaBreakingChange
  expr: |
    sum(rate(contextcore_schema_breaking_total[5m])) > 0
  for: 0m
  labels:
    severity: critical
  annotations:
    summary: "Breaking schema change violates evolution rule"
    description: |
      A schema change has violated a declared evolution rule.
      This may cause silent failures at service boundaries.
```

---

## 12. Consequences

### Positive

1. **Cross-service contracts become explicit artifacts.** The mapping between
   `status: active` and `state: running` lives in a YAML file reviewed in PRs,
   not in a wiki page or tribal knowledge.

2. **Schema drift becomes observable.** Every unmapped value, type mismatch,
   or field rename produces an OTel event — queryable, dashboardable, alertable.

3. **Evolution is governed, not ad-hoc.** Evolution rules declare what changes
   are allowed. Breaking changes are caught at CI time, not discovered in
   production.

4. **Three-level model matches reality.** Real schema incompatibilities span
   structural (wrong field name), semantic (wrong value mapping), and behavioral
   (wrong usage pattern). One level is not enough.

5. **Composes with Layer 1.** "Did the field arrive?" (Layer 1) + "Is it the
   right shape?" (Layer 2) = complete cross-boundary verification.

6. **Progressive adoption.** Start with one mapping in YAML. Add CI checks.
   Add runtime monitoring. Tighten severity. Same path as Layer 1.

### Neutral

1. **Contract YAML must be maintained.** When service schemas change, the
   compatibility contract must be updated. This is the same cost as maintaining
   API documentation — except the contract is machine-verified.

2. **Version history grows over time.** The `versions` list in the contract
   accumulates schema snapshots. Older versions can be pruned once all consumers
   have migrated past them.

3. **Runtime checking adds latency.** Each boundary check involves loading the
   contract (cached) and checking field mappings. For typical contracts (10-50
   mappings), this is sub-millisecond.

### Negative

1. **Behavioral compatibility is hard to declare.** Structural and semantic
   checks are straightforward (field exists, value maps). Behavioral checks
   ("what does `null` mean?") require nuanced declarations that may not fit
   cleanly into YAML. Initial implementation may support only structural and
   semantic levels.

2. **Schema extraction is not standardized.** The CI check needs to extract
   the current schema from code (Pydantic models, OpenAPI specs, Proto files,
   or raw dictionaries). Each format requires a different extractor. Initial
   implementation will support Pydantic and OpenAPI; others will be added as
   needed.

3. **Bidirectional mappings are constraining.** Requiring 1:1 value mappings
   means many-to-one translations (e.g., `pending_review` and `active` both
   map to `running`) cannot be declared as bidirectional. This is intentional
   (lossy mappings cannot be safely reversed) but may surprise users.

4. **Not a schema registry.** Layer 2 declares contracts between pairs of
   services. It does not provide a centralized registry of all schemas. A schema
   registry (Layer 2.5?) is a natural extension but is out of scope for this
   design.

---

## 13. Future Work

1. **Schema registry.** A centralized registry where services publish their
   current schemas, and compatibility contracts are auto-validated against all
   published versions. This would move from pairwise contracts to a global
   compatibility graph.

2. **Automated migration generation.** When a breaking change is detected,
   generate a migration script or adapter function that translates between old
   and new schemas. Layer 2 has the mapping information needed to produce these
   automatically.

3. **OpenAPI / Protobuf extractors.** CI-time schema extraction from OpenAPI
   3.x specs and Protobuf definitions. Initial implementation supports Pydantic
   models; extractors for other formats are a natural extension.

4. **Behavioral compatibility DSL.** A mini-language for declaring behavioral
   contracts beyond what YAML key-value pairs can express. For example:
   `when source.status is null then target.state must be "stopped"`.

5. **Cross-pipeline compatibility.** Compatibility contracts that span multiple
   pipelines — "Pipeline A's output schema is compatible with Pipeline B's
   input schema." This composes with Layer 1's cross-pipeline chains (future
   work item 6 in the Layer 1 design).

6. **Compatibility score metric.** A continuous metric (0.0-1.0) representing
   the overall schema compatibility health across all declared contracts.
   Emitted as an OTel metric gauge, dashboardable alongside Layer 1's
   `completeness_pct`.

7. **Drift prediction.** Using version history trends to predict when a schema
   change is likely to cause drift. If service A has been adding fields at a
   rate of 2 per month and service B's mapping hasn't been updated in 3 months,
   flag the contract as "stale — likely drifted."

8. **Integration with Pact.** Import existing Pact contracts as Layer 2
   compatibility contracts. Pact already declares consumer expectations — Layer
   2 adds semantic mapping, evolution rules, and OTel integration on top.

9. **Weaver registry integration.** Register schema compatibility event names
   (`schema.compatibility.*`) in the Weaver semconv registry alongside Layer 1's
   `context.boundary.*` and `context.chain.*` events.

---

## Appendix A: Planned File Inventory

| File | Purpose | Estimated Lines |
|---|---|---|
| `contracts/schema_compat/__init__.py` | Public API, re-exports | ~60 |
| `contracts/schema_compat/schema.py` | Pydantic models (above) | ~200 |
| `contracts/schema_compat/loader.py` | YAML loading + caching | ~80 |
| `contracts/schema_compat/checker.py` | Structural/semantic/behavioral checks | ~300 |
| `contracts/schema_compat/evolution.py` | Version comparison + rule checking | ~250 |
| `contracts/schema_compat/otel.py` | OTel event emission helpers | ~150 |
| `contracts/types.py` (modified) | Add `CompatibilityLevel` enum | +10 |
| **Total** | | **~1,050** |

## Appendix B: Type Hierarchy

```
SchemaCompatibilitySpec
├── schema_version: str
├── contract_type: str                ("schema_compatibility")
├── description: str?
├── mappings: list[FieldMapping]
│   └── FieldMapping
│       ├── source_service: str
│       ├── source_field: str          (dot-path)
│       ├── source_type: str           (Python type name)
│       ├── source_values: list[str]?  (enum values)
│       ├── target_service: str
│       ├── target_field: str          (dot-path)
│       ├── target_type: str
│       ├── target_values: list[str]?
│       ├── mapping: dict[str,str]?    (value translation)
│       ├── severity: ConstraintSeverity
│       ├── description: str?
│       └── bidirectional: bool
├── evolution_rules: list[SchemaEvolutionRule]
│   └── SchemaEvolutionRule
│       ├── rule_id: str
│       ├── scope: str
│       ├── policy: str                (additive_only | backward_compatible | full)
│       ├── allowed_changes: list[str]
│       ├── forbidden_changes: list[str]
│       └── description: str?
└── versions: list[SchemaVersion]
    └── SchemaVersion
        ├── service: str
        ├── version: str               (SemVer)
        ├── fields: dict[str, str]     (field name → type)
        ├── enums: dict[str, list[str]](field name → allowed values)
        ├── required_fields: list[str]
        ├── deprecated_fields: list[str]
        └── timestamp: str?

CompatibilityResult
├── compatible: bool
├── level: str                         (structural | semantic | behavioral)
├── source_service: str
├── target_service: str
├── field_results: list[dict]
├── drift_details: list[str]
├── severity: ConstraintSeverity
└── message: str

EvolutionCheckResult
├── compatible: bool
├── service: str
├── old_version: str
├── new_version: str
├── total_changes: int
├── breaking_changes: list[dict]
├── compatible_changes: list[dict]
├── applicable_rule: str?
└── message: str
```
